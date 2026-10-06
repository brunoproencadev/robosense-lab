"""M3: vídeos reais, setores na imagem, círculos e reprodução opcional em Tk."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter, perf_counter_ns, sleep

import cv2
import numpy as np

from .cameras import CameraError, RecordedVideoCamera
from .models import BallObservation
from .perception import BallDetector, BallTracker
from .telemetry import runtime_versions, write_event


def image_sector(x: float | None, width: int) -> str | None:
    """Terços sem espelhar: Left < 1/3; Front < 2/3; Right no restante."""
    if type(width) is not int or width <= 0:
        raise ValueError("largura deve ser inteira positiva")
    if x is None:
        return None
    if not math.isfinite(x) or not 0 <= x < width:
        raise ValueError("centro fora da imagem")
    return "Left" if x < width / 3 else "Front" if x < 2 * width / 3 else "Right"


def annotate(image: np.ndarray, observation: BallObservation, processing_ms: float,
             *, display_width: int = 960, roi_top: float = 0.15) -> np.ndarray:
    """Desenha só a detecção do frame atual, sem prever bola oculta."""
    height, width = image.shape[:2]
    out_width = min(width, display_width)
    out_height = max(2, round(height * out_width / width))
    # mp4v requer dimensões pares; escala efetiva é preservada abaixo.
    out_width -= out_width % 2
    out_height -= out_height % 2
    canvas = cv2.resize(image, (out_width, out_height))
    sx, sy = out_width / width, out_height / height
    sector = image_sector(observation.ball_x, width)
    for i, label in enumerate(("Left", "Front", "Right")):
        x = round(i * out_width / 3)
        if i:
            cv2.line(canvas, (x, 0), (x, out_height - 1), (180, 180, 180), 1)
        color = (0, 255, 255) if label == sector else (230, 230, 230)
        cv2.putText(canvas, label, (x + 12, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2)
    cv2.line(canvas, (0, round(roi_top * out_height)), (out_width - 1, round(roi_top * out_height)),
             (150, 150, 150), 1)
    if observation.ball_detected:
        center = (round(observation.ball_x * sx), round(observation.ball_y * sy))
        radius = max(2, math.ceil(observation.ball_radius * max(sx, sy)))
        cv2.circle(canvas, center, radius + 2, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.drawMarker(canvas, center, (0, 255, 0), cv2.MARKER_CROSS, 10, 1)
    cv2.rectangle(canvas, (0, out_height - 35), (out_width, out_height), (20, 20, 20), -1)
    text = f'{sector or "NO BALL"} | detector {processing_ms:.2f} ms | frame {observation.sequence}'
    cv2.putText(canvas, text, (12, out_height - 12), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
    return canvas


class ReplayPreview:
    """Tk é opcional; sem OpenCV GUI e sem fila de frames processados."""

    def __init__(self) -> None:
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("RoboSense M3 — Left / Front / Right — Esc para sair")
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _: self.close())
        self.label = tk.Label(self.root)
        self.label.pack()

    def show(self, image: np.ndarray, deadline: float) -> None:
        while not self.closed and perf_counter() < deadline:
            self.root.update()
            sleep(min(.01, max(0, deadline - perf_counter())))
        if self.closed:
            raise InterruptedError("prévia encerrada pelo usuário")
        h, w = image.shape[:2]
        data = f"P6\n{w} {h}\n255\n".encode() + cv2.cvtColor(image, cv2.COLOR_BGR2RGB).tobytes()
        self.photo = self.tk.PhotoImage(data=data, format="PPM")
        self.label.configure(image=self.photo)
        self.root.update()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.root.destroy()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_video(path: Path, output_dir: Path, detector: BallDetector,
                  preview: ReplayPreview | None = None) -> dict:
    with ExitStack() as resources:
        camera = RecordedVideoCamera(path)
        resources.callback(camera.close)
        log = resources.enter_context((output_dir / f"{path.stem}.jsonl").open("x", encoding="utf-8"))
        metadata = {"input": path.name, "sha256": sha256(path), "source_fps": camera.fps,
                    "source_frames": camera.frame_count, "processing_width": detector.processing_width,
                    "roi_top": detector.roi_top, "versions": runtime_versions(),
                    "profile": "m3-hsv-v1", "association_reference_ms": 2000,
                    "clock_domain": "recorded_video", "output_timing": "CFR mean source FPS; silent"}
        write_event(log, {"type": "run_start", **metadata})
        writer = None
        detector_times, step_times = [], []
        counts = {"Left": 0, "Front": 0, "Right": 0, "NO_BALL": 0}
        wall_start = perf_counter()
        first_timestamp = None
        first_detection_saved = False
        tracker = BallTracker(detector)
        try:
            while True:
                step_start = perf_counter_ns()
                frame = camera.read()
                if frame is None:
                    break
                if first_timestamp is None:
                    first_timestamp = frame.timestamp_ns
                started = perf_counter_ns()
                observation = tracker.detect(frame)
                processing_ms = (perf_counter_ns() - started) / 1e6
                sector = image_sector(observation.ball_x, frame.image.shape[1])
                counts[sector or "NO_BALL"] += 1
                rendered = annotate(frame.image, observation, processing_ms, roi_top=detector.roi_top)
                if writer is None:
                    writer = cv2.VideoWriter(str(output_dir / f"{path.stem}-annotated.mp4"),
                                             cv2.VideoWriter_fourcc(*"mp4v"), camera.fps,
                                             (rendered.shape[1], rendered.shape[0]))
                    resources.callback(writer.release)
                    if not writer.isOpened():
                        raise CameraError("encoder mp4v indisponível")
                writer.write(rendered)
                if observation.ball_detected and not first_detection_saved and (
                        observation.ball_radius <= observation.ball_x < frame.image.shape[1] - observation.ball_radius):
                    if not cv2.imwrite(str(output_dir / f"{path.stem}-preview.jpg"), rendered):
                        raise OSError("não foi possível salvar a prévia")
                    first_detection_saved = True
                write_event(log, {"type": "observation", **asdict(observation), "sector": sector,
                                  "processing_ms": processing_ms})
                detector_times.append(processing_ms)
                step_times.append((perf_counter_ns() - step_start) / 1e6)
                if preview:
                    preview.show(rendered, wall_start + (frame.timestamp_ns - first_timestamp) / 1e9)
            # Finaliza e verifica o arquivo: VideoWriter.write não informa sucesso.
            writer.release()
            check = cv2.VideoCapture(str(output_dir / f"{path.stem}-annotated.mp4"))
            try:
                if not check.isOpened() or int(check.get(cv2.CAP_PROP_FRAME_COUNT)) != len(detector_times):
                    raise OSError("vídeo exportado incompleto")
            finally:
                check.release()
        except Exception as error:
            write_event(log, {"type": "run_error", "error": str(error), "frames": len(detector_times)})
            raise
        summary = {**metadata, "frames": len(detector_times), "sector_counts": counts,
                   "mean_detector_ms": float(np.mean(detector_times)),
                   "p95_detector_ms": float(np.percentile(detector_times, 95)),
                   "p95_decode_detect_render_write_ms": float(np.percentile(step_times, 95)),
                   "wall_seconds": perf_counter() - wall_start, "preview_paced": preview is not None}
        write_event(log, {"type": "run_summary", **summary})
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, required=True, help="diretório novo")
    parser.add_argument("--processing-width", type=int, default=320)
    parser.add_argument("--roi-top", type=float, default=.15, help="fração superior ignorada (0 a <1)")
    parser.add_argument("--preview", action="store_true", help="Tk opcional, replay nos timestamps do vídeo")
    args = parser.parse_args(argv)
    try:
        detector = BallDetector(recorded=True, processing_width=args.processing_width, roi_top=args.roi_top)
        if len({p.stem for p in args.videos}) != len(args.videos):
            raise ValueError("nomes de vídeo devem ser únicos")
        for path in args.videos:
            if not path.is_file():
                raise CameraError(f"vídeo não encontrado: {path}")
        args.output_dir.mkdir(parents=True, exist_ok=False)
        with ExitStack() as resources:
            preview = ReplayPreview() if args.preview else None
            if preview:
                resources.callback(preview.close)
            results = [process_video(path, args.output_dir, detector, preview) for path in args.videos]
        (args.output_dir / "summary.json").write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"output_dir": str(args.output_dir), "videos": len(results),
                          "frames": sum(r["frames"] for r in results)}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"M3 interrompido: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
