"""Camera USB + bola laranja + servos posicionais: GPIO BCM 18/19."""
import argparse
import math
import threading
import time

import cv2
import numpy as np


class Servos:
    def __init__(self, enabled, pan_sign, tilt_sign):
        self.pi = None
        self.signs = (pan_sign, tilt_sign)
        self.pulses = [1500.0, 1500.0]
        self.last = None
        self.error = None
        self.lock = threading.Lock()
        self.done = threading.Event()
        if enabled:
            import pigpio
            self.pi = pigpio.pi("localhost")
            if not self.pi.connected:
                self.pi.stop()
                raise RuntimeError("pigpio desconectado. Execute: sudo pigpiod -l")
        self.worker = threading.Thread(target=self.watch, daemon=True)
        self.worker.start()

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

    def watch(self):
        while not self.done.wait(0.05):
            with self.lock:
                if self.last is not None and time.monotonic() - self.last > 0.5:
                    try:
                        self.write((0, 0))
                    except Exception as error:
                        self.error = error
                    self.last = None

    def update(self, center, shape, delivered):
        with self.lock:
            if self.error:
                raise RuntimeError("Falha no watchdog") from self.error
            now = time.monotonic()
            if center is None or now - delivered > 0.1:
                self.write((0, 0))
                self.last = None
                return
            height, width = shape[:2]
            errors = (2 * center[0] / width - 1, 2 * center[1] / height - 1)
            dt = min(0.1, max(0, now - self.last)) if self.last is not None else 0
            for axis, error in enumerate(errors):
                velocity = 0 if abs(error) <= 0.08 else self.signs[axis] * 90 * error
                self.pulses[axis] = float(np.clip(self.pulses[axis] + velocity * dt, 1200, 1800))
            self.write(self.pulses)
            self.last = now

    def close(self):
        self.done.set()
        self.worker.join()
        try:
            self.write((0, 0))
        finally:
            if self.pi is not None:
                self.pi.stop()


def detect(image, lower, upper):
    height, width = image.shape[:2]
    scale = min(1.0, 320 / width)
    small = cv2.resize(image, (round(width * scale), max(1, round(height * scale))))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if area < 40 or perimeter == 0:
            continue
        circularity = 4 * math.pi * area / perimeter ** 2
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if circularity >= 0.65 and area / (math.pi * radius ** 2) >= 0.55:
            candidates.append((area, x, y, radius))
    if not candidates:
        return None, mask
    _, x, y, radius = max(candidates)
    sx, sy = width / small.shape[1], height / small.shape[0]
    return (x * sx, y * sy, radius * max(sx, sy)), mask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--motores", action="store_true")
    parser.add_argument("--preview", action="store_true", help="requer desktop grafico")
    parser.add_argument("--pan-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument("--tilt-sign", type=int, choices=(-1, 1), default=1)
    parser.add_argument("--h-min", type=int, default=3)
    parser.add_argument("--h-max", type=int, default=25)
    parser.add_argument("--s-min", type=int, default=150)
    parser.add_argument("--v-min", type=int, default=70)
    args = parser.parse_args()
    if not (args.device >= 0 and 0 <= args.h_min <= args.h_max <= 179
            and 0 <= args.s_min <= 255 and 0 <= args.v_min <= 255):
        parser.error("Indice/limites HSV invalidos")
    camera = None
    servos = None
    try:
        camera = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
        if not camera.isOpened():
            raise RuntimeError("Camera USB indisponivel; confira --device e feche outros apps")
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        servos = Servos(args.motores, args.pan_sign, args.tilt_sign)
        lower = np.array((args.h_min, args.s_min, args.v_min), dtype=np.uint8)
        upper = np.array((args.h_max, 255, 255), dtype=np.uint8)
        print("Motores:", "ATIVOS" if args.motores else "DESLIGADOS", "| Ctrl+C encerra")
        last_print = 0
        while True:
            ok, image = camera.read()
            delivered = time.monotonic()
            if not ok or image is None:
                raise RuntimeError("Falha de captura USB")
            ball, mask = detect(image, lower, upper)
            servos.update(ball, image.shape, delivered)
            if delivered - last_print >= 1:
                print("SEM BOLA" if ball is None else f"Bola x={ball[0]:.0f} y={ball[1]:.0f}",
                      f"| PAN/TILT logicos: {servos.pulses[0]:.0f}/{servos.pulses[1]:.0f} us")
                last_print = delivered
            if args.preview:
                h, w = image.shape[:2]
                cv2.drawMarker(image, (w // 2, h // 2), (255, 255, 255))
                if ball is not None:
                    x, y, radius = map(round, ball)
                    cv2.circle(image, (x, y), radius, (0, 255, 0), 2)
                cv2.imshow("Tracking - ESC encerra", image)
                cv2.imshow("Mascara HSV", mask)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    except KeyboardInterrupt:
        print("Encerrando")
    except Exception as error:
        print("ERRO:", error)
        return 1
    finally:
        try:
            if servos is not None:
                servos.close()
        finally:
            if camera is not None:
                camera.release()
            if args.preview:
                cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
