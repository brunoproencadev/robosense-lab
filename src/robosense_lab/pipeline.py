"""Aquisição → percepção → avaliação opcional → registro."""

from collections.abc import Sequence
from dataclasses import asdict
import math
from time import perf_counter_ns
from typing import TextIO

from .cameras import Camera, CameraError
from .perception import BallDetector
from .telemetry import write_event


def run_pipeline(
    camera: Camera,
    detector: BallDetector,
    stream: TextIO,
    *,
    expected_positions: Sequence[tuple[int, int] | None] | None = None,
) -> dict:
    """Consome uma fonte finita e sempre a encerra, inclusive em falhas.

    Ground truth é exclusivo da avaliação e nunca entra no detector.
    A sequência deve começar em zero e ser contígua quando há ground truth.
    """
    frames = 0
    processing_ns = 0
    counts = {"true_positives": 0, "false_positives": 0, "false_negatives": 0, "true_negatives": 0}
    error_sum = 0.0
    try:
        write_event(stream, {"type": "run_start", "ground_truth_available": expected_positions is not None})
        while True:
            try:
                frame = camera.read()
            except CameraError as exc:
                write_event(stream, {"type": "camera_error", "message": str(exc), "frames_processed": frames})
                raise
            if frame is None:
                break
            if expected_positions is not None and (
                frame.sequence != frames or frames >= len(expected_positions)
            ):
                raise ValueError("ground truth não corresponde à sequência de frames")
            started = perf_counter_ns()
            observation = detector.detect(frame)
            elapsed_ns = perf_counter_ns() - started
            processing_ns += elapsed_ns
            event = {"type": "observation", **asdict(observation), "processing_ns": elapsed_ns}
            if expected_positions is not None:
                expected = expected_positions[frames]
                event["expected_center_px"] = expected
                error = None
                if expected is None:
                    counts["false_positives" if observation.ball_detected else "true_negatives"] += 1
                elif observation.ball_detected:
                    counts["true_positives"] += 1
                    error = math.hypot(observation.ball_x - expected[0], observation.ball_y - expected[1])
                    error_sum += error
                else:
                    counts["false_negatives"] += 1
                event["localization_error_px"] = error
            write_event(stream, event)
            frames += 1
        if expected_positions is not None and frames != len(expected_positions):
            raise ValueError("fonte terminou antes do fim do ground truth")
        summary = {
            "type": "run_summary",
            "frames": frames,
            "mean_processing_ms": processing_ns / frames / 1_000_000 if frames else None,
        }
        if expected_positions is not None:
            tp, fp, fn = counts["true_positives"], counts["false_positives"], counts["false_negatives"]
            summary.update(counts)
            summary.update(
                precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                mean_localization_error_px=error_sum / tp if tp else None,
            )
        write_event(stream, summary)
        return summary
    finally:
        camera.close()
