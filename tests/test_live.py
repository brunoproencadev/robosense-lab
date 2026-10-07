"""CLI ao vivo: falha, execução finita e proteção de resultados."""
from io import StringIO
from contextlib import redirect_stderr
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from robosense_lab.live import main


class LiveCLITests(unittest.TestCase):
    def test_hsv_cli_and_interrupt_close_camera_and_servos(self):
        capture = MagicMock()
        pixels = np.zeros((480, 640, 3), np.uint8)
        capture.read.side_effect = [(True, pixels), KeyboardInterrupt()]
        with TemporaryDirectory() as tmp, patch('robosense_lab.cameras.cv2.VideoCapture', return_value=capture), patch('robosense_lab.live.PanTiltServos') as servos:
            servos.return_value.update.return_value = (1500, 1500)
            output = Path(tmp) / 'trial'
            self.assertEqual(main(['--detector', 'hsv', '--no-preview', '--output-dir', str(output)]), 0)
            servos.assert_called_once_with(enabled=False, pan_sign=-1, tilt_down_sign=-1)
            servos.return_value.close.assert_called_once()
            capture.release.assert_called_once()
            rows = [json.loads(row) for row in (output / 'live.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['detector_profile'], 'school-hsv-v1')
            self.assertEqual(rows[-1]['type'], 'run_stopped')

    def test_unavailable_camera_releases_and_records_failure(self):
        capture = MagicMock()
        capture.isOpened.return_value = False
        with TemporaryDirectory() as tmp, patch('robosense_lab.cameras.cv2.VideoCapture', return_value=capture), redirect_stderr(StringIO()):
            output = Path(tmp) / 'trial'
            self.assertEqual(main(['--no-preview', '--frames', '2', '--output-dir', str(output)]), 1)
            capture.release.assert_called_once()
            rows = [json.loads(r) for r in (output / 'live.jsonl').read_text().splitlines()]
            self.assertEqual([r['type'] for r in rows], ['run_start', 'run_error'])

    def test_finite_cli_no_old_measure_and_no_overwrite(self):
        capture = MagicMock()
        capture.read.return_value = (True, np.zeros((240, 320, 3), np.uint8))
        with TemporaryDirectory() as tmp, patch('robosense_lab.cameras.cv2.VideoCapture', return_value=capture):
            output = Path(tmp) / 'trial'
            args = ['--no-preview', '--frames', '2', '--output-dir', str(output)]
            self.assertEqual(main(args), 0)
            capture.release.assert_called_once()
            rows = [json.loads(r) for r in (output / 'live.jsonl').read_text().splitlines()]
            self.assertEqual(rows[-1]['type'], 'run_summary')
            self.assertEqual(rows[-1]['frames'], 2)
            self.assertEqual([r['ball_x'] for r in rows if r['type'] == 'observation'], [None, None])
            with redirect_stderr(StringIO()):
                self.assertEqual(main(args), 1)
            self.assertEqual(capture.read.call_count, 2)
