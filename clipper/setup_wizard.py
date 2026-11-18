"""Asistente de configuración: pide las claves de Twitch y los streamers y lo deja todo listo."""
import re
import shutil

from .config import ROOT


def _ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default


def _set_env(text, key, value):
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        return re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    return text.rstrip("\n") + f"\n{key}={value}\n"


def run_setup():
    print("\n🎮  Configuración de GTA Clipper\n" + "-" * 40)
    env_path, cfg_path = ROOT / ".env", ROOT / "config.yaml"
    if not env_path.exists():
        shutil.copy(ROOT / ".env.example", env_path)
    if not cfg_path.exists():
        shutil.copy(ROOT / "config.example.yaml", cfg_path)

    env = env_path.read_text(encoding="utf-8")
    cur_id = re.search(r"^TWITCH_CLIENT_ID=(.*)$", env, re.M)
    cur_id = cur_id.group(1).strip() if cur_id else ""

    print("\n1) Claves de Twitch: OPCIONALES. La app funciona sin ellas (pulsa Enter dos veces para saltar).")
    print("   Solo hacen falta para el modo 'game' (clips de todo Twitch).")
    while True:
        cid = _ask("   Client ID", cur_id)
        secret = _ask("   Client Secret" + (" (Enter = dejar el que hay)" if cur_id else ""))
        if not secret:
            m = re.search(r"^TWITCH_CLIENT_SECRET=(.*)$", env, re.M)
            secret = m.group(1).strip() if m else ""
        if not cid and not secret:
            print("   ➖ Sin claves: leeré los clips públicos de cada canal directamente.")
            break
        if not cid or not secret:
            print("   ❌ Pon las dos claves, o deja las dos vacías para saltar.")
            continue
        try:
            from .twitch import Twitch
            Twitch(cid, secret)._auth()
            print("   ✅ Claves de Twitch correctas")
            break
        except Exception as e:
            import requests
            if isinstance(e, requests.HTTPError):
                print("   ❌ Twitch rechaza esas claves. Revisa que estén bien copiadas y vuelve a intentarlo.")
                cur_id = cid
                continue
            print(f"   ⚠ No pude conectar con Twitch para comprobarlas ({str(e)[:60]}). Las guardo igualmente.")
            break

    env = _set_env(env, "TWITCH_CLIENT_ID", cid or "")
    env = _set_env(env, "TWITCH_CLIENT_SECRET", secret or "")
    env_path.write_text(env, encoding="utf-8")

    print("\n2) Streamers de Twitch (su nombre en twitch.tv/NOMBRE), separados por comas")
    streamers = _ask("   Streamers", "djmariio, ibai, auronplay, elxokas, illojuan")
    logins = [s.strip().lower().replace("twitch.tv/", "") for s in streamers.split(",") if s.strip()]

    print("\n3) ¿Usar GTA V en vez de GTA VI? (solo para pruebas)")
    test_gta5 = _ask("   s/n", "n").lower().startswith("s")
    game = "Grand Theft Auto V" if test_gta5 else "Grand Theft Auto VI"

    cfg = cfg_path.read_text(encoding="utf-8")
    cfg = re.sub(r'^game:.*$', f'game: "{game}"', cfg, count=1, flags=re.M)
    block = "streamers:\n" + "".join(f"  - login: {l}\n    layout: blur\n" for l in logins) + "\n"
    cfg = re.sub(r"^streamers:\n(?:[ #].*\n|\n)*?(?=^languages:)", block, cfg, count=1, flags=re.M)
    cfg_path.write_text(cfg, encoding="utf-8")

    print("\n✅ Configuración guardada.")
    print(f"   Juego: {game}" + ("  (cuando salga GTA VI, vuelve a ejecutar la configuración y responde 'n')" if test_gta5 else ""))
    print(f"   Streamers: {', '.join(logins)}")
    print("   Subida a TikTok: desactivada (los vídeos quedan en la carpeta 'output' para subirlos tú)\n")
