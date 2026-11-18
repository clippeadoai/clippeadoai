import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "game": "Grand Theft Auto VI",
    "mode": "streamers",
    "streamers": [],
    "languages": [],
    "lookback_hours": 24,
    "min_views": 30,
    "min_duration": 8,
    "max_duration": 60,
    "clips_per_streamer_per_run": 3,
    "clips_per_run_game_mode": 10,
    "dedupe_window_seconds": 45,
    "keep_raw": False,
    "subtitles": {"enabled": True, "model": "small", "language": "es", "device": "auto"},
    "video": {"layout": "blur", "crf": 20, "preset": "veryfast"},
    "tiktok": {
        "enabled": False,
        "mode": "draft",
        "privacy_level": "SELF_ONLY",
        "max_uploads_per_day": 8,
        "min_minutes_between_uploads": 60,
        "disable_comment": False,
        "disable_duet": False,
        "disable_stitch": False,
        "caption_template": "{title} 😂 | {streamer} #gta6 #gtavi #{streamer_tag} #gaming #fyp",
    },
    "schedule": {"fetch_every_minutes": 30},
}


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None):
    load_dotenv(ROOT / ".env")
    path = Path(path or os.getenv("CLIPPER_CONFIG", ROOT / "config.yaml"))
    if not path.exists():
        raise SystemExit(
            f"No encuentro {path}. Copia config.example.yaml a config.yaml y edítalo."
        )
    with open(path, encoding="utf-8") as f:
        cfg = _merge(DEFAULTS, yaml.safe_load(f) or {})

    cfg["paths"] = {
        "root": ROOT,
        "data": ROOT / "data",
        "raw": ROOT / "data" / "raw",
        "work": ROOT / "data" / "work",
        "output": ROOT / "output",
        "db": ROOT / "data" / "clipper.db",
        "tokens": ROOT / "data" / "tiktok_tokens.json",
    }
    for key in ("data", "raw", "work", "output"):
        cfg["paths"][key].mkdir(parents=True, exist_ok=True)

    cfg["env"] = {
        "twitch_client_id": os.getenv("TWITCH_CLIENT_ID", ""),
        "twitch_client_secret": os.getenv("TWITCH_CLIENT_SECRET", ""),
        "tiktok_client_key": os.getenv("TIKTOK_CLIENT_KEY", ""),
        "tiktok_client_secret": os.getenv("TIKTOK_CLIENT_SECRET", ""),
        "tiktok_redirect_uri": os.getenv("TIKTOK_REDIRECT_URI", ""),
        "tiktok_use_pkce": os.getenv("TIKTOK_USE_PKCE", "false").lower() == "true",
    }
    return cfg
