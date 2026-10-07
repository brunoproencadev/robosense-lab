"""Direções lógicas, dados atuais, desligamento e driver pigpio simulado."""

from contextlib import ExitStack
from dataclasses import replace
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from robosense_lab.models import BallObservation
from robosense_lab.pan_tilt import PanTiltServos


class PanTiltTests(unittest.TestCase):
    def test_watchdog_failure_prevents_rearming(self):
        controller = PanTiltServos(clock=lambda: self.now)
        self.addCleanup(controller.close)
        controller.update(self.observation(), 640, 480)
        controller.write = MagicMock(side_effect=RuntimeError('driver failed'))
        self.now += 500_000_001
        controller.stop_if_expired()
        with self.assertRaisesRegex(RuntimeError, 'watchdog'):
            controller.update(self.observation(), 640, 480)
        controller.write.side_effect = None

    def setUp(self):
        self.now = 1_000_000_000
        self.sequence = 0

    def observation(self, x=500, y=400):
        self.sequence += 1
        return BallObservation('live-0', self.sequence, self.now, 'host_delivery_monotonic',
                               x is not None, x, y if x is not None else None, 1 if x is not None else 0,
                               20 if x is not None else None)

    def advance(self, controller, x=500, y=400):
        self.now += 100_000_000
        return controller.update(self.observation(x, y), 640, 480)

    def test_inverted_pan_and_down_only_tilt(self):
        controller = PanTiltServos(clock=lambda: self.now)
        self.addCleanup(controller.close)
        controller.update(self.observation(), 640, 480)
        pan, tilt = self.advance(controller)
        self.assertLess(pan, 1500)
        self.assertLess(tilt, 1500)
        next_pan, next_tilt = self.advance(controller, 100, 30)
        self.assertGreater(next_pan, pan)
        self.assertEqual(next_tilt, tilt)
        self.advance(controller, 320, 240)
        self.assertEqual(controller.pulses, [next_pan, next_tilt])

    def test_both_mounting_signs_and_pulse_limits(self):
        for sign in (-1, 1):
            controller = PanTiltServos(pan_sign=sign, tilt_down_sign=sign, clock=lambda: self.now)
            self.addCleanup(controller.close)
            controller.update(self.observation(639, 479), 640, 480)
            for _ in range(500):
                self.advance(controller, 639, 479)
            self.assertEqual(controller.pulses, [1200, 1200] if sign == -1 else [1800, 1800])
            self.advance(controller, 320, 0)
            self.assertEqual(controller.pulses[1], 1200 if sign == -1 else 1800)

    def test_missing_old_future_wrong_clock_and_repeated_measure_disarm(self):
        controller = PanTiltServos(clock=lambda: self.now)
        self.addCleanup(controller.close)
        controller.write = MagicMock()
        valid = self.observation()
        controller.update(valid, 640, 480)
        cases = [valid, self.observation(None), replace(self.observation(), timestamp_ns=self.now - 100_000_001),
                 replace(self.observation(), timestamp_ns=self.now + 1),
                 replace(self.observation(), clock_domain='recorded_video')]
        for observation in cases:
            controller.update(observation, 640, 480)
            controller.write.assert_called_with((0, 0))
            self.assertIsNone(controller.last)

    def test_watchdog_without_new_frames_and_reacquisition_has_no_large_step(self):
        controller = PanTiltServos(clock=lambda: self.now)
        self.addCleanup(controller.close)
        controller.write = MagicMock()
        controller.update(self.observation(), 640, 480)
        self.advance(controller)
        saved = list(controller.pulses)
        self.now += 500_000_001
        controller.stop_if_expired()
        controller.write.assert_called_with((0, 0))
        controller.update(self.observation(), 640, 480)
        self.assertEqual(controller.pulses, saved)

    def test_gpio_error_attempts_both_shutdowns_and_closes_connection(self):
        driver = MagicMock(connected=True)
        driver.set_servo_pulsewidth.return_value = 0
        with ExitStack() as resources:
            resources.enter_context(patch('robosense_lab.pan_tilt.sys.platform', 'linux'))
            resources.enter_context(patch.dict(sys.modules, {'pigpio': SimpleNamespace(pi=lambda host: driver)}))
            controller = PanTiltServos(enabled=True, clock=lambda: self.now)
            driver.set_servo_pulsewidth.side_effect = [-1, 0, 0, 0]
            with self.assertRaisesRegex(RuntimeError, 'GPIO 18'):
                controller.update(self.observation(), 640, 480)
            self.assertEqual(driver.set_servo_pulsewidth.call_args_list[-2].args, (18, 0))
            self.assertEqual(driver.set_servo_pulsewidth.call_args_list[-1].args, (19, 0))
            driver.set_servo_pulsewidth.side_effect = None
            controller.close()
            driver.stop.assert_called_once()
