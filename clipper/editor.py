"""Convierte un clip horizontal en vídeo vertical 1080x1920 listo para TikTok."""
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

W, H = 1080, 1920
CAM_H = 768            # alto de la facecam en layout "split"
GAME_H = H - CAM_H     # alto del gameplay en layout "split"


def _ts(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(path, chunks, credit, layout, duration):
    """Subtítulos grandes en mayúsculas + crédito al streamer durante todo el clip."""
    if layout == "split":
        sub_align, sub_margin = 8, CAM_H - 70   # justo en la unión cámara/gameplay
        credit_align, credit_margin = 2, 140    # abajo
    else:
        sub_align, sub_margin = 8, 1330          # debajo del vídeo centrado
        credit_align, credit_margin = 8, 380     # encima del vídeo centrado

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,{sub_align},60,60,{sub_margin},1
Style: Credit,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,3,3,0,{credit_align},40,40,{credit_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if credit:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(duration + 1)},Credit,,0,0,0,,{_esc(credit)}\n")
    for start, end, text in chunks:
        # pequeño "pop" de escala al aparecer cada bloque
        pop = r"{\fscx85\fscy85\t(0,90,\fscx100\fscy100)}"
        lines.append(
            f"Dialogue: 0,{_ts(start)},{_ts(end + 0.05)},Sub,,0,0,0,,{pop}{_esc(text.upper())}\n"
        )
    Path(path).write_text("".join(lines), encoding="utf-8")


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out or 0)


def _filter(layout, facecam, ass_name):
    if layout == "split":
        fx, fy, fw, fh = facecam
        graph = (
            f"[0:v]crop=iw*{fw}:ih*{fh}:iw*{fx}:ih*{fy},"
            f"scale={W}:{CAM_H}:force_original_aspect_ratio=increase,crop={W}:{CAM_H}[cam];"
            f"[0:v]scale=-2:{GAME_H},crop={W}:{GAME_H}[game];"
            f"[cam][game]vstack=inputs=2,setsar=1[v]"
        )
    else:  # blur: vídeo completo centrado sobre fondo desenfocado
        graph = (
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=25:3,eq=brightness=-0.08[bg];"
            f"[0:v]scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
    if ass_name:
        graph += f";[v]ass={ass_name}[out]"
        return graph, "[out]"
    return graph, "[v]"


def render_vertical(src, dst, workdir, chunks=None, credit=None, layout="blur",
                    facecam=(0.0, 0.0, 0.25, 0.3), crf=20, preset="veryfast"):
    src, dst, workdir = Path(src).resolve(), Path(dst).resolve(), Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(src)

    ass_name = None
    if chunks or credit:
        ass_name = f"{dst.stem}.ass"
        build_ass(workdir / ass_name, chunks or [], credit, layout, duration)

    graph, out_label = _filter(layout, facecam, ass_name)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-filter_complex", graph, "-map", out_label, "-map", "0:a?",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart", str(dst),
    ]
    # cwd=workdir para que la ruta del .ass sea relativa (evita problemas de escape en Windows)
    res = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {res.stderr.strip()[-800:]}")
    if ass_name:
        (workdir / ass_name).unlink(missing_ok=True)
    return dst
