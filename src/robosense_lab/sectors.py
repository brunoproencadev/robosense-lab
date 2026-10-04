"""Detecção por setor e demonstração serial, independentes de webcams físicas."""

import argparse
from contextlib import ExitStack
from pathlib import Path
import sys
from typing import TextIO

import serial

from .__main__ import nonnegative_integer, positive_integer
from .cameras import Camera, CameraError, SimulatedCamera
from .communication import SerialOutput
from .perception import BallDetector
from .pipeline import analyze_frame
from .telemetry import runtime_versions, write_event


SECTOR_ORDER = "FDEA"
# Roteiro sintético: cada direção, ausência e sobreposição frente/direita.
DEMO_ROUTE = ("F", "D", "E", "A", "", "FD")


def parse_sectors(value: str) -> str:
    if not value or any(sector not in SECTOR_ORDER for sector in value) or len(set(value)) != len(value):
        raise argparse.ArgumentTypeError("use setores distintos entre F, D, E e A, por exemplo FDEA ou FD")
    return "".join(sector for sector in SECTOR_ORDER if sector in value)


def make_simulated_cameras(frame_count: int, sectors: str = SECTOR_ORDER) -> dict[str, SimulatedCamera]:
    sectors = parse_sectors(sectors)
    return {
        sector: SimulatedCamera(
            frame_count, camera_id=f"simulated-{sector}",
            visible_frames=[i for i in range(frame_count) if sector in DEMO_ROUTE[i % len(DEMO_ROUTE)]],
        )
        for sector in sectors
    }


def run_sector_pipeline(
    cameras: dict[str, Camera], stream: TextIO, terminal: TextIO, *,
    max_frame_age_ns: int = 100_000_000, serial_output: SerialOutput | None = None,
) -> dict:
    """Avalia um frame por fonte por ciclo, sem reutilizar resultados anteriores.

    Câmera inválida torna o ciclo indisponível; falha de aquisição encerra todas.
    Os relógios e sequências precisam coincidir neste demonstrador sincronizado.
    """
    cycles = detected = no_ball = unavailable = 0
    try:
        if not cameras or any(sector not in SECTOR_ORDER for sector in cameras):
            raise ValueError("é necessário mapear câmeras para setores F/D/E/A")
        if type(max_frame_age_ns) is not int or max_frame_age_ns < 0:
            raise ValueError("limite de idade deve ser um inteiro não negativo")
        observed = [sector for sector in SECTOR_ORDER if sector in cameras]
        detector = BallDetector()
        write_event(stream, {"type": "sector_run_start", "observed_sectors": observed, "runtime": runtime_versions(), "max_frame_age_ns": max_frame_age_ns})
        while True:
            frames = {}
            for sector in observed:
                try:
                    frames[sector] = cameras[sector].read()
                except CameraError as exc:
                    write_event(stream, {"type": "camera_error", "sector": sector, "message": str(exc), "cycles_completed": cycles})
                    raise
            if all(frame is None for frame in frames.values()):
                break
            if any(frame is None for frame in frames.values()):
                write_event(stream, {"type": "camera_error", "message": "fontes terminaram em ciclos diferentes", "cycles_completed": cycles})
                raise CameraError("fontes terminaram em ciclos diferentes")
            stamps = {(frame.sequence, frame.timestamp_ns, frame.clock_domain) for frame in frames.values()}
            if len(stamps) != 1 or next(iter(stamps))[0] != cycles:
                raise ValueError("fontes precisam ter sequência, captura e relógio sincronizados")
            results = {sector: analyze_frame(frames[sector], detector, max_frame_age_ns=max_frame_age_ns) for sector in observed}
            valid = all(result["type"] == "observation" for result in results.values())
            found = [sector for sector in observed if valid and results[sector]["ball_detected"]]
            status = "unavailable" if not valid else "detected" if found else "no_ball"
            sequence, timestamp_ns, clock_domain = next(iter(stamps))
            message = {
                "schema_version": 1, "sequence": sequence, "timestamp_ns": timestamp_ns,
                "clock_domain": clock_domain, "observed_sectors": observed,
                "status": status, "sectors": found,
            }
            if serial_output is not None:
                try:
                    serial_output.send(message)
                except (serial.SerialException, OSError) as exc:
                    write_event(stream, {"type": "serial_error", "message": str(exc), "cycles_completed": cycles})
                    raise
            write_event(stream, {"type": "sector_observation", **message, "cameras": results})
            print(" ".join(found) if found else "SEM_BOLA" if valid else "SEM_DADOS", file=terminal, flush=True)
            cycles += 1
            detected += status == "detected"
            no_ball += status == "no_ball"
            unavailable += status == "unavailable"
        summary = {"type": "sector_run_summary", "cycles": cycles, "detected_cycles": detected, "no_ball_cycles": no_ball, "unavailable_cycles": unavailable}
        write_event(stream, summary)
        return summary
    finally:
        for camera in cameras.values():
            camera.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quatro setores simulados, com PySerial opcional.")
    parser.add_argument("--frames", type=positive_integer, default=12, help="ciclos por câmera (padrão: 12)")
    parser.add_argument("--sectors", type=parse_sectors, default=SECTOR_ORDER, help="câmeras locais: FDEA, FD ou EA, por exemplo")
    parser.add_argument("--output", type=Path, default=Path("runs/sectors.jsonl"), help="novo arquivo JSONL")
    parser.add_argument("--serial-port", help="loop://, COM3 ou /dev/serial/by-id/...; omitido: só terminal")
    parser.add_argument("--baudrate", type=positive_integer, default=115200)
    parser.add_argument("--max-frame-age-ms", type=nonnegative_integer, default=100)
    args = parser.parse_args(argv)
    cameras = make_simulated_cameras(args.frames, args.sectors)
    try:
        with ExitStack() as resources:
            for camera in cameras.values():
                resources.callback(camera.close)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            stream = resources.enter_context(args.output.open("x", encoding="utf-8"))
            output = None
            if args.serial_port is not None:
                output = SerialOutput(args.serial_port, args.baudrate)
                resources.callback(output.close)
            run_sector_pipeline(cameras, stream, sys.stdout, max_frame_age_ns=args.max_frame_age_ms * 1_000_000, serial_output=output)
    except (OSError, ValueError, CameraError, serial.SerialException) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
