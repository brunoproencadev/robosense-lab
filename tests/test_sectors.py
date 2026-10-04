"""Setores, indisponibilidade e PySerial real em loopback."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import serial

from robosense_lab.cameras import CameraError, SimulatedCamera
from robosense_lab.communication import SerialOutput
from robosense_lab.sectors import main, make_simulated_cameras, run_sector_pipeline


class Frames:
    def __init__(self, frames, fail=False):
        self.frames = iter(frames)
        self.fail = fail
        self.closed = False

    def read(self):
        frame = next(self.frames, None)
        if frame is None and self.fail:
            raise CameraError("desconexão de teste")
        return frame

    def close(self):
        self.closed = True


class SectorTests(unittest.TestCase):
    def test_four_sectors_no_ball_and_overlap_are_measured_from_pixels(self):
        cameras = make_simulated_cameras(6)
        log, terminal = StringIO(), StringIO()
        summary = run_sector_pipeline(cameras, log, terminal)
        self.assertEqual(terminal.getvalue().splitlines(), ["F", "D", "E", "A", "SEM_BOLA", "F D"])
        events = [json.loads(line) for line in log.getvalue().splitlines()]
        observations = events[1:-1]
        self.assertEqual(summary["cycles"], 6)
        self.assertEqual(summary["detected_cycles"], 5)
        self.assertEqual(summary["no_ball_cycles"], 1)
        self.assertEqual(observations[0]["cameras"]["F"]["camera_id"], "simulated-F")
        self.assertEqual(observations[4]["sectors"], [])
        self.assertEqual(observations[5]["sectors"], ["F", "D"])
        self.assertTrue(all(len(event["cameras"]) == 4 for event in observations))
        for camera in cameras.values():
            with self.assertRaises(CameraError):
                camera.read()

    def test_two_camera_subset_declares_local_coverage(self):
        log, terminal = StringIO(), StringIO()
        run_sector_pipeline(make_simulated_cameras(6, "DF"), log, terminal)
        self.assertEqual(terminal.getvalue().splitlines(), ["F", "D", "SEM_BOLA", "SEM_BOLA", "SEM_BOLA", "F D"])
        events = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertTrue(all(event["observed_sectors"] == ["F", "D"] for event in events if "observed_sectors" in event))

    def test_camera_identity_and_visibility_validation(self):
        camera = SimulatedCamera(3, camera_id="front", visible_frames=[1])
        first, second = camera.read(), camera.read()
        self.assertEqual(second.camera_id, "front")
        self.assertIsNone(camera.expected_positions[0])
        self.assertIsNotNone(camera.expected_positions[1])
        camera.configuration["visible_frames"].append(2)
        self.assertEqual(camera.configuration["visible_frames"], [1])
        self.assertFalse(np.array_equal(first.image, second.image))
        camera.close()
        for kwargs in ({"camera_id": " "}, {"visible_frames": [-1]}, {"visible_frames": [1, True]}, {"visible_frames": [3]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SimulatedCamera(3, **kwargs)

    def test_stale_camera_makes_snapshot_unavailable_not_no_ball(self):
        f = SimulatedCamera(1, camera_id="front").read()
        d = SimulatedCamera(1, camera_id="right").read()
        cameras = {"F": Frames([f]), "D": Frames([replace(d, received_timestamp_ns=200_000_000)])}
        log, terminal = StringIO(), StringIO()
        summary = run_sector_pipeline(cameras, log, terminal)
        self.assertEqual(terminal.getvalue().strip(), "SEM_DADOS")
        self.assertEqual(summary["unavailable_cycles"], 1)
        event = json.loads(log.getvalue().splitlines()[1])
        self.assertEqual(event["status"], "unavailable")
        self.assertEqual(event["sectors"], [])
        self.assertEqual(event["cameras"]["D"]["type"], "frame_rejected")
        self.assertTrue(all(camera.closed for camera in cameras.values()))

    def test_loss_and_mixed_eof_abort_without_repeating_direction(self):
        frame = SimulatedCamera(1).read()
        for cameras in ({"F": Frames([frame], fail=True), "D": Frames([frame])}, {"F": Frames([frame]), "D": Frames([])}):
            log, terminal = StringIO(), StringIO()
            with self.subTest(), self.assertRaises(CameraError):
                run_sector_pipeline(cameras, log, terminal)
            self.assertNotIn("sector_run_summary", log.getvalue())
            self.assertEqual(json.loads(log.getvalue().splitlines()[-1])["type"], "camera_error")
            self.assertTrue(all(camera.closed for camera in cameras.values()))
            self.assertLessEqual(len(terminal.getvalue().splitlines()), 1)

    def test_different_clocks_or_sequences_are_not_fused(self):
        frame = SimulatedCamera(1).read()
        for other in (replace(frame, clock_domain="another"), replace(frame, sequence=1), replace(frame, timestamp_ns=1, received_timestamp_ns=1)):
            cameras = {"F": Frames([frame]), "D": Frames([other])}
            with self.subTest(), self.assertRaises(ValueError):
                run_sector_pipeline(cameras, StringIO(), StringIO())
            self.assertTrue(all(camera.closed for camera in cameras.values()))

    def test_invalid_mapping_and_age_close_sources(self):
        for kwargs in ({"cameras": {"X": Frames([])}}, {"cameras": {"F": Frames([])}, "max_frame_age_ns": -1}):
            source = next(iter(kwargs["cameras"].values()))
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_sector_pipeline(stream=StringIO(), terminal=StringIO(), **kwargs)
            self.assertTrue(source.closed)

    def test_serial_failure_is_logged_and_aborts(self):
        class BrokenSerial:
            def send(self, message):
                raise serial.SerialTimeoutException("escrita bloqueada")

        cameras, log, terminal = make_simulated_cameras(1), StringIO(), StringIO()
        with self.assertRaises(serial.SerialException):
            run_sector_pipeline(cameras, log, terminal, serial_output=BrokenSerial())
        self.assertEqual(json.loads(log.getvalue().splitlines()[-1])["type"], "serial_error")
        self.assertEqual(terminal.getvalue(), "")
        self.assertNotIn("sector_run_summary", log.getvalue())


class SerialTests(unittest.TestCase):
    def test_pyserial_loopback_echo_for_all_statuses(self):
        output = SerialOutput("loop://")
        try:
            for status, sectors in (("detected", ["F"]), ("detected", ["F", "D"]), ("no_ball", []), ("unavailable", [])):
                output.send({"schema_version": 1, "status": status, "sectors": sectors})
        finally:
            output.close()
        output.close()

    def test_network_serial_urls_and_invalid_baud_are_rejected(self):
        for port, baud in (("", 115200), ("socket://example.org:1234", 115200), ("loop://", 0), ("loop://", True)):
            with self.subTest(port=port, baud=baud), self.assertRaises(ValueError):
                SerialOutput(port, baud)

    def test_partial_write_and_wrong_echo_raise(self):
        class Connection:
            def write(self, data):
                return len(data) - 1

            def read(self, count):
                return b"wrong"

        output = SerialOutput("loop://")
        output.close()
        output._connection = Connection()
        with self.assertRaises(serial.SerialTimeoutException):
            output.send({"sectors": ["F"]})
        output._connection.write = lambda data: len(data)
        with self.assertRaises(serial.SerialException):
            output.send({"sectors": ["F"]})

    def test_cli_loopback_and_no_overwrite(self):
        with TemporaryDirectory() as directory, redirect_stdout(StringIO()) as terminal, redirect_stderr(StringIO()):
            path = Path(directory) / "sectors.jsonl"
            args = ["--frames", "6", "--serial-port", "loop://", "--output", str(path)]
            self.assertEqual(main(args), 0)
            self.assertEqual(terminal.getvalue().splitlines(), ["F", "D", "E", "A", "SEM_BOLA", "F D"])
            original = path.read_bytes()
            self.assertEqual(main(args), 1)
            self.assertEqual(path.read_bytes(), original)

    def test_cli_invalid_sectors_and_counts(self):
        for args in (["--sectors", "FF"], ["--sectors", "X"], ["--sectors", ""], ["--frames", "0"], ["--baudrate", "-1"]):
            with self.subTest(args=args), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                main(args)
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
