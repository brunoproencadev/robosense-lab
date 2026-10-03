"""Baseline de segmentação por cor para o cenário sintético."""

import math

import cv2

from .models import BallObservation, Frame


class BallDetector:
    """Seleciona o maior contorno laranja com área e circularidade mínimas.

    A confiança é a circularidade limitada a [0, 1], não uma probabilidade.
    Os limiares fixos pertencem ao cenário M1; exigem revisão com imagens reais.
    """

    def detect(self, frame: Frame) -> BallObservation:
        hsv = cv2.cvtColor(frame.image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (5, 120, 100), (25, 255, 255))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        center_x = center_y = None
        confidence = 0.0
        largest_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area < 50 or perimeter <= 0:
                continue
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < 0.65 or area <= largest_area:
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            center_x = moments["m10"] / moments["m00"]
            center_y = moments["m01"] / moments["m00"]
            confidence = min(1.0, circularity)
            largest_area = area
        return BallObservation(
            camera_id=frame.camera_id,
            sequence=frame.sequence,
            timestamp_ns=frame.timestamp_ns,
            clock_domain=frame.clock_domain,
            ball_detected=center_x is not None,
            ball_x=center_x,
            ball_y=center_y,
            confidence=confidence,
        )
