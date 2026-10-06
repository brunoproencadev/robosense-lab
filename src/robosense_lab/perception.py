"""Segmentação por cor: baseline sintético e perfil óptico das gravações M3."""

import math

import cv2

from .models import BallObservation, Frame


class BallDetector:
    """Seleciona o maior candidato de cor e forma válidas.

    A confiança é a circularidade limitada a [0, 1], não uma probabilidade.
    Por padrão mantém o M1. recorded=True usa o perfil experimental M3, cujo
    recorte e limites de tamanho dependem da montagem e precisam de calibração.
    """

    def __init__(self, *, recorded: bool = False, processing_width: int = 320,
                 roi_top: float = 0.15) -> None:
        if type(processing_width) is not int or processing_width < 160:
            raise ValueError("processing_width deve ser inteiro >= 160")
        if not math.isfinite(roi_top) or not 0 <= roi_top < 1:
            raise ValueError("roi_top deve estar entre 0 e 1 (exclusivo)")
        self.recorded = recorded
        self.processing_width = processing_width
        self.roi_top = roi_top

    def detect(self, frame: Frame, *, previous: BallObservation | None = None) -> BallObservation:
        image = frame.image
        height, width = image.shape[:2]
        if self.recorded and width > self.processing_width:
            image = cv2.resize(image, (self.processing_width, max(1, round(height * self.processing_width / width))),
                               interpolation=cv2.INTER_AREA)
        scale_x, scale_y = width / image.shape[1], height / image.shape[0]
        top = int(image.shape[0] * self.roi_top) if self.recorded else 0
        hsv = cv2.cvtColor(image[top:], cv2.COLOR_BGR2HSV)
        if self.recorded:
            # Perfil óptico M3: aceita reflexos amarelos e vermelho da bola.
            mask = cv2.inRange(hsv, (0, 40, 80), (35, 255, 255))
            mask |= cv2.inRange(hsv, (170, 40, 80), (179, 255, 255))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                                    borderType=cv2.BORDER_CONSTANT, borderValue=0)
        else:
            mask = cv2.inRange(hsv, (5, 120, 100), (25, 255, 255))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        center_x = center_y = None
        confidence = 0.0
        largest_area = 0.0
        radius = None
        for contour in contours:
            if self.recorded:
                contour = cv2.convexHull(contour)
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area < (8 if self.recorded else 50) or perimeter <= 0:
                continue
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < (0.5 if self.recorded else 0.65) or area <= largest_area:
                continue
            (circle_x, circle_y), candidate_radius = cv2.minEnclosingCircle(contour)
            if self.recorded and (area / (math.pi * candidate_radius ** 2) < 0.4
                                  or candidate_radius < image.shape[1] * 0.02
                                  or candidate_radius > image.shape[1] * 0.09
                                  or area > image.shape[0] * image.shape[1] * 0.08):
                continue
            if previous is not None:
                x, y = circle_x * scale_x, (circle_y + top) * scale_y
                r = candidate_radius * max(scale_x, scale_y)
                if (not .55 <= r / previous.ball_radius <= 1.8
                        or math.dist((x, y), (previous.ball_x, previous.ball_y))
                        > max(previous.ball_radius * 4, width * .15)):
                    continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            center_x = (circle_x if self.recorded else moments["m10"] / moments["m00"]) * scale_x
            center_y = ((circle_y if self.recorded else moments["m01"] / moments["m00"]) + top) * scale_y
            radius = candidate_radius * max(scale_x, scale_y)
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
            ball_radius=radius,
        )


class BallTracker:
    """Associa medidas atuais; nunca prevê ou reapresenta uma posição ausente.

    Referência por até 2 segundos de tempo do vídeo. Evita saltos para distratores
    durante oclusões breves; após esse prazo volta à busca sem referência.
    """

    def __init__(self, detector: BallDetector) -> None:
        self.detector = detector
        self.previous: BallObservation | None = None

    def detect(self, frame: Frame) -> BallObservation:
        previous = self.previous
        if previous is not None and (frame.camera_id != previous.camera_id
                or frame.clock_domain != previous.clock_domain
                or not 0 <= frame.timestamp_ns - previous.timestamp_ns <= 2_000_000_000):
            previous = self.previous = None
        observation = self.detector.detect(frame, previous=previous)
        # Um recorte na borda altera o raio: desenhe a medida atual, mas não a
        # use como referência de tamanho para bloquear a entrada da bola.
        if observation.ball_detected and (observation.ball_radius <= observation.ball_x
                < frame.image.shape[1] - observation.ball_radius):
            self.previous = observation
        return observation
