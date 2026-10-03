"""Contrato de aquisição e fonte sintética dos milestones M1/M2."""

from dataclasses import replace
import math
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
    O M2 adiciona perturbações de pixels, perda terminal e atraso virtual.
    O cenário não modela óptica, infravermelho ou física do robô.
    """

    def __init__(
        self, frame_count: int = 60, *, noise_std: float = 0.0, seed: int = 42,
        occlusion_fraction: float = 0.0, loss_at_frame: int | None = None,
        delay_ns: int = 0,
    ) -> None:
        if type(frame_count) is not int or frame_count <= 0:
            raise ValueError("frame_count deve ser um inteiro positivo")
        if not math.isfinite(noise_std) or not 0 <= noise_std <= 255:
            raise ValueError("noise_std deve ser finito, entre 0 e 255")
        if type(seed) is not int or seed < 0:
            raise ValueError("seed deve ser um inteiro não negativo")
        if not math.isfinite(occlusion_fraction) or not 0 <= occlusion_fraction <= 1:
            raise ValueError("occlusion_fraction deve estar entre 0 e 1")
        if loss_at_frame is not None and (
            type(loss_at_frame) is not int or not 0 <= loss_at_frame < frame_count
        ):
            raise ValueError("loss_at_frame deve ser um índice dentro da sequência")
        if type(delay_ns) is not int or delay_ns < 0:
            raise ValueError("delay_ns deve ser um inteiro não negativo")
        self._configuration = {
            "frame_count": frame_count, "noise_std": noise_std, "seed": seed,
            "occlusion_fraction": occlusion_fraction,
            "loss_at_frame": loss_at_frame, "delay_ns": delay_ns,
        }
        self._rng = np.random.default_rng(seed)
        self.expected_positions: tuple[tuple[int, int] | None, ...] = tuple(
            None if i % 5 == 4 else (24 + (i * 7) % 272, 24 + (i * 5) % 192)
            for i in range(frame_count)
        )
        self._sequence = 0
        self._closed = False

    @property
    def configuration(self) -> dict:
        """Cópia dos parâmetros necessários para reproduzir a execução."""
        return dict(self._configuration)

    def read(self) -> Frame | None:
        if self._closed:
            raise CameraError("câmera já encerrada")
        if self._sequence == len(self.expected_positions):
            return None
        if self._sequence == self._configuration["loss_at_frame"]:
            raise CameraError(f"perda simulada da câmera no frame {self._sequence}")
        image = np.full((240, 320, 3), (0, 100, 0), dtype=np.uint8)
        center = self.expected_positions[self._sequence]
        if center is not None:
            cv2.circle(image, center, 12, (0, 140, 255), thickness=-1)
            covered_width = math.ceil(25 * self._configuration["occlusion_fraction"])
            if covered_width:
                x, y = center
                cv2.rectangle(image, (x - 12, y - 12), (x - 13 + covered_width, y + 12), (0, 100, 0), -1)
        if self._configuration["noise_std"]:
            noise = self._rng.normal(0, self._configuration["noise_std"], image.shape)
            image = np.clip(image.astype(np.float64) + noise, 0, 255).astype(np.uint8)
        frame = Frame(
            image=image,
            camera_id="simulated-0",
            sequence=self._sequence,
            timestamp_ns=self._sequence * 1_000_000_000 // 30,
            clock_domain="simulation",
        )
        frame = replace(frame, received_timestamp_ns=frame.timestamp_ns + self._configuration["delay_ns"])
        self._sequence += 1
        return frame

    def close(self) -> None:
        self._closed = True
