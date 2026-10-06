"""Contratos de vídeos, perfil real, setores, avaliação e saída M3."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock

import cv2
import numpy as np

from robosense_lab.cameras import CameraError, RecordedVideoCamera
from robosense_lab.evaluate_m3 import score
from robosense_lab.m3 import annotate, image_sector, main, process_video
from robosense_lab.models import Frame
from robosense_lab.perception import BallDetector, BallTracker


def image(center=None):
    pixels = np.full((360, 640, 3), (60, 100, 30), np.uint8)
    if center:
        cv2.circle(pixels, center, 35, (0, 140, 255), -1)
        cv2.circle(pixels, (center[0] - 5, center[1] - 8), 9, (220, 240, 255), -1)
    return pixels


def make_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20, (640, 360))
    if not writer.isOpened():
        raise RuntimeError("mp4v necessário para os testes M3")
    try:
        for center in ((100, 200), (230, 200), None):
            writer.write(image(center))
    finally:
        writer.release()


class RecordedCameraTests(unittest.TestCase):
    def test_real_decoder_metadata_eof_and_close(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "video.mp4"
            make_video(path)
            camera = RecordedVideoCamera(path)
            try:
                self.assertEqual(camera.frame_count, 3)
                frames = [camera.read() for _ in range(3)]
                self.assertEqual([f.sequence for f in frames], [0, 1, 2])
                self.assertEqual([f.timestamp_ns for f in frames], [0, 50_000_000, 100_000_000])
                self.assertEqual(frames[0].clock_domain, "recorded_video")
                self.assertIsNone(frames[0].received_timestamp_ns)
                self.assertIsNone(camera.read())
            finally:
                camera.close()
            camera.close()
            with self.assertRaises(CameraError):
                camera.read()

    def test_invalid_file_and_early_decode_failure_release(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "video.mp4"
            with self.assertRaises(CameraError):
                RecordedVideoCamera(path)
            make_video(path)
            camera = RecordedVideoCamera(path)
            camera._capture.release()
            with self.assertRaisesRegex(CameraError, "decodificação"):
                camera.read()
            camera.close()

    def test_invalid_metadata_closes_capture(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.mp4"
            path.touch()
            capture = MagicMock()
            capture.get.return_value = float("nan")
            with patch("robosense_lab.cameras.cv2.VideoCapture", return_value=capture):
                with self.assertRaises(CameraError):
                    RecordedVideoCamera(path)
            capture.release.assert_called_once()


class RecordedDetectorTests(unittest.TestCase):
    def test_border_measurement_does_not_lock_acquisition_to_small_radius(self):
        tracker = BallTracker(BallDetector(recorded=True))
        tracker.detect(Frame(image((5, 200)), "x", 0, 0, "v"))
        self.assertIsNone(tracker.previous)
        result = tracker.detect(Frame(image((70, 200)), "x", 1, 50_000_000, "v"))
        self.assertTrue(result.ball_detected)
        self.assertAlmostEqual(result.ball_x, 70, delta=3)

    def test_tracker_rejects_jump_never_predicts_and_expires_reference(self):
        tracker = BallTracker(BallDetector(recorded=True))
        result = tracker.detect(Frame(image((200, 200)), "x", 0, 0, "v"))
        self.assertTrue(result.ball_detected)
        pixels = image()
        cv2.circle(pixels, (500, 150), 15, (0, 140, 255), -1)
        missing = tracker.detect(Frame(pixels, "x", 1, 50_000_000, "v"))
        self.assertFalse(missing.ball_detected)
        self.assertIsNone(missing.ball_x)
        self.assertIsNone(missing.ball_radius)
        recovered = tracker.detect(Frame(image((210, 200)), "x", 2, 100_000_000, "v"))
        self.assertTrue(recovered.ball_detected)
        self.assertAlmostEqual(recovered.ball_x, 210, delta=3)
        far = tracker.detect(Frame(image((500, 200)), "x", 3, 3_000_000_000, "v"))
        self.assertTrue(far.ball_detected)

    def test_reflection_scaling_radius_and_input_preserved(self):
        pixels = image((500, 200))
        original = pixels.copy()
        frame = Frame(pixels, "recording", 2, 100, "recorded_video")
        result = BallDetector(recorded=True).detect(frame)
        self.assertTrue(result.ball_detected)
        self.assertAlmostEqual(result.ball_x, 500, delta=3)
        self.assertAlmostEqual(result.ball_y, 200, delta=3)
        self.assertAlmostEqual(result.ball_radius, 35, delta=4)
        self.assertEqual(result.timestamp_ns, 100)
        np.testing.assert_array_equal(pixels, original)
        canvas = annotate(pixels, result, 1)
        self.assertEqual(canvas.shape, pixels.shape)
        self.assertFalse(np.array_equal(canvas, pixels))
        np.testing.assert_array_equal(pixels, original)

    def test_no_reuse_of_old_detection_wrong_color_tiny_or_horizon(self):
        detector = BallDetector(recorded=True)
        self.assertTrue(detector.detect(Frame(image((200, 200)), "x", 0, 0, "v")).ball_detected)
        for pixels in (image(), np.zeros((360, 640, 3), np.uint8)):
            cv2.circle(pixels, (80, 20), 12, (0, 140, 255), -1)  # fora da ROI
            cv2.circle(pixels, (400, 200), 4, (0, 140, 255), -1)  # pequeno demais
            cv2.circle(pixels, (250, 200), 35, (255, 0, 0), -1)  # azul
            result = detector.detect(Frame(pixels, "x", 1, 1, "v"))
            self.assertFalse(result.ball_detected)
            self.assertIsNone(result.ball_radius)

    def test_sector_boundaries_and_invalid_coordinates(self):
        for x, expected in ((None, None), (0, "Left"), (99.9, "Left"), (100, "Front"),
                            (199.9, "Front"), (200, "Right"), (299, "Right")):
            self.assertEqual(image_sector(x, 300), expected)
        for x in (-1, 300, float("nan")):
            with self.assertRaises(ValueError):
                image_sector(x, 300)

    def test_configuration_and_radius_validation(self):
        for settings in ({"processing_width": 159}, {"processing_width": True},
                         {"roi_top": 1}, {"roi_top": float("nan")}):
            with self.assertRaises(ValueError):
                BallDetector(**settings)
        result = BallDetector(recorded=True).detect(Frame(image((200, 200)), "x", 0, 0, "v"))
        from dataclasses import replace
        for radius in (-1, 0, float("nan")):
            with self.assertRaises(ValueError):
                replace(result, ball_radius=radius)


class M3OutputTests(unittest.TestCase):
    def test_cli_export_logs_and_refuses_existing_output(self):
        with TemporaryDirectory() as tmp:
            path, output = Path(tmp) / "video.mp4", Path(tmp) / "result"
            make_video(path)
            arguments = [str(path), "--output-dir", str(output)]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(arguments), 0)
            events = [json.loads(line) for line in (output / "video.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["type"], "run_summary")
            rows = [e for e in events if e["type"] == "observation"]
            self.assertEqual([r["sector"] for r in rows], ["Left", "Front", None])
            self.assertEqual(len(json.loads((output / "summary.json").read_text())), 1)
            before = (output / "video.jsonl").read_bytes()
            with redirect_stderr(StringIO()):
                self.assertEqual(main(arguments), 1)
            self.assertEqual((output / "video.jsonl").read_bytes(), before)

    def test_camera_failure_logs_error_closes_and_no_success(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.mp4"
            path.touch()
            camera = MagicMock(fps=20, frame_count=3)
            camera.read.side_effect = CameraError("vídeo truncado")
            with patch("robosense_lab.m3.RecordedVideoCamera", return_value=camera):
                with self.assertRaises(CameraError):
                    process_video(path, Path(tmp), BallDetector(recorded=True))
            camera.close.assert_called_once()
            events = [json.loads(line) for line in (Path(tmp) / "source.jsonl").read_text().splitlines()]
            self.assertEqual([e["type"] for e in events], ["run_start", "run_error"])

    def test_spatial_scoring_counts_wrong_target_as_fp_and_fn(self):
        base = {"expected_center_px": [50, 50], "expected_radius_px": 20,
                "detected_center_px": [51, 50], "detected_radius_px": 21,
                "sector": "Left", "width": 300, "detector_ms": 1}
        rows = [base, {**base, "detected_center_px": [200, 50]},
                {**base, "expected_center_px": None},
                {**base, "detected_center_px": None},
                {**base, "expected_center_px": None, "detected_center_px": None}]
        result = score(rows)
        self.assertEqual((result["tp"], result["fp"], result["fn"], result["tn"]), (1, 2, 2, 1))
        self.assertEqual(result["mean_center_error_px"], 1)
        self.assertEqual(result["sector_accuracy_matched"], 1)
        self.assertIsNone(score([])["precision"])


if __name__ == "__main__":
    unittest.main()
