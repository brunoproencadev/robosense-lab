"""Bancada da câmera em BCM 18/19; não controla rodas nem Arduino GIGA."""

import sys
import threading
from time import perf_counter_ns


class PanTiltServos:
    """Pulsos lógicos limitados. Sentidos físicos dependem da montagem/calibração."""

    def __init__(self, *, enabled=False, pan_sign=-1, tilt_down_sign=-1, clock=perf_counter_ns):
        if type(pan_sign) is not int or pan_sign not in (-1, 1) or type(tilt_down_sign) is not int or tilt_down_sign not in (-1, 1):
            raise ValueError("Sinais devem ser -1 ou 1")
        self.pi = None
        self.pan_sign, self.tilt_down_sign = pan_sign, tilt_down_sign
        self.clock = clock
        self.pulses = [1500.0, 1500.0]
        self.last = None
        self.last_observation = None
        self.error = None
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.worker = None
        if enabled:
            if not sys.platform.startswith("linux"):
                raise RuntimeError("GPIO de servos exige Raspberry Pi/Linux; omita --servos para simular")
            import pigpio
            self.pi = pigpio.pi("localhost")
            if not self.pi.connected:
                self.pi.stop()
                raise RuntimeError("pigpio desconectado; inicie pigpiod localmente")
            try:
                self.write((0, 0))
                self.worker = threading.Thread(target=self.watch, daemon=True)
                self.worker.start()
            except BaseException:
                try:
                    self.write((0, 0))
                finally:
                    self.pi.stop()
                raise

    def write(self, pulses):
        if self.pi is None:
            return
        first_error = None
        for pin, pulse in zip((18, 19), pulses):
            try:
                if self.pi.set_servo_pulsewidth(pin, round(pulse)) < 0:
                    raise RuntimeError(f"Falha no GPIO {pin}")
            except Exception as error:
                first_error = first_error or error
        if first_error:
            raise first_error

    def stop_if_expired(self):
        with self.lock:
            if self.last is not None and self.clock() - self.last > 500_000_000:
                try:
                    self.write((0, 0))
                except Exception as error:
                    self.error = error
                finally:
                    self.last = None

    def watch(self):
        while not self.done.wait(.05):
            self.stop_if_expired()

    def update(self, observation, width, height):
        with self.lock:
            if self.error:
                raise RuntimeError("Falha no watchdog GPIO") from self.error
            now = self.clock()
            previous = self.last_observation
            repeated = (previous is not None and previous[0] == observation.camera_id
                        and (observation.sequence <= previous[1] or observation.timestamp_ns <= previous[2]))
            if (observation.clock_domain != "host_delivery_monotonic"
                    or repeated or not observation.ball_detected or not 0 <= now - observation.timestamp_ns <= 100_000_000
                    or type(width) is not int or type(height) is not int or width <= 0 or height <= 0
                    or not 0 <= observation.ball_x < width or not 0 <= observation.ball_y < height):
                self.write((0, 0))
                self.last = None
                return tuple(self.pulses)
            if previous is not None and previous[0] != observation.camera_id:
                self.last = None
            dt = min(.1, max(0, (now - self.last) / 1e9)) if self.last is not None else 0
            ex, ey = 2 * observation.ball_x / width - 1, 2 * observation.ball_y / height - 1
            pan_velocity = 0 if abs(ex) <= .08 else self.pan_sign * 90 * ex
            # Não subir para bola acima do centro, nem desfazer inclinação anterior.
            tilt_velocity = self.tilt_down_sign * 90 * ey if ey > .08 else 0
            self.pulses[0] = min(1800, max(1200, self.pulses[0] + pan_velocity * dt))
            tilt_limits = (1200, 1500) if self.tilt_down_sign == -1 else (1500, 1800)
            self.pulses[1] = min(tilt_limits[1], max(tilt_limits[0], self.pulses[1] + tilt_velocity * dt))
            try:
                self.write(self.pulses)
            except BaseException:
                self.last = None
                self.write((0, 0))
                raise
            self.last = now
            self.last_observation = (observation.camera_id, observation.sequence, observation.timestamp_ns)
            return tuple(self.pulses)

    def close(self):
        self.done.set()
        if self.worker:
            self.worker.join()
        try:
            with self.lock:
                self.last = None
                self.write((0, 0))
        finally:
            if self.pi is not None:
                self.pi.stop()
