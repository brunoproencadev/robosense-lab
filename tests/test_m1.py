"""Provas do pipeline M1 usando imagens e fontes controladas."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import cv2
import numpy as np

from robosense_lab.__main__ import main
from robosense_lab.cameras import CameraError, SimulatedCamera
from robosense_lab.models import BallObservation, Frame
from robosense_lab.perception import BallDetector
from robosense_lab.pipeline import run_pipeline
from robosense_lab.telemetry import write_event


def make_frame(image: np.ndarray) -> Frame:
    return Frame(image, "test-camera", 0, 123, "test-clock")


class SequenceCamera:
    """Segunda fonte somente de teste: prova a independência da simulação."""

    def __init__(self, frames=(), fail=False):
        self.frames = iter(frames)
        self.fail = fail
        self.closed = False

    def read(self):
        frame = next(self.frames, None)
        if frame is None and self.fail:
            raise CameraError("desconexão simulada")
        return frame

    def close(self):
        self.closed = True


class CameraTests(unittest.TestCase):
    def test_deterministic_images_metadata_and_end(self):
        first, second = SimulatedCamera(6), SimulatedCamera(6)
        for i in range(6):
            a, b = first.read(), second.read()
            np.testing.assert_array_equal(a.image, b.image)
            self.assertEqual(a.sequence, i)
            self.assertEqual(a.timestamp_ns, i * 1_000_000_000 // 30)
            self.assertEqual(a.clock_domain, "simulation")
        self.assertIsNone(first.read())
        self.assertIsNone(first.read())
        first.close()
        first.close()
        with self.assertRaises(CameraError):
            first.read()

    def test_invalid_frame_count(self):
        for count in (0, -1, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                SimulatedCamera(count)


class ContractTests(unittest.TestCase):
    def test_invalid_images_rejected(self):
        for image in ([], np.zeros((4, 4), np.uint8), np.zeros((4, 4, 3)), np.zeros((0, 4, 3), np.uint8)):
            with self.subTest(shape=getattr(image, "shape", None)), self.assertRaises(ValueError):
                make_frame(image)

    def test_invalid_metadata_rejected(self):
        valid = make_frame(np.zeros((4, 4, 3), np.uint8))
        for changes in ({"sequence": -1}, {"sequence": True}, {"timestamp_ns": -1}, {"camera_id": ""}, {"clock_domain": " "}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(valid, **changes)

    def test_absence_and_finite_coordinate_invariants(self):
        absent = BallObservation("test", 0, 0, "test", False, None, None, 0.0)
        for changes in (
            {"ball_x": 0.0}, {"confidence": 0.2}, {"confidence": float("nan")},
            {"confidence": 1.1}, {"ball_detected": True}, {"ball_detected": 1},
            {"ball_detected": True, "ball_x": float("inf"), "ball_y": 3.0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(absent, **changes)
        present = replace(absent, ball_detected=True, ball_x=0.0, ball_y=0.0, confidence=0.8)
        self.assertTrue(present.ball_detected)


class DetectorTests(unittest.TestCase):
    def test_detects_independent_circle_and_preserves_metadata(self):
        image = np.zeros((160, 200, 3), np.uint8)
        cv2.circle(image, (137, 81), 15, (0, 140, 255), -1)
        original = image.copy()
        frame = make_frame(image)
        result = BallDetector().detect(frame)
        self.assertTrue(result.ball_detected)
        self.assertAlmostEqual(result.ball_x, 137, delta=0.5)
        self.assertAlmostEqual(result.ball_y, 81, delta=0.5)
        self.assertGreater(result.confidence, 0.65)
        self.assertLessEqual(result.confidence, 1)
        self.assertEqual((result.camera_id, result.sequence, result.timestamp_ns, result.clock_domain), ("test-camera", 0, 123, "test-clock"))
        np.testing.assert_array_equal(image, original)

    def test_absent_wrong_color_tiny_and_elongated_targets(self):
        empty = np.zeros((120, 160, 3), np.uint8)
        blue, tiny, elongated = empty.copy(), empty.copy(), empty.copy()
        cv2.circle(blue, (50, 50), 12, (255, 0, 0), -1)
        cv2.circle(tiny, (50, 50), 2, (0, 140, 255), -1)
        cv2.rectangle(elongated, (10, 10), (140, 15), (0, 140, 255), -1)
        for name, image in (("empty", empty), ("blue", blue), ("tiny", tiny), ("elongated", elongated)):
            with self.subTest(name=name):
                result = BallDetector().detect(make_frame(image))
                self.assertFalse(result.ball_detected)
                self.assertIsNone(result.ball_x)
                self.assertIsNone(result.ball_y)
                self.assertEqual(result.confidence, 0)

    def test_largest_valid_candidate(self):
        image = np.zeros((160, 200, 3), np.uint8)
        cv2.circle(image, (40, 40), 8, (0, 140, 255), -1)
        cv2.circle(image, (130, 90), 15, (0, 140, 255), -1)
        result = BallDetector().detect(make_frame(image))
        self.assertEqual((result.ball_x, result.ball_y), (130.0, 90.0))


class PipelineTests(unittest.TestCase):
    def test_full_simulation_and_jsonl(self):
        camera, stream = SimulatedCamera(60), StringIO()
        summary = run_pipeline(camera, BallDetector(), stream, expected_positions=camera.expected_positions)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(len(events), 62)
        self.assertTrue(all(e["schema_version"] == 1 for e in events))
        self.assertEqual(events[0]["type"], "run_start")
        self.assertEqual(events[-1]["type"], "run_summary")
        self.assertEqual(summary["frames"], 60)
        self.assertEqual(summary["true_positives"], 48)
        self.assertEqual(summary["true_negatives"], 12)
        self.assertEqual(summary["false_positives"], 0)
        self.assertEqual(summary["false_negatives"], 0)
        self.assertEqual(summary["mean_localization_error_px"], 0.0)
        self.assertGreaterEqual(summary["mean_processing_ms"], 0)
        with self.assertRaises(CameraError):
            camera.read()

    def test_false_positives_false_negatives_and_error_are_measured(self):
        blank = np.zeros((120, 160, 3), np.uint8)
        ball = blank.copy()
        cv2.circle(ball, (50, 50), 12, (0, 140, 255), -1)
        frames = [replace(make_frame(image), sequence=i) for i, image in enumerate((ball, blank, ball, blank))]
        camera = SequenceCamera(frames)
        summary = run_pipeline(camera, BallDetector(), StringIO(), expected_positions=[None, (50, 50), (53, 54), None])
        for key in ("true_positives", "false_positives", "false_negatives", "true_negatives"):
            self.assertEqual(summary[key], 1)
        self.assertEqual(summary["precision"], 0.5)
        self.assertEqual(summary["recall"], 0.5)
        self.assertEqual(summary["mean_localization_error_px"], 5.0)
        self.assertTrue(camera.closed)

    def test_source_failure_is_not_ball_absence_or_success(self):
        camera, stream = SequenceCamera([make_frame(np.zeros((20, 20, 3), np.uint8))], fail=True), StringIO()
        with self.assertRaisesRegex(CameraError, "desconexão"):
            run_pipeline(camera, BallDetector(), stream)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual([e["type"] for e in events], ["run_start", "observation", "camera_error"])
        self.assertEqual(events[-1]["frames_processed"], 1)
        self.assertTrue(camera.closed)

    def test_empty_source_has_no_invented_metrics(self):
        camera = SequenceCamera()
        summary = run_pipeline(camera, BallDetector(), StringIO(), expected_positions=[])
        self.assertEqual(summary["frames"], 0)
        for key in ("precision", "recall", "mean_localization_error_px", "mean_processing_ms"):
            self.assertIsNone(summary[key])
        self.assertTrue(camera.closed)

    def test_source_without_ground_truth(self):
        summary = run_pipeline(SequenceCamera(), BallDetector(), StringIO())
        self.assertNotIn("precision", summary)
        self.assertNotIn("true_positives", summary)

    def test_invalid_ground_truth_alignment_closes_source(self):
        frame = make_frame(np.zeros((20, 20, 3), np.uint8))
        for frames, expected in (([frame], []), ([], [None]), ([replace(frame, sequence=1)], [None])):
            camera = SequenceCamera(frames)
            with self.subTest(frames=len(frames), expected=len(expected)), self.assertRaises(ValueError):
                run_pipeline(camera, BallDetector(), StringIO(), expected_positions=expected)
            self.assertTrue(camera.closed)

    def test_write_failure_closes_source(self):
        class BrokenStream(StringIO):
            def write(self, value):
                raise OSError("disco indisponível")

        camera = SequenceCamera()
        with self.assertRaises(OSError):
            run_pipeline(camera, BallDetector(), BrokenStream())
        self.assertTrue(camera.closed)

    def test_detector_failure_closes_source(self):
        class BrokenDetector:
            def detect(self, frame):
                raise RuntimeError("falha no detector")

        camera = SequenceCamera([make_frame(np.zeros((20, 20, 3), np.uint8))])
        stream = StringIO()
        with self.assertRaises(RuntimeError):
            run_pipeline(camera, BrokenDetector(), stream)
        self.assertTrue(camera.closed)
        self.assertNotIn("run_summary", stream.getvalue())

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            write_event(StringIO(), {"value": float("nan")})


class CLITests(unittest.TestCase):
    def test_cli_creates_log_and_refuses_overwrite(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            target = Path(directory) / "nested" / "run.jsonl"
            args = ["--frames", "5", "--output", str(target)]
            self.assertEqual(main(args), 0)
            original = target.read_bytes()
            self.assertEqual(len(original.splitlines()), 7)
            self.assertEqual(main(args), 1)
            self.assertEqual(target.read_bytes(), original)

    def test_cli_rejects_invalid_frame_counts(self):
        for value in ("0", "-1", "abc", "1.5"):
            with self.subTest(value=value), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                main(["--frames", value])
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
