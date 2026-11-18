"""Fuente de clips SIN claves de Twitch: lee los clips públicos del canal con yt-dlp."""
import logging
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _range(hours):
    if hours <= 24:
        return "24hr"
    if hours <= 24 * 7:
        return "7d"
    return "30d"


def list_clips(login, lookback_hours=24, limit=100):
    """Lista ligera (sin juego) de los clips del canal, ordenada por views."""
    import yt_dlp

    url = f"https://www.twitch.tv/{login}/clips?filter=clips&range={_range(lookback_hours)}"
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    since = time.time() - lookback_hours * 3600
    out = []
    for e in info.get("entries") or []:
        ts = e.get("timestamp") or 0
        if ts and ts < since:
            continue
        out.append({
            "id": (e.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or str(e.get("id")),
            "url": e.get("url"),
            "title": e.get("title"),
            "view_count": e.get("view_count") or 0,
            "duration": e.get("duration") or 0,
            "broadcaster_name": login,
            "created_at": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
            "language": None,
            # sin VOD: usamos la hora de creación para detectar clips del mismo momento
            "video_id": f"ts-{login}",
            "vod_offset": int(ts) if ts else None,
        })
    out.sort(key=lambda c: c["view_count"], reverse=True)
    return out


def enrich(clip):
    """Pide los detalles del clip (juego, nombre del canal). Devuelve el clip actualizado."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(clip["url"], download=False)
    cats = info.get("categories") or []
    clip["game_id"] = cats[0] if cats else None   # aquí guardamos el NOMBRE del juego
    clip["broadcaster_name"] = info.get("channel") or clip["broadcaster_name"]
    clip["view_count"] = info.get("view_count") or clip["view_count"]
    return clip
