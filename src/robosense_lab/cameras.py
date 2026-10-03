"""Contrato de aquisição e fonte sintética determinística do M1."""

from typing import Protocol

import cv2
import numpy as np

from .models import Frame


class CameraError(RuntimeError):
    """Falha de aquisição; diferente do fim normal da sequência."""


class Camera(Protocol):
    def read(self) -> Frame | None:
        """Retorna frame, None no fim normal, ou levanta CameraError."""
        ...

    def close(self) -> None:
        """Libera a fonte; chamadas repetidas devem ser seguras."""
        ...


class SimulatedCamera:
    """Círculo laranja em fundo verde, 320 x 240, tempo virtual de 30 Hz.

    Cada quinto frame não contém bola. A fonte não espera tempo real.
    O cenário não modela óptica, infravermelho ou física do robô.
    """

    def __init__(self, frame_count: int = 60) -> None:
        if type(frame_count) is not int or frame_count <= 0:
            raise ValueError("frame_count deve ser um inteiro positivo")
        self.expected_positions: tuple[tuple[int, int] | None, ...] = tuple(
            None if i % 5 == 4 else (24 + (i * 7) % 272, 24 + (i * 5) % 192)
            for i in range(frame_count)
        )
        self._sequence = 0
        self._closed = False

    def read(self) -> Frame | None:
        if self._closed:
            raise CameraError("câmera já encerrada")
        if self._sequence == len(self.expected_positions):
            return None
        image = np.full((240, 320, 3), (0, 100, 0), dtype=np.uint8)
        center = self.expected_positions[self._sequence]
        if center is not None:
            cv2.circle(image, center, 12, (0, 140, 255), thickness=-1)
        frame = Frame(
            image=image,
            camera_id="simulated-0",
            sequence=self._sequence,
            timestamp_ns=self._sequence * 1_000_000_000 // 30,
            clock_domain="simulation",
        )
        self._sequence += 1
        return frame

    def close(self) -> None:
        self._closed = True
