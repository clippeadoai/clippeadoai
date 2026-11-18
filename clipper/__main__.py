"""
Uso:
  python -m clipper setup                Asistente: claves de Twitch y streamers
  python -m clipper auth                 Conecta tu cuenta de TikTok (una sola vez)
  python -m clipper run                  Un ciclo: busca clips, los edita y sube 1 si toca
  python -m clipper daemon               Modo automático 24/7 (lo que quieres dejar encendido)
  python -m clipper status               Resumen de clips y subidas
  python -m clipper test-edit VIDEO.mp4  Prueba la edición vertical con un vídeo tuyo
  python -m clipper doctor               Comprueba que todo está bien configurado
"""
import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

from . import editor, pipeline, subtitles
from .config import load_config
from .db import DB


def setup_logging(cfg):
    fmt = "%(asctime)s %(levelname)-7s %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(cfg["paths"]["data"] / "clipper.log", encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%H:%M:%S", handlers=handlers)
    for noisy in ("urllib3", "faster_whisper", "httpx", "httpx2", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def cmd_daemon(cfg, db):
    log = logging.getLogger("daemon")
    every = cfg["schedule"]["fetch_every_minutes"] * 60
    last_fetch = 0
    log.info("🚀 Modo automático. Busco clips cada %d min. Ctrl+C para parar.", every // 60)
    while True:
        try:
            if time.time() - last_fetch >= every:
                last_fetch = time.time()
                pipeline.fetch_and_process(cfg, db)
            pipeline.upload_next(cfg, db)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception:
            log.exception("Error en el ciclo; sigo en 60 s")
        time.sleep(60)


def cmd_status(cfg, db):
    print("\n📊 Estado:", db.counts() or "sin clips todavía")
    print(f"⬆  Subidas últimas 24 h: {db.uploads_last_24h()}/{cfg['tiktok']['max_uploads_per_day']}\n")
    for r in db.recent():
        print(f"  [{r['status']:<8}] {r['broadcaster'] or '':<16} {r['views'] or 0:>6} views  {(r['title'] or '')[:50]}"
              + (f"  ⚠ {r['error'][:60]}" if r["error"] else ""))
    print()


def cmd_test_edit(cfg, video, layout):
    src = Path(video)
    dst = cfg["paths"]["output"] / f"TEST_{src.stem}_{layout}.mp4"
    chunks = []
    if cfg["subtitles"]["enabled"]:
        sub = cfg["subtitles"]
        chunks = subtitles.group_words(subtitles.transcribe_words(src, sub["model"], sub.get("language"), sub.get("device", "auto")))
    editor.render_vertical(src, dst, cfg["paths"]["work"], chunks=chunks,
                           credit="twitch.tv/streamer", layout=layout)
    print(f"✅ Generado: {dst}")


def cmd_doctor(cfg):
    ok = True

    def check(cond, msg, fix=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + msg + ("" if cond else f"  → {fix}"))
        ok &= bool(cond)

    print("\n🩺 Comprobando instalación:")
    check(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg instalado", "instala ffmpeg y añádelo al PATH")
    try:
        import yt_dlp  # noqa
        check(True, "yt-dlp instalado")
    except ImportError:
        check(False, "yt-dlp instalado", "pip install -r requirements.txt")
    try:
        import faster_whisper  # noqa
        check(True, "faster-whisper instalado (subtítulos)")
    except ImportError:
        check(not cfg["subtitles"]["enabled"], "faster-whisper instalado (subtítulos)",
              "pip install faster-whisper  o pon subtitles.enabled: false")
    e = cfg["env"]
    if e["twitch_client_id"] and e["twitch_client_secret"]:
        check(True, "Credenciales de Twitch en .env")
    else:
        check(cfg["mode"] != "game", "Sin claves de Twitch: leo los clips públicos de cada canal",
              "el modo 'game' necesita claves de Twitch")
    if cfg["tiktok"].get("enabled"):
        check(e["tiktok_client_key"] and e["tiktok_client_secret"], "Credenciales de TikTok en .env", "ver README paso 3")
        check(cfg["paths"]["tokens"].exists(), "Cuenta de TikTok conectada", "python -m clipper auth")
    else:
        print("  ➖ Subida a TikTok desactivada: los vídeos se quedan en la carpeta 'output'")
    check(cfg["mode"] == "game" or cfg["streamers"], "Streamers configurados", "añade streamers en config.yaml")
    if e["twitch_client_id"] and e["twitch_client_secret"]:
        try:
            from .twitch import Twitch
            t = Twitch(e["twitch_client_id"], e["twitch_client_secret"])
            if cfg.get("game"):
                gid = t.game_id(cfg["game"])
                check(True, f"Categoría de Twitch '{cfg['game']}' encontrada (id {gid})")
        except Exception as ex:
            check(False, "Conexión con Twitch", str(ex))
    print("\n" + ("Todo listo 🚀" if ok else "Arregla lo marcado con ❌") + "\n")


def main():
    ap = argparse.ArgumentParser(prog="clipper", description="Clipper automático Twitch → TikTok")
    ap.add_argument("--config", help="ruta a config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    sub.add_parser("run")
    sub.add_parser("daemon")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("setup")
    te = sub.add_parser("test-edit")
    te.add_argument("video")
    te.add_argument("--layout", choices=["blur", "split"], default="blur")
    args = ap.parse_args()

    if args.cmd == "setup":
        from .setup_wizard import run_setup
        run_setup()
        return

    cfg = load_config(args.config)
    setup_logging(cfg)
    db = DB(cfg["paths"]["db"])

    if args.cmd == "auth":
        pipeline.make_tiktok(cfg).authorize_interactive()
    elif args.cmd == "run":
        pipeline.fetch_and_process(cfg, db)
        pipeline.upload_next(cfg, db)
        cmd_status(cfg, db)
    elif args.cmd == "daemon":
        try:
            cmd_daemon(cfg, db)
        except KeyboardInterrupt:
            print("\nParado.")
    elif args.cmd == "status":
        cmd_status(cfg, db)
    elif args.cmd == "doctor":
        cmd_doctor(cfg)
    elif args.cmd == "test-edit":
        cmd_test_edit(cfg, args.video, args.layout)


if __name__ == "__main__":
    main()
