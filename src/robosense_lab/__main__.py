"""Execução local dos milestones M1/M2."""

import argparse
import json
import math
from pathlib import Path
import sys

from .cameras import CameraError, SimulatedCamera
from .perception import BallDetector
from .pipeline import run_pipeline
from .telemetry import runtime_versions


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo")
    return number


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("deve ser um inteiro não negativo")
    return number


def noise_standard_deviation(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 255:
        raise argparse.ArgumentTypeError("deve ser finito, entre 0 e 255")
    return number


def fraction(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("deve estar entre 0 e 1")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RoboSense Lab M1/M2: detecção em imagens sintéticas.")
    parser.add_argument("--frames", type=positive_integer, default=60, help="quantidade de frames (padrão: 60)")
    parser.add_argument("--output", type=Path, default=Path("runs/m1.jsonl"), help="novo arquivo JSONL; não sobrescreve")
    parser.add_argument("--noise-std", type=noise_standard_deviation, default=0.0, help="desvio padrão do ruído gaussiano BGR, de 0 a 255")
    parser.add_argument("--seed", type=nonnegative_integer, default=42, help="semente do gerador de ruído (padrão: 42)")
    parser.add_argument("--occlusion", type=fraction, default=0.0, help="fração da largura da bola ocultada, de 0 a 1")
    parser.add_argument("--loss-at-frame", type=nonnegative_integer, help="índice a partir de zero onde a câmera falha")
    parser.add_argument("--delay-ms", type=nonnegative_integer, default=0, help="atraso virtual constante de entrega")
    parser.add_argument("--max-frame-age-ms", type=nonnegative_integer, default=100, help="idade máxima aceita, inclusive (padrão: 100 ms)")
    args = parser.parse_args(argv)
    if args.loss_at_frame is not None and args.loss_at_frame >= args.frames:
        parser.error("--loss-at-frame deve ser menor que --frames")
    camera = SimulatedCamera(
        args.frames, noise_std=args.noise_std, seed=args.seed,
        occlusion_fraction=args.occlusion, loss_at_frame=args.loss_at_frame,
        delay_ns=args.delay_ms * 1_000_000,
    )
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            summary = run_pipeline(
                camera, BallDetector(), stream, expected_positions=camera.expected_positions,
                max_frame_age_ns=args.max_frame_age_ms * 1_000_000,
                run_metadata={"simulation": camera.configuration, "runtime": runtime_versions()},
            )
    except (OSError, CameraError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        camera.close()
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    print(f"Registro: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
