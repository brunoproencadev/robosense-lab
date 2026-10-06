"""Empacota uma execução já concluída em vídeos H.264 e uma página local.

Dependência de desenvolvimento opcional: pip install imageio-ffmpeg.
Não participa do detector, da reprodução Tk ou da instalação na Raspberry Pi.
"""

import argparse
import html
import json
from pathlib import Path
import shutil
import subprocess

import cv2
from robosense_lab.m3 import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    import imageio_ffmpeg
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    cards, manifest = [], []
    for run in summary:
        source = run["input"]
        if Path(source).name != source or Path(source).suffix.lower() != ".mp4":
            raise ValueError("nome de vídeo inválido no resumo")
        stem = Path(source).stem
        target = args.output_dir / f"{stem}-annotated.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-n", "-loglevel", "error",
                        "-i", str(args.run_dir / target.name), "-an", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(target)], check=True)
        capture = cv2.VideoCapture(str(target))
        try:
            if not capture.isOpened() or int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) != run["frames"]:
                raise RuntimeError("conversão H.264 incompleta")
        finally:
            capture.release()
        for suffix in (".jsonl", "-preview.jpg"):
            shutil.copyfile(args.run_dir / f"{stem}{suffix}", args.output_dir / f"{stem}{suffix}")
        manifest.append({"file": target.name, "sha256": sha256(target), "frames": run["frames"],
                         "codec": "H.264", "audio": False, "timing": "CFR average source FPS"})
        cards.append(f'<article><h2>{html.escape(source)}</h2><video controls preload="metadata" '
                     f'poster="{html.escape(stem)}-preview.jpg" src="{html.escape(target.name)}"></video></article>')
    shutil.copyfile(args.run_dir / "summary.json", args.output_dir / "summary.json")
    shutil.copyfile(args.evaluation, args.output_dir / "evaluation.json")
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (args.output_dir / "index.html").write_text('''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RoboSense — M3</title>
<style>body{max-width:1100px;margin:32px auto;padding:0 18px;background:#101820;color:#eef4f6;
font:16px/1.5 system-ui}video{width:100%;border-radius:10px;background:#000}article{margin:32px 0}
h1{color:#80eac8}h2{font-size:18px}a{color:#80eac8}</style><h1>RoboSense Lab — bola real</h1>
<p>Left | Front | Right por terços da imagem. O círculo verde acompanha a medida atual;
desaparece quando não há detecção. Use os controles para reproduzir, pausar e rever.</p>
<p>Gravações de aproximadamente 21 FPS. Processamento local em Windows; desempenho na Pi ainda não medido.
Anotações aproximadas e avaliação exploratória: <a href="evaluation.json">resultados</a>;
<a href="summary.json">execução completa</a>.</p>''' + "".join(cards) + "</html>", encoding="utf-8")
    print(args.output_dir)


if __name__ == "__main__":
    main()
