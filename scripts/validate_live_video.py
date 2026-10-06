"""Reproduz o ensaio doméstico usando pixels, crop e rótulos separados."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter_ns

import cv2
import numpy as np

from robosense_lab.cameras import RecordedVideoCamera
from robosense_lab.evaluate_m3 import score
from robosense_lab.m3 import image_sector, sha256
from robosense_lab.models import Frame
from robosense_lab.perception import BallDetector, BallTracker, LIVE_PROFILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--annotations", type=Path, default=Path("datasets/live/home-20261006.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.annotations.read_text(encoding="utf-8"))
    if dataset["schema_version"] != 1 or sha256(args.video) != dataset["sha256"]:
        raise ValueError("Vídeo/schema diverge do dataset")
    x, y, w, h = dataset["crop_xywh"]
    width, height = dataset["source_size"]
    start, stop = dataset["frame_range"]
    if (any(type(v) is not int for v in (x, y, w, h, start, stop))
            or not (0 <= x < x + w <= width and 0 <= y < y + h <= height)
            or w % 2 or h % 2 or not 0 <= start < stop <= dataset["frames"]):
        raise ValueError("Crop/intervalo inválido")
    labels = {row["frame"]: row for row in dataset["annotations"]}
    if len(labels) != len(dataset["annotations"]) or any(not start <= i < stop for i in labels):
        raise ValueError("Rótulos repetidos ou fora do intervalo")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with ExitStack() as resources:
        camera = RecordedVideoCamera(args.video)
        resources.callback(camera.close)
        if camera.frame_count != dataset["frames"]:
            raise ValueError("Quantidade de frames diverge")
        writer = cv2.VideoWriter(str(args.output_dir / "live-demo.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                 dataset["fps"], (w, h))
        resources.callback(writer.release)
        if not writer.isOpened():
            raise RuntimeError("Não foi possível abrir exportação MP4")
        log = resources.enter_context((args.output_dir / "observations.jsonl").open("x", encoding="utf-8"))
        tracker = BallTracker(BallDetector(recorded=True, live=True, roi_top=0), max_reference_seconds=.3)
        samples, durations = [], []
        count = detected = decoded = 0
        while (source := camera.read()) is not None:
            decoded += 1
            if source.image.shape[:2] != (height, width):
                raise ValueError("Dimensões divergem")
            if not start <= source.sequence < stop:
                continue
            pixels = source.image[y:y + h, x:x + w]
            frame = Frame(pixels, source.camera_id, source.sequence, source.timestamp_ns, source.clock_domain)
            began = perf_counter_ns()
            observation = tracker.detect(frame)
            milliseconds = (perf_counter_ns() - began) / 1e6
            durations.append(milliseconds)
            count += 1
            detected += observation.ball_detected
            log.write(json.dumps({**asdict(observation), "detector_ms": milliseconds}) + "\n")
            if frame.sequence in labels:
                label = labels[frame.sequence]
                samples.append({"frame": frame.sequence, "expected_center_px": label["center_px"],
                                "expected_radius_px": label["radius_px"],
                                "detected_center_px": [observation.ball_x, observation.ball_y] if observation.ball_detected else None,
                                "detected_radius_px": observation.ball_radius, "width": w,
                                "sector": image_sector(observation.ball_x, w), "detector_ms": milliseconds})
            canvas = pixels.copy()
            if observation.ball_detected:
                cv2.circle(canvas, (round(observation.ball_x), round(observation.ball_y)),
                           round(observation.ball_radius), (255, 150, 0), 2)
            cv2.rectangle(canvas, (0, h - 28), (w, h), (20, 20, 20), -1)
            cv2.putText(canvas, f"{LIVE_PROFILE} AZUL | {'BALL' if observation.ball_detected else 'NO BALL'} | {milliseconds:.2f} ms | {frame.sequence}",
                        (8, h - 9), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 200, 100), 1)
            writer.write(canvas)
        if len(samples) != len(labels):
            raise ValueError("Rótulos não foram todos avaliados")
        report = {"profile": LIVE_PROFILE, "sha256": dataset["sha256"], "crop_xywh": dataset["crop_xywh"],
                  "decoded_frames": decoded, "processed_frames": count, "frames_with_detection": detected,
                  "all_frames_median_detector_ms": float(np.median(durations)),
                  "all_frames_p95_detector_ms": float(np.percentile(durations, 95)),
                  "summary": score(samples), "samples": samples,
                  "limitations": "screen recording with overlays; approximate tuning labels; no independent holdout or Pi validation"}
        with (args.output_dir / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(json.dumps({key: value for key, value in report.items() if key != "samples"}))


if __name__ == "__main__":
    main()
