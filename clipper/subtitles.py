"""Transcripción con faster-whisper y generación de subtítulos .ass estilo TikTok."""
import logging

log = logging.getLogger(__name__)

_model = None
_failed = False  # si el modelo no se pudo cargar, no reintentar en cada clip


def _get_model(name, device):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # import perezoso: es pesado

        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        compute = "float16" if device == "cuda" else "int8"
        log.info("Cargando Whisper '%s' en %s (la primera vez descarga el modelo)...", name, device)
        _model = WhisperModel(name, device=device, compute_type=compute)
    return _model


def _load_audio(path, sr=16000):
    """Extrae el audio con ffmpeg (mono, 16 kHz) sin depender de PyAV."""
    import subprocess

    import numpy as np

    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def transcribe_words(video_path, model="small", language="es", device="auto"):
    """Devuelve una lista de (inicio, fin, palabra)."""
    global _failed
    if _failed:
        return []
    try:
        m = _get_model(model, device)
        segments, _ = m.transcribe(
            _load_audio(video_path),
            language=language or None,
            word_timestamps=True,
            vad_filter=True,
        )
        words = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append((w.start, w.end, text))
        return words
    except ImportError:
        _failed = True
        log.warning("faster-whisper no está instalado: sigo sin subtítulos.")
    except Exception as e:
        if _model is None:
            _failed = True
        log.warning("No pude transcribir (%s): sigo sin subtítulos.", str(e).splitlines()[0][:150])
    return []


def group_words(words, max_words=3, max_dur=1.4, max_gap=0.5):
    """Agrupa palabras en bloques cortos (2-3 palabras), el estilo que funciona en TikTok."""
    chunks, cur = [], []
    for start, end, text in words:
        if cur and (
            len(cur) >= max_words
            or end - cur[0][0] > max_dur
            or start - cur[-1][1] > max_gap
        ):
            chunks.append(cur)
            cur = []
        cur.append((start, end, text))
    if cur:
        chunks.append(cur)
    return [(c[0][0], c[-1][1], " ".join(t for _, _, t in c)) for c in chunks]
