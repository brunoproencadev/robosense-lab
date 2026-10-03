"""Aquisição → validade temporal → percepção → avaliação → registro."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import math
from time import perf_counter_ns
from typing import TextIO

from .cameras import Camera, CameraError
from .models import BallObservation
from .perception import BallDetector
from .telemetry import write_event


@dataclass
class _Metrics:
    ground_truth_available: bool
    frames: int = 0
    frames_received: int = 0
    stale_frames: int = 0
    processing_ns: int = 0
    age_samples: int = 0
    age_sum_ns: int = 0
    max_age_ns: int = 0
    error_sum: float = 0.0
    counts: dict = field(default_factory=lambda: {
        "true_positives": 0, "false_positives": 0, "false_negatives": 0, "true_negatives": 0,
    })

    def evaluate(self, observation: BallObservation, expected: tuple[int, int] | None) -> float | None:
        if expected is None:
            self.counts["false_positives" if observation.ball_detected else "true_negatives"] += 1
        elif observation.ball_detected:
            self.counts["true_positives"] += 1
            error = math.hypot(observation.ball_x - expected[0], observation.ball_y - expected[1])
            self.error_sum += error
            return error
        else:
            self.counts["false_negatives"] += 1
        return None

    def summary(self) -> dict:
        result = {
            "frames": self.frames,
            "frames_received": self.frames_received,
            "stale_frames": self.stale_frames,
            "mean_processing_ms": self.processing_ns / self.frames / 1_000_000 if self.frames else None,
            "mean_frame_age_ms": self.age_sum_ns / self.age_samples / 1_000_000 if self.age_samples else None,
            "max_observed_frame_age_ms": self.max_age_ns / 1_000_000 if self.age_samples else None,
        }
        if self.ground_truth_available:
            tp, fp, fn = self.counts["true_positives"], self.counts["false_positives"], self.counts["false_negatives"]
            result.update(self.counts)
            result.update(
                precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                mean_localization_error_px=self.error_sum / tp if tp else None,
            )
        return result


def run_pipeline(
    camera: Camera,
    detector: BallDetector,
    stream: TextIO,
    *,
    expected_positions: Sequence[tuple[int, int] | None] | None = None,
    max_frame_age_ns: int | None = None,
    run_metadata: dict | None = None,
) -> dict:
    """Consome uma fonte finita e sempre a encerra, inclusive em falhas.

    Ground truth é usado somente na avaliação de frames processados.
    Frames antigos são rejeitados antes do detector; não são falsos negativos.
    O limite compara captura/entrega no domínio declarado pela fonte.
    """
    metrics = _Metrics(expected_positions is not None)
    try:
        if max_frame_age_ns is not None and (type(max_frame_age_ns) is not int or max_frame_age_ns < 0):
            raise ValueError("max_frame_age_ns deve ser um inteiro não negativo")
        write_event(stream, {
            "type": "run_start", "ground_truth_available": metrics.ground_truth_available,
            "max_frame_age_ns": max_frame_age_ns, "metadata": run_metadata or {},
        })
        while True:
            try:
                frame = camera.read()
            except CameraError as exc:
                write_event(stream, {
                    "type": "camera_error", "message": str(exc), "frames_processed": metrics.frames,
                    "partial_summary": metrics.summary(),
                })
                raise
            if frame is None:
                break
            if expected_positions is not None and (
                frame.sequence != metrics.frames_received or metrics.frames_received >= len(expected_positions)
            ):
                raise ValueError("ground truth não corresponde à sequência de frames")
            expected = expected_positions[metrics.frames_received] if expected_positions is not None else None
            age_ns = None
            if frame.received_timestamp_ns is not None:
                age_ns = frame.received_timestamp_ns - frame.timestamp_ns
                metrics.age_samples += 1
                metrics.age_sum_ns += age_ns
                metrics.max_age_ns = max(metrics.max_age_ns, age_ns)
            elif max_frame_age_ns is not None:
                raise ValueError("limite de idade exige timestamp de entrega no relógio da captura")
            metrics.frames_received += 1
            timing = {"received_timestamp_ns": frame.received_timestamp_ns, "frame_age_ns": age_ns}
            if max_frame_age_ns is not None and age_ns > max_frame_age_ns:
                metrics.stale_frames += 1
                event = {
                    "type": "frame_rejected", "reason": "stale_frame",
                    "camera_id": frame.camera_id, "sequence": frame.sequence,
                    "timestamp_ns": frame.timestamp_ns, "clock_domain": frame.clock_domain,
                    "max_frame_age_ns": max_frame_age_ns, **timing,
                }
                if metrics.ground_truth_available:
                    event["expected_center_px"] = expected
                write_event(stream, event)
                continue
            started = perf_counter_ns()
            observation = detector.detect(frame)
            elapsed_ns = perf_counter_ns() - started
            metrics.processing_ns += elapsed_ns
            event = {"type": "observation", **asdict(observation), "processing_ns": elapsed_ns, **timing}
            if metrics.ground_truth_available:
                event["expected_center_px"] = expected
                event["localization_error_px"] = metrics.evaluate(observation, expected)
            write_event(stream, event)
            metrics.frames += 1
        if expected_positions is not None and metrics.frames_received != len(expected_positions):
            raise ValueError("fonte terminou antes do fim do ground truth")
        summary = {"type": "run_summary", **metrics.summary()}
        write_event(stream, summary)
        return summary
    finally:
        camera.close()
