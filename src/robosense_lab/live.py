"""Ensaio ao vivo com câmera local/virtual e o perfil M3; preparação do M4."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import sys
from pathlib import Path
from time import perf_counter, perf_counter_ns

from .cameras import LiveCamera
from .m3 import ReplayPreview, annotate, image_sector
from .perception import BallDetector, BallTracker, LIVE_PROFILE
from .telemetry import runtime_versions, write_event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0, help="índice da câmera no sistema")
    parser.add_argument("--frames", type=int, default=0, help="0: até Esc; positivo: ensaio limitado")
    parser.add_argument("--output-dir", type=Path, required=True, help="pasta nova para logs")
    parser.add_argument("--roi-top", type=float, default=0, help="0: imagem inteira; campo M3: 0.15")
    parser.add_argument("--processing-width", type=int, default=320)
    parser.add_argument("--no-preview", action="store_true", help="exige --frames positivo")
    args = parser.parse_args(argv)
    if args.device < 0 or args.frames < 0 or (args.no_preview and args.frames == 0):
        parser.error("device/frames não negativos; --no-preview exige --frames positivo")
    try:
        detector = BallDetector(recorded=True, live=True, processing_width=args.processing_width, roi_top=args.roi_top)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        with ExitStack() as resources:
            log = resources.enter_context((args.output_dir / "live.jsonl").open("x", encoding="utf-8"))
            write_event(log, {"type": "run_start", "device": args.device, "versions": runtime_versions(),
                              "processing_width": args.processing_width, "roi_top": args.roi_top,
                              "detector_profile": LIVE_PROFILE, "max_reference_seconds": .3,
                              "timestamp_semantics": "host delivery; sensor/network latency unknown"})
            count = 0
            started = perf_counter()
            try:
                camera = LiveCamera(args.device)
                resources.callback(camera.close)
                preview = None if args.no_preview else ReplayPreview()
                if preview:
                    resources.callback(preview.close)
                    preview.root.title(f"RoboSense ao vivo ({LIVE_PROFILE}) — Left / Front / Right — Esc para sair")
                tracker = BallTracker(detector, max_reference_seconds=.3)
                while args.frames == 0 or count < args.frames:
                    if preview:
                        if preview.closed:
                            break
                        preview.root.update()
                        if preview.closed:
                            break
                    frame = camera.read()
                    start = perf_counter_ns()
                    observation = tracker.detect(frame)
                    ms = (perf_counter_ns() - start) / 1e6
                    write_event(log, {"type": "observation", **asdict(observation),
                                      "sector": image_sector(observation.ball_x, frame.image.shape[1]),
                                      "processing_ms": ms, "image_width": frame.image.shape[1],
                                      "image_height": frame.image.shape[0]})
                    count += 1
                    if preview:
                        preview.show(annotate(frame.image, observation, ms, roi_top=args.roi_top), perf_counter())
                elapsed = perf_counter() - started
                write_event(log, {"type": "run_summary", "frames": count,
                                  "wall_seconds": elapsed, "host_processed_fps": count / elapsed,
                                  "stop_reason": "frame_limit" if args.frames and count == args.frames else "user"})
            except Exception as error:
                write_event(log, {"type": "run_error", "frames": count, "error": str(error)})
                raise
        return 0
    except Exception as error:
        print(f"Ensaio ao vivo interrompido: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
