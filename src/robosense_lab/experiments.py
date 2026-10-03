"""Comparação reproduzível dos sete cenários do milestone M2."""

import argparse
import json
from pathlib import Path
import sys

from .__main__ import nonnegative_integer, positive_integer
from .cameras import CameraError, SimulatedCamera
from .perception import BallDetector
from .pipeline import run_pipeline
from .telemetry import runtime_versions


def run_experiments(output_dir: Path, *, frame_count: int = 60, seed: int = 42) -> dict:
    """Cria uma pasta nova; perda de câmera produz métricas parciais identificadas."""
    # Valida antes de criar qualquer resultado.
    SimulatedCamera(frame_count, seed=seed).close()
    output_dir.mkdir(parents=True, exist_ok=False)
    scenarios = (
        ("baseline", {}),
        ("noise", {"noise_std": 45.0}),
        ("partial_occlusion", {"occlusion_fraction": 0.5}),
        ("full_occlusion", {"occlusion_fraction": 1.0}),
        ("camera_loss", {"loss_at_frame": frame_count // 2}),
        ("delay_50ms", {"delay_ns": 50_000_000}),
        ("delay_200ms", {"delay_ns": 200_000_000}),
    )
    age_limit_ns = 100_000_000
    versions = runtime_versions()
    results = []
    for name, parameters in scenarios:
        camera = SimulatedCamera(frame_count, seed=seed, **parameters)
        log_path = output_dir / f"{name}.jsonl"
        try:
            with log_path.open("x", encoding="utf-8") as stream:
                try:
                    metrics = run_pipeline(
                        camera, BallDetector(), stream, expected_positions=camera.expected_positions,
                        max_frame_age_ns=age_limit_ns,
                        run_metadata={"scenario": name, "simulation": camera.configuration, "runtime": versions},
                    )
                    status = "completed"
                except CameraError:
                    # Somente a falha terminal planejada permite continuar a comparação.
                    if parameters.get("loss_at_frame") is None:
                        raise
                    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
                    last_event = events[-1]
                    if last_event["type"] != "camera_error":
                        raise
                    metrics = last_event["partial_summary"]
                    if metrics["frames_received"] != parameters["loss_at_frame"]:
                        raise
                    status = "camera_error"
        finally:
            camera.close()
        metrics = {key: value for key, value in metrics.items() if key != "type"}
        results.append({
            "scenario": name, "status": status, "log": log_path.name,
            "simulation": camera.configuration, "metrics": metrics,
        })
    report = {
        "schema_version": 1, "milestone": "M2", "runtime": versions,
        "max_frame_age_ns": age_limit_ns, "results": results,
    }
    with (output_dir / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa os cenários M2 e registra uma comparação.")
    parser.add_argument("--frames", type=positive_integer, default=60)
    parser.add_argument("--seed", type=nonnegative_integer, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/m2"), help="pasta nova; não sobrescreve")
    args = parser.parse_args(argv)
    try:
        report = run_experiments(args.output_dir, frame_count=args.frames, seed=args.seed)
    except (OSError, CameraError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    for result in report["results"]:
        metrics = result["metrics"]
        print(
            f"{result['scenario']}: {result['status']} | recebidos={metrics['frames_received']} "
            f"processados={metrics['frames']} antigos={metrics['stale_frames']} "
            f"TP={metrics['true_positives']} FP={metrics['false_positives']} FN={metrics['false_negatives']}"
        )
    print(f"Relatório: {(args.output_dir / 'summary.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
