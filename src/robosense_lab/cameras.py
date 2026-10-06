"""Contrato de aquisição, simulação M1/M2 e gravações M3."""

from dataclasses import replace
from collections.abc import Collection
import math
from typing import Protocol
from pathlib import Path
import sys
from time import perf_counter_ns

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


class RecordedVideoCamera:
    """Decodifica em ordem; timestamps são do vídeo, nunca relógio de hardware.

    OpenCV informa o número de frames: fim antes desse limite é erro, não ausência.
    A posição temporal vem do decoder (VFR); FPS médio é usado apenas na exportação.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise CameraError(f"vídeo não encontrado: {self.path}")
        self._capture = cv2.VideoCapture(str(self.path))
        self._closed = False
        self._sequence = 0
        self._previous_timestamp = 0
        self.fps = self._capture.get(cv2.CAP_PROP_FPS)
        count = self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if (not self._capture.isOpened() or not math.isfinite(self.fps) or self.fps <= 0
                or not math.isfinite(count) or count <= 0 or not count.is_integer()):
            self.close()
            raise CameraError(f"vídeo sem metadados válidos: {self.path}")
        self.frame_count = int(count)
        self._shape = None

    def read(self) -> Frame | None:
        if self._closed:
            raise CameraError("vídeo já encerrado")
        if self._sequence >= self.frame_count:
            return None
        ok, image = self._capture.read()
        if not ok:
            raise CameraError(f"falha de decodificação no frame {self._sequence}: {self.path.name}")
        if self._shape is not None and image.shape != self._shape:
            raise CameraError("dimensões do vídeo mudaram durante a decodificação")
        self._shape = image.shape
        position_ms = self._capture.get(cv2.CAP_PROP_POS_MSEC)
        if not math.isfinite(position_ms) or position_ms < 0:
            raise CameraError("timestamp do vídeo inválido")
        timestamp = round(position_ms * 1_000_000)
        if timestamp < self._previous_timestamp:
            raise CameraError("timestamp do vídeo regrediu")
        frame = Frame(image, self.path.name, self._sequence, timestamp, "recorded_video")
        self._previous_timestamp = timestamp
        self._sequence += 1
        return frame

    def close(self) -> None:
        self._capture.release()
        self._closed = True


class LiveCamera:
    """Fonte local USB/virtual. Timestamp marca entrega ao host, não exposição.

    Não mede atraso de DroidCam/rede/driver. read() pode bloquear no backend;
    reconexão e captura em fila limitada ficam para a validação M4.
    """

    def __init__(self, device: int = 0) -> None:
        if type(device) is not int or device < 0:
            raise ValueError("device deve ser inteiro não negativo")
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self._capture = cv2.VideoCapture(device, backend)
        self._closed = False
        self._sequence = 0
        self.camera_id = f"live-{device}"
        if not self._capture.isOpened():
            self.close()
            raise CameraError(f"câmera {device} indisponível; confira DroidCam e o índice")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        # Pedido ao driver; suporte e resolução efetiva dependem do dispositivo.
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> Frame:
        if self._closed:
            raise CameraError("câmera ao vivo já encerrada")
        ok, pixels = self._capture.read()
        timestamp = perf_counter_ns()
        if not ok or pixels is None:
            raise CameraError("sem imagem da câmera; confira conexão e aplicativos usando a fonte")
        frame = Frame(pixels, self.camera_id, self._sequence, timestamp, "host_delivery_monotonic")
        self._sequence += 1
        return frame

    def close(self) -> None:
        self._capture.release()
        self._closed = True


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
        camera_id: str = "simulated-0", visible_frames: Collection[int] | None = None,
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
        if not isinstance(camera_id, str) or not camera_id.strip():
            raise ValueError("camera_id deve identificar a câmera")
        visibility = None if visible_frames is None else tuple(visible_frames)
        if visibility is not None and any(type(i) is not int or not 0 <= i < frame_count for i in visibility):
            raise ValueError("visible_frames deve conter índices dentro da sequência")
        visibility = None if visibility is None else frozenset(visibility)
        self._configuration = {
            "frame_count": frame_count, "noise_std": noise_std, "seed": seed,
            "occlusion_fraction": occlusion_fraction,
            "loss_at_frame": loss_at_frame, "delay_ns": delay_ns,
            "camera_id": camera_id,
            "visible_frames": None if visibility is None else sorted(visibility),
        }
        self._rng = np.random.default_rng(seed)
        self.expected_positions: tuple[tuple[int, int] | None, ...] = tuple(
            None if (i % 5 == 4 if visibility is None else i not in visibility)
            else (24 + (i * 7) % 272, 24 + (i * 5) % 192)
            for i in range(frame_count)
        )
        self._sequence = 0
        self._closed = False

    @property
    def configuration(self) -> dict:
        """Cópia dos parâmetros necessários para reproduzir a execução."""
        configuration = dict(self._configuration)
        if configuration["visible_frames"] is not None:
            configuration["visible_frames"] = list(configuration["visible_frames"])
        return configuration

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
            camera_id=self._configuration["camera_id"],
            sequence=self._sequence,
            timestamp_ns=self._sequence * 1_000_000_000 // 30,
            clock_domain="simulation",
        )
        frame = replace(frame, received_timestamp_ns=frame.timestamp_ns + self._configuration["delay_ns"])
        self._sequence += 1
        return frame

    def close(self) -> None:
        self._closed = True
