"""Registros JSON Lines, sem dependência de interface gráfica ou rede."""

import json
from typing import TextIO


def write_event(stream: TextIO, event: dict) -> None:
    """Recusa NaN/Infinity e descarrega cada evento para o arquivo."""
    stream.write(json.dumps({"schema_version": 1, **event}, ensure_ascii=False, allow_nan=False) + "\n")
    stream.flush()
