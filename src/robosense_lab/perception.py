"""Segmentação por cor: baseline sintético e perfil óptico das gravações M3."""

import math

import cv2
import numpy as np

from .models import BallObservation, Frame

LIVE_PROFILE = "live-orange-v5"


class HSVBallDetector:
    """Perfil recuperado da escola; limites calibráveis, sem garantia semântica."""

    def __init__(self, *, h_min=3, h_max=25, s_min=150, v_min=70, processing_width=320):
        if (any(type(v) is not int for v in (h_min, h_max, s_min, v_min, processing_width))
                or not 0 <= h_min <= h_max <= 179 or not 0 <= s_min <= 255
                or not 0 <= v_min <= 255 or processing_width < 160):
            raise ValueError("Limites HSV/largura inválidos")
        self.lower = (h_min, s_min, v_min)
        self.upper = (h_max, 255, 255)
        self.processing_width = processing_width

    def detect(self, frame: Frame) -> BallObservation:
        image = frame.image
        height, width = image.shape[:2]
        scale = min(1, self.processing_width / width)
        small = cv2.resize(image, (round(width * scale), max(1, round(height * scale))))
        mask = cv2.inRange(cv2.cvtColor(small, cv2.COLOR_BGR2HSV), self.lower, self.upper)
        kernel = np.ones((3, 3), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_area, center, radius, confidence = 0, None, None, 0
        sx, sy = width / small.shape[1], height / small.shape[0]
        for contour in contours:
            area, perimeter = cv2.contourArea(contour), cv2.arcLength(contour, True)
            if area < 40 or perimeter <= 0:
                continue
            circularity = 4 * math.pi * area / perimeter ** 2
            (x, y), r = cv2.minEnclosingCircle(contour)
            if circularity >= .65 and area / (math.pi * r ** 2) >= .55 and area > best_area:
                best_area, center = area, (x * sx, y * sy)
                radius, confidence = r * max(sx, sy), min(1, circularity)
        return BallObservation(frame.camera_id, frame.sequence, frame.timestamp_ns, frame.clock_domain,
                               center is not None, None if center is None else center[0],
                               None if center is None else center[1], confidence, radius)


class BallDetector:
    """Seleciona o maior candidato de cor e forma válidas.

    A confiança é a circularidade limitada a [0, 1], não uma probabilidade.
    Por padrão mantém o M1. recorded=True usa o perfil experimental M3, cujo
    recorte e limites de tamanho dependem da montagem e precisam de calibração.
    live=True usa cor/brilho para sombra vermelha e reflexo amarelo, e permite
    alvos próximos. Não é universal; outros objetos parecidos ainda confundem.
    """

    def __init__(self, *, recorded: bool = False, live: bool = False, processing_width: int = 320,
                 roi_top: float = 0.15) -> None:
        if live and not recorded:
            raise ValueError("live exige recorded=True")
        if type(processing_width) is not int or processing_width < 160:
            raise ValueError("processing_width deve ser inteiro >= 160")
        if not math.isfinite(roi_top) or not 0 <= roi_top < 1:
            raise ValueError("roi_top deve estar entre 0 e 1 (exclusivo)")
        self.recorded = recorded
        self.live = live
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
            if self.live:
                hue, saturation, value = cv2.split(hsv)
                color_strength = saturation.astype(np.uint16) + value
                chromatic = (((hue <= 35) | (hue >= 170)) & (saturation >= 70)
                             & (value >= 60))
                # Não unir sombra à cor forte: essa união pode conectar mão/bola.
                planes = [chromatic & (color_strength >= 370),
                          chromatic & (hue >= 18) & (hue <= 35) & (color_strength >= 330),
                          chromatic & (saturation >= 210) & (value >= 80)]
                candidates = []
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                for priority, plane in zip((3, 2, 1), planes):
                    mask = plane.astype(np.uint8) * 255
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0)
                    found, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    candidates.extend((priority, contour) for contour in found)
            else:
                mask = cv2.inRange(hsv, (0, 40, 80), (35, 255, 255))
                mask |= cv2.inRange(hsv, (170, 40, 80), (179, 255, 255))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
                                        borderType=cv2.BORDER_CONSTANT, borderValue=0)
        else:
            mask = cv2.inRange(hsv, (5, 120, 100), (25, 255, 255))
        if not self.live:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidates = [(0, contour) for contour in contours]
        if self.live:
            orange = cv2.inRange(hsv, (3, 70, 80), (35, 255, 255))
        center_x = center_y = None
        confidence = 0.0
        best_score = 0.0
        radius = None
        for priority, contour in candidates:
            if self.recorded:
                hull = cv2.convexHull(contour)
                if self.live and cv2.contourArea(contour) < .65 * cv2.contourArea(hull):
                    continue
                contour = hull
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area < (8 if self.recorded else 50) or perimeter <= 0:
                continue
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < (0.65 if self.live or not self.recorded else 0.5) or (not self.live and area <= best_score):
                continue
            candidate_score = area
            (circle_x, circle_y), candidate_radius = cv2.minEnclosingCircle(contour)
            if self.live:
                x0, y0, w, h = cv2.boundingRect(contour)
                # Contorno totalmente vermelho continua ambíguo com pele.
                local_orange = orange[y0:y0 + h, x0:x0 + w]
                local_contour = contour - np.array([[[x0, y0]]], dtype=np.int32)
                support = np.zeros((h, w), dtype=np.uint8)
                cv2.drawContours(support, [local_contour], -1, 255, -1)
                if cv2.countNonZero(cv2.bitwise_and(local_orange, support)) < .02 * area:
                    continue
                candidate_score = cv2.contourArea(contour) * circularity * (1 + .05 * priority)
            if self.recorded and (area / (math.pi * candidate_radius ** 2) < (0.5 if self.live else 0.4)
                                  or candidate_radius < image.shape[1] * (0.008 if self.live else 0.02)
                                  or candidate_radius > image.shape[1] * (0.4 if self.live else 0.09)
                                  or area > image.shape[0] * image.shape[1] * (0.5 if self.live else 0.08)):
                continue
            if previous is not None:
                x, y = circle_x * scale_x, (circle_y + top) * scale_y
                r = candidate_radius * max(scale_x, scale_y)
                if self.live:
                    # Continuidade é preferência, nunca veto a uma medida atual
                    # válida após movimento rápido. Não há posição prevista.
                    distance = math.dist((x, y), (previous.ball_x, previous.ball_y))
                    candidate_score *= 1 + .25 * math.exp(-distance / max(r, previous.ball_radius))
                elif (not .55 <= r / previous.ball_radius <= 1.8
                        or math.dist((x, y), (previous.ball_x, previous.ball_y))
                        > max(previous.ball_radius * 4, width * .15)):
                    continue
            if candidate_score <= best_score:
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            center_x = (circle_x if self.recorded else moments["m10"] / moments["m00"]) * scale_x
            center_y = ((circle_y if self.recorded else moments["m01"] / moments["m00"]) + top) * scale_y
            radius = candidate_radius * max(scale_x, scale_y)
            confidence = min(1.0, circularity)
            best_score = candidate_score
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

    Referência por até 2 segundos por padrão, no relógio da fonte. Evita saltos para distratores
    durante oclusões breves; após esse prazo volta à busca sem referência.
    """

    def __init__(self, detector: BallDetector, *, max_reference_seconds: float = 2) -> None:
        if not math.isfinite(max_reference_seconds) or max_reference_seconds <= 0:
            raise ValueError("max_reference_seconds deve ser finito positivo")
        self.detector = detector
        self.max_reference_ns = int(max_reference_seconds * 1e9)
        self.previous: BallObservation | None = None

    def detect(self, frame: Frame) -> BallObservation:
        previous = self.previous
        if previous is not None and (frame.camera_id != previous.camera_id
                or frame.clock_domain != previous.clock_domain
                or not 0 <= frame.timestamp_ns - previous.timestamp_ns <= self.max_reference_ns):
            previous = self.previous = None
        observation = self.detector.detect(frame, previous=previous)
        # Um recorte na borda altera o raio: desenhe a medida atual, mas não a
        # use como referência de tamanho para bloquear a entrada da bola.
        if observation.ball_detected and (observation.ball_radius <= observation.ball_x
                < frame.image.shape[1] - observation.ball_radius
                and observation.ball_radius <= observation.ball_y
                < frame.image.shape[0] - observation.ball_radius):
            self.previous = observation
        return observation
