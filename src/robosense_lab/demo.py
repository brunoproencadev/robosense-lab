"""Gera um painel de apresentação a partir de uma execução real do M1."""

import argparse
from io import StringIO
import json
from pathlib import Path
import sys

import cv2
import numpy as np

from .cameras import CameraError, SimulatedCamera
from .perception import BallDetector
from .pipeline import run_pipeline


def label(image: np.ndarray, text: str, x: int, y: int, *, scale: float = 0.7, color=(230, 239, 248), thickness: int = 1) -> None:
    cv2.putText(image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def rounded_box(image: np.ndarray, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int], radius: int = 18) -> None:
    x1, y1 = start
    x2, y2 = end
    cv2.rectangle(image, (x1 + radius, y1), (x2 - radius, y2), color, -1)
    cv2.rectangle(image, (x1, y1 + radius), (x2, y2 - radius), color, -1)
    for center in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius), (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
        cv2.circle(image, center, radius, color, -1, cv2.LINE_AA)


def _draw_frame(canvas: np.ndarray, image: np.ndarray, observation: dict, title: str, frame_index: int) -> None:
    detected = observation["ball_detected"]
    accent = (169, 222, 105) if detected else (190, 177, 159)
    title_color = (243, 247, 252)
    label(canvas, title.upper(), 112 if frame_index == 20 else 864, 365, scale=0.72, color=accent, thickness=2)
    label(canvas, f"FRAME {frame_index + 1:02d} / 60  |  {observation['camera_id']}", 112 if frame_index == 20 else 864, 397, scale=0.46, color=(168, 189, 212))

    x = 112 if frame_index == 20 else 864
    panel_y = 425
    image_x, image_y = x, panel_y
    enlarged = cv2.resize(image, (640, 480), interpolation=cv2.INTER_NEAREST)
    if detected:
        center = (round(observation["ball_x"] * 2), round(observation["ball_y"] * 2))
        cv2.circle(enlarged, center, 30, (104, 222, 166), 3, cv2.LINE_AA)
        cv2.drawMarker(enlarged, center, (240, 255, 249), cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)
        label_text = f"CENTRO  x={observation['ball_x']:.0f}  y={observation['ball_y']:.0f} px"
        cv2.rectangle(enlarged, (0, 438), (640, 480), (40, 25, 13), -1)
        label(enlarged, label_text, 16, 466, scale=0.55, color=(230, 255, 207))
    else:
        cv2.rectangle(enlarged, (0, 438), (640, 480), (40, 25, 13), -1)
        label(enlarged, "SEM DETECCAO  |  COORDENADAS INDISPONIVEIS", 16, 466, scale=0.43, color=(230, 217, 205))
    canvas[image_y:image_y + 480, image_x:image_x + 640] = enlarged
    cv2.rectangle(canvas, (image_x, image_y), (image_x + 639, image_y + 479), accent, 2)

    y = 943
    label(canvas, "CANDIDATO VALIDADO" if detected else "CANDIDATO NAO ENCONTRADO", x, y, scale=0.48, color=title_color)
    detail = f"Centroide da mascara HSV  |  circularidade {observation['confidence']:.2f}" if detected else "Mascara HSV vazia  |  bola_detected = false"
    label(canvas, detail, x, y + 29, scale=0.43, color=(168, 189, 212))


def make_demo() -> np.ndarray:
    camera = SimulatedCamera(60)
    log = StringIO()
    summary = run_pipeline(camera, BallDetector(), log, expected_positions=camera.expected_positions)
    events = [json.loads(line) for line in log.getvalue().splitlines()]
    observations = {event["sequence"]: event for event in events if event["type"] == "observation"}
    positive_index, negative_index = 20, 4

    image = np.zeros((1190, 1600, 3), dtype=np.uint8)
    image[:] = (38, 23, 15)
    cv2.rectangle(image, (0, 0), (1600, 14), (197, 226, 120), -1)

    label(image, "ROBOSENSE LAB   /   M1", 80, 79, scale=0.65, color=(120, 226, 197), thickness=2)
    label(image, "Do frame a observacao", 80, 145, scale=1.25, color=(252, 247, 243), thickness=2)
    label(image, "OpenCV encontra um candidato e estima seu centro em pixels.", 80, 187, scale=0.62, color=(212, 189, 168))

    steps = ((80, "01  CAMERA SIMULADA"), (575, "02  OPENCV / HSV"), (1070, "03  OBSERVACAO"))
    for x, title in steps:
        rounded_box(image, (x, 224), (x + 450, 274), (62, 43, 28), 14)
        label(image, title, x + 19, 257, scale=0.51, color=(244, 229, 216), thickness=1)
    for x in (540, 1035):
        label(image, ">", x, 258, scale=0.85, color=(120, 226, 197), thickness=2)

    for x in (68, 820):
        rounded_box(image, (x, 311), (x + 712, 1005), (57, 38, 25), 22)

    positive_camera = SimulatedCamera(positive_index + 1)
    positive_frame = None
    for _ in range(positive_index + 1):
        positive_frame = positive_camera.read()
    positive_camera.close()
    negative_camera = SimulatedCamera(negative_index + 1)
    negative_frame = None
    for _ in range(negative_index + 1):
        negative_frame = negative_camera.read()
    negative_camera.close()

    assert positive_frame is not None and negative_frame is not None
    _draw_frame(image, positive_frame.image, observations[positive_index], "Bola encontrada", positive_index)
    _draw_frame(image, negative_frame.image, observations[negative_index], "Sem bola", negative_index)

    metrics = (
        ("60", "FRAMES"),
        (f"{summary['true_positives']} / 48", "DETECCOES CORRETAS"),
        (f"{summary['true_negatives']} / 12", "AUSENCIAS CORRETAS"),
        (f"{summary['false_positives']}", "FALSOS POSITIVOS"),
        (f"{summary['mean_localization_error_px']:.0f} px", "ERRO MEDIO DO CENTRO"),
    )
    card_width, card_gap, start_x = 280, 24, 80
    for index, (value, caption) in enumerate(metrics):
        x = start_x + index * (card_width + card_gap)
        rounded_box(image, (x, 1035), (x + card_width, 1120), (62, 43, 28), 14)
        label(image, value, x + 17, 1076, scale=0.79, color=(120, 226, 197), thickness=2)
        label(image, caption, x + 17, 1104, scale=0.34, color=(211, 190, 171))

    label(image, "DEMONSTRACAO SINTETICA  |  circulo laranja em fundo verde", 80, 1162, scale=0.43, color=(123, 203, 241))
    label(image, "A bola real da Infrared League e o hardware ainda precisam ser validados.", 780, 1162, scale=0.40, color=(168, 189, 212))
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria uma imagem demonstrativa do pipeline M1 usando o detector atual.")
    parser.add_argument("--output", type=Path, default=Path("runs/demo-m1.png"), help="novo arquivo PNG; não sobrescreve")
    args = parser.parse_args(argv)
    try:
        encoded_ok, encoded = cv2.imencode(".png", make_demo())
        if not encoded_ok:
            raise OSError("OpenCV não conseguiu codificar a imagem PNG")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write(encoded.tobytes())
    except (OSError, CameraError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(f"Demonstração visual: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
