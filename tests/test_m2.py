"""Provas de perturbações, dados antigos e comparação reproduzível do M2."""

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
from robosense_lab.experiments import main as experiment_main, run_experiments
from robosense_lab.perception import BallDetector
from robosense_lab.pipeline import run_pipeline


class ControlledSource:
    def __init__(self, frames, *, fail=False):
        self.frames = iter(frames)
        self.fail = fail
        self.closed = False

    def read(self):
        frame = next(self.frames, None)
        if frame is None and self.fail:
            raise CameraError("fonte desconectada")
        return frame

    def close(self):
        self.closed = True


class SpyDetector:
    def __init__(self):
        self.sequences = []

    def detect(self, frame):
        self.sequences.append(frame.sequence)
        return BallDetector().detect(frame)


class SimulationTests(unittest.TestCase):
    def test_default_pixels_match_m1_baseline(self):
        camera = SimulatedCamera(6)
        for i in range(6):
            frame = camera.read()
            expected = np.full((240, 320, 3), (0, 100, 0), dtype=np.uint8)
            if i % 5 != 4:
                cv2.circle(expected, (24 + (i * 7) % 272, 24 + (i * 5) % 192), 12, (0, 140, 255), -1)
            np.testing.assert_array_equal(frame.image, expected)
            self.assertEqual(frame.received_timestamp_ns, frame.timestamp_ns)
        camera.close()

    def test_noise_reproducible_by_seed_without_modifying_ground_truth(self):
        first = SimulatedCamera(5, noise_std=45, seed=7)
        second = SimulatedCamera(5, noise_std=45, seed=7)
        third = SimulatedCamera(5, noise_std=45, seed=8)
        clean = SimulatedCamera(5)
        self.assertEqual(first.expected_positions, clean.expected_positions)
        for _ in range(5):
            a, b, c, d = first.read(), second.read(), third.read(), clean.read()
            np.testing.assert_array_equal(a.image, b.image)
            self.assertFalse(np.array_equal(a.image, c.image))
            self.assertFalse(np.array_equal(a.image, d.image))
            self.assertEqual(a.image.dtype, np.uint8)
        for camera in (first, second, third, clean):
            camera.close()

    def test_occlusion_changes_pixels_but_keeps_physical_presence(self):
        clean, partial, full = SimulatedCamera(5), SimulatedCamera(5, occlusion_fraction=0.5), SimulatedCamera(5, occlusion_fraction=1)
        a, b, c = clean.read(), partial.read(), full.read()
        orange_a = np.count_nonzero(a.image[:, :, 2] == 255)
        orange_b = np.count_nonzero(b.image[:, :, 2] == 255)
        self.assertGreater(orange_b, 0)
        self.assertLess(orange_b, orange_a)
        np.testing.assert_array_equal(c.image, np.full((240, 320, 3), (0, 100, 0), np.uint8))
        self.assertEqual(full.expected_positions, clean.expected_positions)
        self.assertIsNotNone(full.expected_positions[0])
        self.assertFalse(BallDetector().detect(c).ball_detected)
        for camera in (clean, partial, full):
            camera.close()

    def test_virtual_delay_preserves_capture_and_pixels(self):
        camera = SimulatedCamera(5, delay_ns=200_000_000)
        clean = SimulatedCamera(5)
        for _ in range(5):
            a, b = camera.read(), clean.read()
            self.assertEqual(a.timestamp_ns, b.timestamp_ns)
            self.assertEqual(a.received_timestamp_ns - a.timestamp_ns, 200_000_000)
            self.assertEqual(a.clock_domain, "simulation")
            np.testing.assert_array_equal(a.image, b.image)
        camera.close()
        clean.close()

    def test_loss_is_terminal_not_eof_or_empty_image(self):
        camera = SimulatedCamera(5, loss_at_frame=2)
        self.assertEqual(camera.read().sequence, 0)
        self.assertEqual(camera.read().sequence, 1)
        for _ in range(2):
            with self.assertRaisesRegex(CameraError, "frame 2"):
                camera.read()
        camera.close()
        with self.assertRaisesRegex(CameraError, "encerrada"):
            camera.read()

    def test_invalid_parameters(self):
        for kwargs in (
            {"noise_std": -1}, {"noise_std": 256}, {"noise_std": float("nan")},
            {"noise_std": float("inf")}, {"seed": -1}, {"seed": True},
            {"occlusion_fraction": -0.1}, {"occlusion_fraction": 1.1}, {"occlusion_fraction": float("nan")},
            {"loss_at_frame": -1}, {"loss_at_frame": 5}, {"loss_at_frame": True},
            {"delay_ns": -1}, {"delay_ns": 0.5}, {"delay_ns": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SimulatedCamera(5, **kwargs)

    def test_configuration_copy_cannot_change_scenario(self):
        camera = SimulatedCamera(5)
        camera.configuration["loss_at_frame"] = 0
        self.assertIsNotNone(camera.read())
        camera.close()


class FreshnessTests(unittest.TestCase):
    def make_frames(self):
        camera = SimulatedCamera(5)
        frames = [camera.read() for _ in range(5)]
        camera.close()
        return frames, camera.expected_positions

    def test_frame_rejects_delivery_before_capture_and_invalid_types(self):
        frame = SimulatedCamera(1).read()
        for value in (-1, True, 0.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(frame, received_timestamp_ns=value)

    def test_mixed_ages_boundary_and_alignment_skip_detector(self):
        frames, expected = self.make_frames()
        ages = (0, 100_000_000, 100_000_001, 200_000_000, 0)
        frames = [replace(frame, received_timestamp_ns=frame.timestamp_ns + age) for frame, age in zip(frames, ages)]
        source, detector, stream = ControlledSource(frames), SpyDetector(), StringIO()
        summary = run_pipeline(source, detector, stream, expected_positions=expected, max_frame_age_ns=100_000_000)
        self.assertEqual(detector.sequences, [0, 1, 4])
        self.assertEqual(summary["frames_received"], 5)
        self.assertEqual(summary["frames"], 3)
        self.assertEqual(summary["stale_frames"], 2)
        self.assertEqual(summary["true_positives"], 2)
        self.assertEqual(summary["true_negatives"], 1)
        self.assertEqual(summary["false_negatives"], 0)
        self.assertEqual(summary["max_observed_frame_age_ms"], 200)
        self.assertAlmostEqual(summary["mean_frame_age_ms"], sum(ages) / 5 / 1_000_000)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        rejected = [event for event in events if event["type"] == "frame_rejected"]
        self.assertEqual([event["sequence"] for event in rejected], [2, 3])
        self.assertTrue(all("ball_detected" not in event for event in rejected))
        self.assertTrue(source.closed)

    def test_all_stale_has_no_detection_metrics_or_processing_time(self):
        camera, detector = SimulatedCamera(5, delay_ns=200_000_000), SpyDetector()
        summary = run_pipeline(camera, detector, StringIO(), expected_positions=camera.expected_positions, max_frame_age_ns=100_000_000)
        self.assertEqual(detector.sequences, [])
        self.assertEqual(summary["frames"], 0)
        self.assertEqual(summary["stale_frames"], 5)
        self.assertEqual(summary["false_negatives"], 0)
        for key in ("precision", "recall", "mean_localization_error_px", "mean_processing_ms"):
            self.assertIsNone(summary[key])

    def test_limit_requires_delivery_timestamp_but_m1_callers_remain_valid(self):
        frames, _ = self.make_frames()
        unknown = replace(frames[0], received_timestamp_ns=None)
        source = ControlledSource([unknown])
        with self.assertRaisesRegex(ValueError, "timestamp de entrega"):
            run_pipeline(source, BallDetector(), StringIO(), max_frame_age_ns=100)
        self.assertTrue(source.closed)
        result = run_pipeline(ControlledSource([unknown]), BallDetector(), StringIO())
        self.assertEqual(result["frames"], 1)
        self.assertIsNone(result["mean_frame_age_ms"])

    def test_invalid_limit_closes_source(self):
        for limit in (-1, True, 1.5):
            source = ControlledSource([])
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                run_pipeline(source, BallDetector(), StringIO(), max_frame_age_ns=limit)
            self.assertTrue(source.closed)

    def test_loss_records_only_observed_partial_metrics(self):
        camera, stream = SimulatedCamera(10, loss_at_frame=5), StringIO()
        with self.assertRaises(CameraError):
            run_pipeline(camera, BallDetector(), stream, expected_positions=camera.expected_positions)
        events = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertNotIn("run_summary", [event["type"] for event in events])
        self.assertEqual(events[-1]["type"], "camera_error")
        partial = events[-1]["partial_summary"]
        self.assertEqual(partial["frames"], 5)
        self.assertEqual(partial["true_positives"], 4)
        self.assertEqual(partial["true_negatives"], 1)
        self.assertEqual(partial["false_negatives"], 0)
        with self.assertRaises(CameraError):
            camera.read()


class ExperimentTests(unittest.TestCase):
    def test_suite_reports_partial_loss_and_stale_without_inventing_success(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "m2"
            report = run_experiments(output, frame_count=10, seed=7)
            self.assertEqual(len(report["results"]), 7)
            by_name = {result["scenario"]: result for result in report["results"]}
            self.assertEqual(by_name["baseline"]["metrics"]["true_positives"], 8)
            self.assertEqual(by_name["full_occlusion"]["metrics"]["false_negatives"], 8)
            self.assertEqual(by_name["camera_loss"]["status"], "camera_error")
            self.assertEqual(by_name["camera_loss"]["metrics"]["frames"], 5)
            self.assertEqual(by_name["delay_200ms"]["metrics"]["stale_frames"], 10)
            self.assertIsNone(by_name["delay_200ms"]["metrics"]["recall"])
            for result in report["results"]:
                lines = [json.loads(line) for line in (output / result["log"]).read_text(encoding="utf-8").splitlines()]
                self.assertEqual(lines[0]["metadata"]["simulation"], result["simulation"])
                self.assertEqual(lines[0]["metadata"]["runtime"], report["runtime"])
                self.assertEqual(lines[0]["metadata"]["simulation"]["seed"], 7)
                self.assertEqual(lines[-1]["type"], "camera_error" if result["scenario"] == "camera_loss" else "run_summary")
            self.assertEqual(json.loads((output / "summary.json").read_text(encoding="utf-8")), report)
            saved = (output / "summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run_experiments(output, frame_count=10)
            self.assertEqual((output / "summary.json").read_bytes(), saved)

    def test_suite_reproducibility_excluding_measured_processing_duration(self):
        with TemporaryDirectory() as directory:
            a = run_experiments(Path(directory) / "a", frame_count=5, seed=9)
            b = run_experiments(Path(directory) / "b", frame_count=5, seed=9)
            for left, right in zip(a["results"], b["results"]):
                left["metrics"].pop("mean_processing_ms")
                right["metrics"].pop("mean_processing_ms")
                self.assertEqual(left, right)

    def test_cli_parameters_metadata_and_stale_events(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            path = Path(directory) / "delay.jsonl"
            self.assertEqual(main(["--frames", "5", "--delay-ms", "200", "--output", str(path)]), 0)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[0]["metadata"]["simulation"]["delay_ns"], 200_000_000)
            self.assertEqual(events[-1]["stale_frames"], 5)
            loss_path = Path(directory) / "loss.jsonl"
            self.assertEqual(main(["--frames", "5", "--loss-at-frame", "2", "--output", str(loss_path)]), 1)
            self.assertEqual(json.loads(loss_path.read_text(encoding="utf-8").splitlines()[-1])["type"], "camera_error")

    def test_cli_invalid_settings_and_loss_outside_sequence(self):
        for args in (
            ["--noise-std", "nan"], ["--noise-std", "256"], ["--occlusion", "inf"],
            ["--occlusion", "1.1"], ["--delay-ms", "-1"], ["--seed", "-1"],
            ["--frames", "5", "--loss-at-frame", "5"], ["--max-frame-age-ms", "-1"],
        ):
            with self.subTest(args=args), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                main(args)
            self.assertEqual(caught.exception.code, 2)

    def test_experiment_cli_success_and_existing_directory(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            args = ["--frames", "5", "--output-dir", str(Path(directory) / "suite")]
            self.assertEqual(experiment_main(args), 0)
            self.assertEqual(experiment_main(args), 1)


if __name__ == "__main__":
    unittest.main()
