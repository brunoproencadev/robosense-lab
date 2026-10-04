"""Saída serial de bancada; não altera o firmware ou o controle do robô."""

import json

import serial


class SerialOutput:
    """JSON ASCII delimitado por LF; operações têm timeout de um segundo."""

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        if not port or ("://" in port and port != "loop://"):
            raise ValueError("use uma porta serial local ou loop://")
        if type(baudrate) is not int or baudrate <= 0:
            raise ValueError("baudrate deve ser um inteiro positivo")
        self._loopback = port == "loop://"
        self._connection = serial.serial_for_url(port, baudrate=baudrate, timeout=1, write_timeout=1)

    def send(self, message: dict) -> None:
        packet = (json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")
        if self._connection.write(packet) != len(packet):
            raise serial.SerialTimeoutException("escrita serial incompleta")
        if self._loopback and self._connection.read(len(packet)) != packet:
            raise serial.SerialException("eco do loopback difere dos bytes enviados")

    def close(self) -> None:
        self._connection.close()
