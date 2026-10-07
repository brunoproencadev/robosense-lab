"""Câmera USB/virtual, detector experimental e pan/tilt opcional da câmera."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import sys
from pathlib import Path
from time import perf_counter, perf_counter_ns

from .cameras import LiveCamera
from .m3 import ReplayPreview, annotate, image_sector
from .perception import BallDetector, BallTracker, HSVBallDetector, LIVE_PROFILE
from .pan_tilt import PanTiltServos
from .telemetry import runtime_versions, write_event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0, help="índice da câmera no sistema")
    parser.add_argument("--frames", type=int, default=0, help="0: até Esc; positivo: ensaio limitado")
    parser.add_argument("--output-dir", type=Path, required=True, help="pasta nova para logs")
    parser.add_argument("--roi-top", type=float, default=0, help="0: imagem inteira; campo M3: 0.15")
    parser.add_argument("--processing-width", type=int, default=320)
    parser.add_argument("--no-preview", action="store_true", help="sem janela; Ctrl+C encerra")
    parser.add_argument("--detector", choices=("live", "hsv"), default="live")
    parser.add_argument("--h-min", type=int, default=3)
    parser.add_argument("--h-max", type=int, default=25)
    parser.add_argument("--s-min", type=int, default=150)
    parser.add_argument("--v-min", type=int, default=70)
    parser.add_argument("--servos", "--motores", action="store_true", help="habilita somente pan/tilt da câmera na Pi")
    parser.add_argument("--pan-sign", type=int, choices=(-1, 1), default=-1)
    parser.add_argument("--tilt-down-sign", type=int, choices=(-1, 1), default=-1)
    args = parser.parse_args(argv)
    if args.device < 0 or args.frames < 0:
        parser.error("device/frames não negativos")
    try:
        hsv = HSVBallDetector(h_min=args.h_min, h_max=args.h_max, s_min=args.s_min,
                              v_min=args.v_min, processing_width=args.processing_width)
        if args.detector == "hsv" and args.roi_top != 0:
            parser.error("perfil HSV da escola usa imagem inteira; omita --roi-top")
        detector = hsv if args.detector == "hsv" else BallTracker(
            BallDetector(recorded=True, live=True, processing_width=args.processing_width, roi_top=args.roi_top),
            max_reference_seconds=.3)
        profile = "school-hsv-v1" if args.detector == "hsv" else LIVE_PROFILE
        args.output_dir.mkdir(parents=True, exist_ok=False)
        with ExitStack() as resources:
            log = resources.enter_context((args.output_dir / "live.jsonl").open("x", encoding="utf-8"))
            write_event(log, {"type": "run_start", "device": args.device, "versions": runtime_versions(),
                              "processing_width": args.processing_width, "roi_top": args.roi_top,
                              "detector_profile": profile, "max_reference_seconds": .3 if args.detector == "live" else None,
                              "hsv_lower": hsv.lower, "hsv_upper": hsv.upper,
                              "servos_enabled": args.servos, "pan_sign": args.pan_sign,
                              "tilt_down_sign": args.tilt_down_sign,
                              "timestamp_semantics": "host delivery; sensor/network latency unknown"})
            count = 0
            previous_delivery = None
            started = perf_counter()
            try:
                servos = PanTiltServos(enabled=args.servos, pan_sign=args.pan_sign, tilt_down_sign=args.tilt_down_sign)
                resources.callback(servos.close)
                camera = LiveCamera(args.device)
                resources.callback(camera.close)
                preview = None if args.no_preview else ReplayPreview()
                if preview:
                    resources.callback(preview.close)
                    preview.root.title(f"RoboSense ao vivo ({profile}) — servos {'ON' if args.servos else 'OFF'} — Esc para sair")
                print(f"Perfil: {profile} | servos {'ATIVOS' if args.servos else 'DESLIGADOS (simulação lógica)'}", flush=True)
                while args.frames == 0 or count < args.frames:
                    if preview:
                        if preview.closed:
                            break
                        preview.root.update()
                        if preview.closed:
                            break
                    read_start = perf_counter_ns()
                    frame = camera.read()
                    read_ms = (perf_counter_ns() - read_start) / 1e6
                    interval_ms = None if previous_delivery is None else (frame.timestamp_ns - previous_delivery) / 1e6
                    previous_delivery = frame.timestamp_ns
                    start = perf_counter_ns()
                    observation = detector.detect(frame)
                    ms = (perf_counter_ns() - start) / 1e6
                    servo_start = perf_counter_ns()
                    pulses = servos.update(observation, frame.image.shape[1], frame.image.shape[0])
                    servo_ms = (perf_counter_ns() - servo_start) / 1e6
                    write_event(log, {"type": "observation", **asdict(observation),
                                      "sector": image_sector(observation.ball_x, frame.image.shape[1]),
                                      "processing_ms": ms, "image_width": frame.image.shape[1],
                                      "image_height": frame.image.shape[0], "servo_pulses_us": pulses,
                                      "servo_commanded": args.servos and servos.last is not None,
                                      "capture_read_ms": read_ms, "servo_update_ms": servo_ms,
                                      "host_frame_interval_ms": interval_ms})
                    count += 1
                    if preview:
                        preview.show(annotate(frame.image, observation, ms, roi_top=args.roi_top), perf_counter())
                elapsed = perf_counter() - started
                write_event(log, {"type": "run_summary", "frames": count,
                                  "wall_seconds": elapsed, "host_processed_fps": count / elapsed,
                                  "stop_reason": "frame_limit" if args.frames and count == args.frames else "user"})
            except KeyboardInterrupt:
                write_event(log, {"type": "run_stopped", "frames": count, "reason": "keyboard_interrupt"})
                return 0
            except Exception as error:
                write_event(log, {"type": "run_error", "frames": count, "error": str(error)})
                raise
        return 0
    except Exception as error:
        print(f"Ensaio ao vivo interrompido: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
