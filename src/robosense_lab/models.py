"""Contratos compartilhados, independentes da fonte da imagem."""

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class Frame:
    """Imagem BGR uint8; captura e entrega usam o mesmo clock_domain."""

    image: NDArray[np.uint8]
    camera_id: str
    sequence: int
    timestamp_ns: int
    clock_domain: str
    received_timestamp_ns: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.image, np.ndarray):
            raise ValueError("image deve ser um array NumPy")
        if (
            self.image.dtype != np.uint8
            or self.image.ndim != 3
            or self.image.shape[2] != 3
            or min(self.image.shape[:2]) == 0
        ):
            raise ValueError("image deve ser BGR uint8 com dimensões H x W x 3 não vazias")
        _validate_metadata(self.camera_id, self.sequence, self.timestamp_ns, self.clock_domain)
        if self.received_timestamp_ns is not None and (
            type(self.received_timestamp_ns) is not int
            or self.received_timestamp_ns < self.timestamp_ns
        ):
            raise ValueError("entrega deve ser um inteiro e não pode anteceder a captura")


@dataclass(frozen=True)
class BallObservation:
    camera_id: str
    sequence: int
    timestamp_ns: int
    clock_domain: str
    ball_detected: bool
    ball_x: float | None
    ball_y: float | None
    confidence: float

    def __post_init__(self) -> None:
        _validate_metadata(self.camera_id, self.sequence, self.timestamp_ns, self.clock_domain)
        if type(self.ball_detected) is not bool:
            raise ValueError("ball_detected deve ser booleano")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence deve estar entre 0 e 1")
        if self.ball_detected:
            if any(v is None or not math.isfinite(v) or v < 0 for v in (self.ball_x, self.ball_y)):
                raise ValueError("detecção exige coordenadas finitas e não negativas")
        elif self.ball_x is not None or self.ball_y is not None or self.confidence != 0:
            raise ValueError("sem detecção: coordenadas devem ser None e confidence deve ser 0")


def _validate_metadata(camera_id: str, sequence: int, timestamp_ns: int, clock_domain: str) -> None:
    if not isinstance(camera_id, str) or not camera_id.strip():
        raise ValueError("camera_id deve identificar a câmera")
    if not isinstance(clock_domain, str) or not clock_domain.strip():
        raise ValueError("clock_domain deve identificar o relógio")
    if type(sequence) is not int or sequence < 0:
        raise ValueError("sequence deve ser um inteiro não negativo")
    if type(timestamp_ns) is not int or timestamp_ns < 0:
        raise ValueError("timestamp_ns deve ser um inteiro não negativo")
