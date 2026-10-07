"""Entrega ao host, falha de captura e fechamento da fonte."""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import cv2
from robosense_lab.cameras import CameraError, LiveCamera


class LiveCameraTests(unittest.TestCase):
    def test_linux_selects_v4l2_and_closes(self):
        capture = MagicMock()
        with patch('robosense_lab.cameras.sys.platform', 'linux'), patch('robosense_lab.cameras.cv2.VideoCapture', return_value=capture) as opened:
            camera = LiveCamera(0)
            opened.assert_called_once_with(0, cv2.CAP_V4L2)
            camera.close()
            capture.release.assert_called_once()

    def test_delivery_metadata_loss_and_release(self):
        capture = MagicMock()
        capture.read.side_effect = [(True, np.zeros((240, 320, 3), np.uint8)), (False, None)]
        with patch('robosense_lab.cameras.cv2.VideoCapture', return_value=capture):
            camera = LiveCamera(0)
            frame = camera.read()
            self.assertEqual(frame.clock_domain, 'host_delivery_monotonic')
            self.assertIsNone(frame.received_timestamp_ns)
            self.assertEqual(frame.sequence, 0)
            with self.assertRaises(CameraError):
                camera.read()
            camera.close()
            capture.release.assert_called_once()
            with self.assertRaises(CameraError):
                camera.read()
