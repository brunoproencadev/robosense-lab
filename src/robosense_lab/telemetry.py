"""Registros JSON Lines, sem dependência de interface gráfica ou rede."""

import json
import platform
from typing import TextIO

import cv2
import numpy as np


def runtime_versions() -> dict[str, str]:
    return {"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__}


def write_event(stream: TextIO, event: dict) -> None:
    """Recusa NaN/Infinity e descarrega cada evento para o arquivo."""
    stream.write(json.dumps({"schema_version": 1, **event}, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()
