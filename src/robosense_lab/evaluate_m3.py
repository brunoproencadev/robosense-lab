"""Avaliação reproduzível de amostras M3 anotadas visualmente, fora do detector."""

import argparse
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

from .cameras import RecordedVideoCamera
from .m3 import image_sector, sha256
from .perception import BallDetector, BallTracker
from .telemetry import runtime_versions


def score(samples: list[dict]) -> dict:
    tp = fp = fn = tn = sector_hits = 0
    errors, radius_errors = [], []
    for row in samples:
        center = row["expected_center_px"]
        detected = row["detected_center_px"]
        if center is None:
            fp += detected is not None
            tn += detected is None
        elif detected is None:
            fn += 1
        else:
            error = math.dist(center, detected)
            # Tolera anotação aproximada e blur; alvo errado conta FP e FN.
            if error > max(24, row["expected_radius_px"] / 2):
                fp += 1
                fn += 1
                continue
            tp += 1
            errors.append(error)
            radius_errors.append(abs(row["detected_radius_px"] - row["expected_radius_px"]))
            sector_hits += image_sector(center[0], row["width"]) == row["sector"]
    return {"samples": len(samples), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "mean_center_error_px": float(np.mean(errors)) if errors else None,
            "p95_center_error_px": float(np.percentile(errors, 95)) if errors else None,
            "mean_radius_error_px": float(np.mean(radius_errors)) if radius_errors else None,
            "sector_accuracy_matched": sector_hits / tp if tp else None,
            "median_detector_ms": float(np.median([r["detector_ms"] for r in samples])) if samples else None,
            "p95_detector_ms": float(np.percentile([r["detector_ms"] for r in samples], 95)) if samples else None}


def evaluate(annotations: Path, recordings_dir: Path) -> dict:
    dataset = json.loads(annotations.read_text(encoding="utf-8"))
    widths = (320, 640, 960, 1920)
    results = {name: [] for name in ("M1_original", *(f"M3_{w}" for w in widths))}
    if dataset.get("schema_version") != 1:
        raise ValueError("schema de anotações não suportado")
    for video in dataset["videos"]:
        name = video["file"]
        if Path(name).name != name or name in ("", ".", ".."):
            raise ValueError("anotação exige nome local de vídeo")
        path = recordings_dir / name
        if sha256(path) != video["sha256"]:
            raise ValueError(f"hash do vídeo diverge das anotações: {name}")
        labels = {}
        for label in video["annotations"]:
            index = label["frame"]
            center, radius = label["center_px"], label["radius_px"]
            if type(index) is not int or index < 0 or index in labels:
                raise ValueError("índice de anotação inválido ou repetido")
            if center is None:
                if radius is not None:
                    raise ValueError("ausência não admite raio")
            elif (len(center) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in center)
                  or not 0 <= center[0] < video["width"] or not 0 <= center[1] < video["height"]
                  or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius <= 0):
                raise ValueError("centro/raio anotado inválido")
            labels[index] = label
        camera = RecordedVideoCamera(path)
        profiles = {"M1_original": BallDetector(), **{
            f"M3_{width}": BallTracker(BallDetector(recorded=True, processing_width=width))
            for width in widths}}
        try:
            if camera.frame_count != video["frames"] or any(i >= camera.frame_count for i in labels):
                raise ValueError("quantidade de frames diverge das anotações")
            while (frame := camera.read()) is not None:
                if frame.sequence not in labels:
                    for detector in profiles.values():
                        if isinstance(detector, BallTracker):
                            detector.detect(frame)
                    continue
                if frame.image.shape[:2] != (video["height"], video["width"]):
                    raise ValueError("dimensões do vídeo divergem das anotações")
                label = labels[frame.sequence]
                for name, detector in profiles.items():
                    detector.detect(frame)  # aquecimento, fora da medição
                    durations = []
                    for _ in range(3):
                        start = perf_counter_ns()
                        observation = detector.detect(frame)
                        durations.append((perf_counter_ns() - start) / 1e6)
                    results[name].append({"file": path.name, "frame": frame.sequence,
                        "expected_center_px": label["center_px"], "expected_radius_px": label["radius_px"],
                        "detected_center_px": [observation.ball_x, observation.ball_y] if observation.ball_detected else None,
                        "detected_radius_px": observation.ball_radius, "width": video["width"],
                        "sector": image_sector(observation.ball_x, video["width"]),
                        "detector_ms": float(np.median(durations))})
        finally:
            camera.close()
    if not any(results.values()):
        raise ValueError("dataset vazio")
    return {"schema_version": 1, "versions": runtime_versions(),
            "annotations_sha256": sha256(annotations), "timing": "median of 3 calls after warmup; detector only",
            "evaluation": "exploratory, annotations and clips inspected during tuning; not independent holdout",
            "profiles": {name: {"summary": score(rows), "by_video": {
                video["file"]: score([r for r in rows if r["file"] == video["file"]]) for video in dataset["videos"]},
                "samples": rows} for name, rows in results.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=Path("datasets/m3/annotations.json"))
    parser.add_argument("--recordings-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise FileExistsError(args.output)
        report = evaluate(args.annotations, args.recordings_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
        print(json.dumps({name: value["summary"] for name, value in report["profiles"].items()}, indent=2))
        return 0
    except Exception as error:
        print(f"Avaliação M3 interrompida: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
