"""Execução local do milestone M1."""

import argparse
import json
from pathlib import Path
import sys

from .cameras import CameraError, SimulatedCamera
from .perception import BallDetector
from .pipeline import run_pipeline


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("deve ser um inteiro positivo")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RoboSense Lab M1: detecção em imagens sintéticas.")
    parser.add_argument("--frames", type=positive_integer, default=60, help="quantidade de frames (padrão: 60)")
    parser.add_argument("--output", type=Path, default=Path("runs/m1.jsonl"), help="novo arquivo JSONL; não sobrescreve")
    args = parser.parse_args(argv)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            camera = SimulatedCamera(args.frames)
            summary = run_pipeline(camera, BallDetector(), stream, expected_positions=camera.expected_positions)
    except (OSError, CameraError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    print(f"Registro: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
