"""Orquesta todo: buscar clips -> descargar -> editar -> encolar -> subir."""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import editor, subtitles
from .tiktok import TikTok, TikTokError
from .twitch import Twitch

log = logging.getLogger(__name__)


def _rfc3339(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag(text):
    return re.sub(r"[^a-z0-9_]", "", text.lower())


def make_caption(cfg, clip):
    tpl = cfg["tiktok"]["caption_template"]
    title = (clip.get("title") or "").strip()
    # si el espectador no renombró el clip, el título es el del directo (largo, con "|"): no sirve
    if not title or len(title) > 60 or "|" in title:
        title = "Momentazo en GTA 6"
    caption = tpl.format(
        title=title,
        streamer=clip.get("broadcaster_name", ""),
        streamer_tag=_tag(clip.get("broadcaster_name", "")),
        views=clip.get("view_count", 0),
    )
    return caption[:2200]


def _passes_filters(cfg, clip, game_id):
    if game_id and clip.get("game_id") != game_id:
        return False
    if clip.get("view_count", 0) < cfg["min_views"]:
        return False
    if not cfg["min_duration"] <= clip.get("duration", 0) <= cfg["max_duration"]:
        return False
    langs = cfg.get("languages") or []
    if langs and clip.get("language") and clip.get("language") not in langs:
        return False
    return True


def _new_candidates(cfg, db, clips, game_id, limit):
    clips = sorted(
        (c for c in clips if _passes_filters(cfg, c, game_id)),
        key=lambda c: c.get("view_count", 0), reverse=True,
    )
    picked = []
    for c in clips:
        if len(picked) >= limit:
            break
        if db.seen(c["id"]):
            continue
        if db.near_duplicate(c.get("video_id"), c.get("vod_offset"), cfg["dedupe_window_seconds"]):
            db.add(c, "skipped", error="duplicado del mismo momento")
            continue
        # evitar duplicados dentro del mismo lote
        if any(p.get("video_id") and p.get("video_id") == c.get("video_id")
               and p.get("vod_offset") is not None and c.get("vod_offset") is not None
               and abs(p["vod_offset"] - c["vod_offset"]) <= cfg["dedupe_window_seconds"]
               for p in picked):
            db.add(c, "skipped", error="duplicado del mismo momento")
            continue
        picked.append(c)
    return picked


def find_clips(cfg, db, twitch):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=cfg["lookback_hours"])
    game_id = twitch.game_id(cfg["game"]) if cfg.get("game") else None

    streamer_cfg = {}
    candidates = []
    if cfg["mode"] == "game":
        if not game_id:
            raise SystemExit("mode: game necesita 'game' configurado")
        clips = twitch.clips(_rfc3339(since), _rfc3339(now), game_id=game_id, max_items=300)
        candidates = _new_candidates(cfg, db, clips, game_id, cfg["clips_per_run_game_mode"])
    else:
        for s in cfg["streamers"]:
            s = {"login": s} if isinstance(s, str) else s
            try:
                uid = twitch.user_id(s["login"])
                clips = twitch.clips(_rfc3339(since), _rfc3339(now), broadcaster_id=uid)
            except Exception as e:
                log.error("No pude leer clips de %s: %s", s["login"], e)
                continue
            new = _new_candidates(cfg, db, clips, game_id, s.get("clips_per_run", cfg["clips_per_streamer_per_run"]))
            log.info("%s: %d clips en ventana, %d nuevos seleccionados", s["login"], len(clips), len(new))
            for c in new:
                streamer_cfg[c["id"]] = s
            candidates.extend(new)
    return candidates, streamer_cfg


def find_clips_ytdlp(cfg, db):
    """Igual que find_clips pero sin claves de Twitch (lee los clips públicos del canal)."""
    from . import ytdlp_source

    if cfg["mode"] == "game":
        raise SystemExit("mode: game necesita claves de Twitch en .env. Usa mode: streamers o añade las claves.")
    game = cfg.get("game") or None
    window = cfg["dedupe_window_seconds"]
    streamer_cfg, candidates = {}, []
    for s in cfg["streamers"]:
        s = {"login": s} if isinstance(s, str) else s
        login = s["login"].lower()
        limit = s.get("clips_per_run", cfg["clips_per_streamer_per_run"])
        try:
            clips = ytdlp_source.list_clips(login, cfg["lookback_hours"])
        except Exception as e:
            log.error("No pude leer clips de %s: %s", login, e)
            continue
        picked = []
        for c in clips:
            if len(picked) >= limit:
                break
            if not _passes_filters(cfg, c, None) or db.seen(c["id"]):
                continue
            if db.near_duplicate(c["video_id"], c["vod_offset"], window) or any(
                    c["vod_offset"] is not None and p["vod_offset"] is not None
                    and abs(c["vod_offset"] - p["vod_offset"]) <= window for p in picked):
                db.add(c, "skipped", error="duplicado del mismo momento")
                continue
            try:
                ytdlp_source.enrich(c)
            except Exception as e:
                log.warning("No pude leer detalles del clip %s: %s", c["id"], e)
                continue
            if game and c.get("game_id") != game:
                db.add(c, "skipped", error=f"otro juego: {c.get('game_id')}")
                continue
            picked.append(c)
        log.info("%s: %d clips en ventana, %d nuevos seleccionados", login, len(clips), len(picked))
        for c in picked:
            streamer_cfg[c["id"]] = s
        candidates.extend(picked)
    return candidates, streamer_cfg


def download(url, dest_dir, clip_id):
    import yt_dlp

    out = Path(dest_dir) / f"{clip_id}.%(ext)s"
    opts = {
        "outtmpl": str(out),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))


def process_clip(cfg, db, clip, s_cfg=None):
    s_cfg = s_cfg or {}
    paths = cfg["paths"]
    cid = clip["id"]
    log.info("▶ Procesando '%s' de %s (%s views)", clip.get("title"), clip.get("broadcaster_name"), clip.get("view_count"))
    raw = None
    try:
        raw = download(clip["url"], paths["raw"], cid)

        chunks = []
        sub = cfg["subtitles"]
        if sub.get("enabled"):
            words = subtitles.transcribe_words(raw, sub["model"], sub.get("language"), sub.get("device", "auto"))
            chunks = subtitles.group_words(words)

        layout = s_cfg.get("layout", cfg["video"]["layout"])
        facecam = s_cfg.get("facecam", [0.0, 0.0, 0.25, 0.3])
        safe_name = _tag(clip.get("broadcaster_name", "clip"))
        dst = paths["output"] / f"{datetime.now():%Y%m%d}_{safe_name}_{cid[:40]}.mp4"
        editor.render_vertical(
            raw, dst, paths["work"], chunks=chunks,
            credit=f"twitch.tv/{s_cfg.get('login') or safe_name}",
            layout=layout, facecam=facecam,
            crf=cfg["video"]["crf"], preset=cfg["video"]["preset"],
        )
        caption = make_caption(cfg, clip)
        dst.with_suffix(".txt").write_text(caption, encoding="utf-8")
        db.add(clip, "ready", output_path=str(dst), caption=caption)
        log.info("✅ Listo: %s", dst.name)
    except Exception as e:
        log.exception("Falló el clip %s", cid)
        db.add(clip, "failed", error=str(e)[:500])
    finally:
        if raw and raw.exists() and not cfg.get("keep_raw"):
            raw.unlink(missing_ok=True)


def fetch_and_process(cfg, db):
    e = cfg["env"]
    if e["twitch_client_id"] and e["twitch_client_secret"]:
        candidates, streamer_cfg = find_clips(cfg, db, Twitch(e["twitch_client_id"], e["twitch_client_secret"]))
    else:
        log.info("Sin claves de Twitch: leo los clips públicos de cada canal directamente")
        candidates, streamer_cfg = find_clips_ytdlp(cfg, db)
    log.info("%d clips nuevos para procesar", len(candidates))
    for clip in candidates:
        process_clip(cfg, db, clip, streamer_cfg.get(clip["id"]))


def make_tiktok(cfg):
    e = cfg["env"]
    return TikTok(e["tiktok_client_key"], e["tiktok_client_secret"], e["tiktok_redirect_uri"],
                  cfg["paths"]["tokens"], e["tiktok_use_pkce"], cfg["tiktok"]["mode"])


def upload_next(cfg, db, tiktok=None):
    """Sube 1 clip si se respetan el límite diario y la separación mínima. Devuelve True si subió."""
    t = cfg["tiktok"]
    if not t.get("enabled"):
        return False
    if db.uploads_last_24h() >= t["max_uploads_per_day"]:
        return False
    if time.time() - db.last_upload_ts() < t["min_minutes_between_uploads"] * 60:
        return False
    row = db.next_ready()
    if not row:
        return False
    if not Path(row["output_path"]).exists():
        db.update(row["id"], status="failed", error="archivo de salida no existe")
        return False

    tiktok = tiktok or make_tiktok(cfg)
    log.info("⬆ Subiendo a TikTok: %s", Path(row["output_path"]).name)
    try:
        publish_id, status = tiktok.upload(
            row["output_path"], row["caption"], mode=t["mode"], privacy_level=t["privacy_level"],
            disable_comment=t["disable_comment"], disable_duet=t["disable_duet"],
            disable_stitch=t["disable_stitch"],
        )
    except TikTokError as e:
        log.error("Error subiendo a TikTok: %s", e)
        msg = str(e)
        # errores de cuenta/token: no marcar el clip como fallido, se reintentará
        if "auth" in msg.lower() or "token" in msg.lower() or "spam" in msg.lower() or "rate" in msg.lower():
            return False
        db.update(row["id"], status="failed", error=msg[:500])
        return False
    db.update(row["id"], status="uploaded", publish_id=publish_id)
    db.log_upload(row["id"])
    log.info("🎉 TikTok: %s (%s)", status, publish_id)
    return True
