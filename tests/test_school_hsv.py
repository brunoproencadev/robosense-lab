"""Recuperação do detector da escola no contrato Frame/BallObservation."""

import unittest
import cv2
import numpy as np

from robosense_lab.models import Frame
from robosense_lab.perception import HSVBallDetector


class SchoolHSVTests(unittest.TestCase):
    def test_scaling_current_measure_absence_and_input_preserved(self):
        detector = HSVBallDetector()
        pixels = np.zeros((480, 640, 3), np.uint8)
        cv2.circle(pixels, (500, 200), 35, (0, 140, 255), -1)
        original = pixels.copy()
        found = detector.detect(Frame(pixels, 'live-0', 0, 0, 'host_delivery_monotonic'))
        self.assertTrue(found.ball_detected)
        self.assertAlmostEqual(found.ball_x, 500, delta=3)
        self.assertAlmostEqual(found.ball_y, 200, delta=3)
        self.assertAlmostEqual(found.ball_radius, 35, delta=4)
        np.testing.assert_array_equal(pixels, original)
        missing = detector.detect(Frame(np.zeros_like(pixels), 'live-0', 1, 1, 'host_delivery_monotonic'))
        self.assertFalse(missing.ball_detected)
        self.assertIsNone(missing.ball_x)

    def test_validation_and_calibration_change_color_acceptance(self):
        for settings in ({'h_min': 26, 'h_max': 25}, {'s_min': -1}, {'v_min': 256}, {'processing_width': 0}):
            with self.assertRaises(ValueError):
                HSVBallDetector(**settings)
        pixels = np.zeros((240, 320, 3), np.uint8)
        cv2.circle(pixels, (150, 100), 20, (255, 0, 0), -1)
        frame = Frame(pixels, 'live-0', 0, 0, 'host_delivery_monotonic')
        self.assertFalse(HSVBallDetector().detect(frame).ball_detected)
        self.assertTrue(HSVBallDetector(h_min=110, h_max=130).detect(frame).ball_detected)
