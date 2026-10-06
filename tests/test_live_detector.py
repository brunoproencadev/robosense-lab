"""Perfil experimental ao vivo: cor, tamanho e associação atual."""
import unittest
import cv2
import numpy as np
from robosense_lab.models import Frame
from robosense_lab.perception import BallDetector, BallTracker


class LiveDetectorTests(unittest.TestCase):
    def test_dark_bridge_does_not_merge_ball_with_round_hand_patch(self):
        pixels = np.zeros((480, 640, 3), np.uint8)
        bright = cv2.cvtColor(np.uint8([[[18, 200, 240]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        shadow = cv2.cvtColor(np.uint8([[[12, 220, 100]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        cv2.line(pixels, (420, 250), (490, 398), shadow, 15)
        cv2.circle(pixels, (490, 398), 28, shadow, -1)
        cv2.circle(pixels, (420, 250), 36, bright, -1)
        result = BallDetector(recorded=True, live=True, roi_top=0).detect(Frame(pixels, 'x', 0, 0, 'live'))
        self.assertTrue(result.ball_detected)
        self.assertAlmostEqual(result.ball_x, 420, delta=4)
        self.assertAlmostEqual(result.ball_y, 250, delta=4)
        self.assertAlmostEqual(result.ball_radius, 36, delta=5)

    def test_yellow_highlight_dark_orange_and_near_camera(self):
        detector = BallDetector(recorded=True, live=True, roi_top=0)
        for hsv, radius in (((25, 90, 255), 35), ((12, 240, 95), 35), ((18, 220, 240), 190)):
            pixels = np.zeros((480, 640, 3), np.uint8)
            color = cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
            cv2.circle(pixels, (320, 240), radius, color, -1)
            original = pixels.copy()
            result = detector.detect(Frame(pixels, 'x', 0, 0, 'live'))
            self.assertTrue(result.ball_detected)
            self.assertAlmostEqual(result.ball_x, 320, delta=4)
            self.assertAlmostEqual(result.ball_y, 240, delta=4)
            self.assertAlmostEqual(result.ball_radius, radius, delta=5)
            np.testing.assert_array_equal(pixels, original)

    def test_red_skin_colored_patch_is_not_an_orange_ball(self):
        pixels = np.zeros((480, 640, 3), np.uint8)
        reddish = cv2.cvtColor(np.uint8([[[0, 210, 180]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        cv2.circle(pixels, (320, 240), 20, reddish, -1)
        result = BallDetector(recorded=True, live=True, roi_top=0).detect(Frame(pixels, 'x', 0, 0, 'live'))
        self.assertFalse(result.ball_detected)

    def test_near_ball_touching_skin_and_smaller_ball(self):
        detector = BallDetector(recorded=True, live=True, roi_top=0)
        # Pele saturada moderadamente encosta na bola: não deve formar um único alvo.
        skin = cv2.cvtColor(np.uint8([[[12, 100, 180]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        for radius in (70, 8):
            pixels = np.full((480, 640, 3), (100, 70, 40), np.uint8)
            cv2.rectangle(pixels, (320, 250), (470, 450), skin, -1)
            cv2.circle(pixels, (300, 240), radius, (0, 140, 255), -1)
            result = detector.detect(Frame(pixels, 'x', 0, 0, 'live'))
            self.assertTrue(result.ball_detected)
            self.assertAlmostEqual(result.ball_x, 300, delta=4)
            self.assertAlmostEqual(result.ball_y, 240, delta=4)
            self.assertAlmostEqual(result.ball_radius, radius, delta=5)
        pixels[:] = skin
        self.assertFalse(detector.detect(Frame(pixels, 'x', 1, 1, 'live')).ball_detected)

    def test_live_reacquires_after_short_gap_without_old_coordinates(self):
        tracker = BallTracker(BallDetector(recorded=True, live=True, roi_top=0), max_reference_seconds=.3)
        def frame(x, timestamp):
            pixels = np.zeros((480, 640, 3), np.uint8)
            if x is not None:
                cv2.circle(pixels, (x, 240), 20, (0, 140, 255), -1)
            return Frame(pixels, 'x', timestamp, timestamp, 'live')
        self.assertTrue(tracker.detect(frame(100, 0)).ball_detected)
        moved = tracker.detect(frame(500, 100_000_000))
        self.assertTrue(moved.ball_detected)
        self.assertAlmostEqual(moved.ball_x, 500, delta=4)
        missing = tracker.detect(frame(None, 200_000_000))
        self.assertFalse(missing.ball_detected)
        self.assertIsNone(missing.ball_x)
        self.assertTrue(tracker.detect(frame(500, 310_000_000)).ball_detected)

    def test_circle_boundary_separates_ball_from_connected_color_blob(self):
        pixels = np.zeros((480, 640, 3), np.uint8)
        skin = cv2.cvtColor(np.uint8([[[12, 170, 180]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        cv2.rectangle(pixels, (345, 270), (470, 450), skin, -1)
        cv2.circle(pixels, (320, 240), 45, (0, 140, 255), -1)
        result = BallDetector(recorded=True, live=True, roi_top=0).detect(Frame(pixels, 'x', 0, 0, 'live'))
        self.assertTrue(result.ball_detected)
        self.assertAlmostEqual(result.ball_x, 320, delta=6)
        self.assertAlmostEqual(result.ball_y, 240, delta=6)
        self.assertAlmostEqual(result.ball_radius, 45, delta=6)
