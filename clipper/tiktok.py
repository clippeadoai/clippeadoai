"""Subida a TikTok con la Content Posting API oficial.

- mode "direct": publica en tu perfil con caption. Hasta que TikTok audite tu app,
  la API obliga a privacy_level=SELF_ONLY (solo tú lo ves); luego lo pasas a público con 1 toque.
  Tras la auditoría pon privacy_level: PUBLIC_TO_EVERYONE y es 100 % automático.
- mode "draft": lo manda a tu bandeja de borradores de TikTok (te llega notificación).
  La API de borradores no admite caption: se guarda en output/<id>.txt para copiarlo.
"""
import hashlib
import json
import logging
import os
import secrets
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

log = logging.getLogger(__name__)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API = "https://open.tiktokapis.com/v2"
# En modo borrador solo hace falta video.upload; video.publish solo para modo direct
SCOPES_DRAFT = "user.info.basic,video.upload"
SCOPES_DIRECT = "user.info.basic,video.upload,video.publish"

MB = 1024 * 1024


class TikTokError(RuntimeError):
    pass


class TikTok:
    def __init__(self, client_key, client_secret, redirect_uri, token_path, use_pkce=True, mode="draft"):
        if not client_key or not client_secret:
            raise SystemExit("Faltan TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET en .env")
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_path = Path(token_path)
        self.use_pkce = use_pkce
        self.scopes = SCOPES_DIRECT if mode == "direct" else SCOPES_DRAFT

    # ---------- OAuth ----------
    def authorize_interactive(self):
        if not self.redirect_uri:
            raise SystemExit("Falta TIKTOK_REDIRECT_URI en .env (debe coincidir con el de tu app)")
        state = secrets.token_urlsafe(16)
        params = {
            "client_key": self.client_key,
            "scope": self.scopes,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }
        verifier = None
        if self.use_pkce:
            verifier = secrets.token_urlsafe(48)[:64]
            # TikTok (Desktop) usa el SHA256 en hexadecimal como code_challenge
            params["code_challenge"] = hashlib.sha256(verifier.encode()).hexdigest()
            params["code_challenge_method"] = "S256"
        url = f"{AUTH_URL}?{urlencode(params)}"
        print("\n1) Se abrirá TikTok en el navegador. Inicia sesión con la cuenta donde quieres subir.")
        print("2) Acepta los permisos.")
        print("3) Te redirigirá a tu redirect URI. Copia la URL COMPLETA de la barra y pégala aquí.\n")
        print(url, "\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        pasted = input("URL de redirección: ").strip()
        qs = parse_qs(urlparse(pasted).query)
        if qs.get("state", [None])[0] != state:
            raise SystemExit("El 'state' no coincide. Repite el proceso.")
        if "code" not in qs:
            raise SystemExit(f"No hay 'code' en la URL: {qs.get('error_description') or qs}")
        data = {
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "code": qs["code"][0],
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        if verifier:
            data["code_verifier"] = verifier
        self._save_tokens(self._token_request(data))
        print("✅ Cuenta de TikTok conectada.")

    def _token_request(self, data):
        r = requests.post(
            TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30,
        )
        body = r.json()
        if "access_token" not in body:
            raise TikTokError(f"Error de token TikTok: {body}")
        return body

    def _save_tokens(self, body):
        now = time.time()
        tokens = {
            "access_token": body["access_token"],
            "refresh_token": body["refresh_token"],
            "open_id": body.get("open_id"),
            "expires_at": now + body.get("expires_in", 86400),
            "refresh_expires_at": now + body.get("refresh_expires_in", 31536000),
        }
        self.token_path.write_text(json.dumps(tokens, indent=2))
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass
        return tokens

    def _access_token(self):
        if not self.token_path.exists():
            raise TikTokError("TikTok no está conectado. Ejecuta: python -m clipper auth")
        tokens = json.loads(self.token_path.read_text())
        if time.time() > tokens["expires_at"] - 300:
            if time.time() > tokens["refresh_expires_at"]:
                raise TikTokError("La sesión de TikTok caducó. Ejecuta: python -m clipper auth")
            log.info("Renovando token de TikTok...")
            tokens = self._save_tokens(self._token_request({
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
            }))
        return tokens["access_token"]

    def _post(self, path, payload):
        r = requests.post(
            f"{API}{path}",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            data=json.dumps(payload),
            timeout=30,
        )
        try:
            body = r.json()
        except ValueError:
            raise TikTokError(f"Respuesta no JSON ({r.status_code}): {r.text[:300]}")
        err = body.get("error", {})
        if err.get("code") not in (None, "", "ok"):
            raise TikTokError(f"{path}: {err.get('code')} - {err.get('message')}")
        return body.get("data", {})

    # ---------- Subida ----------
    def creator_info(self):
        return self._post("/post/publish/creator_info/query/", {})

    @staticmethod
    def _chunks(size):
        # Reglas de TikTok: trozos de 5-64 MB; < 64 MB se puede mandar en uno solo.
        if size <= 64 * MB:
            return size, 1
        chunk = 10 * MB
        return chunk, size // chunk  # el último trozo se lleva el resto

    def _upload_file(self, upload_url, path, size, chunk, count):
        with open(path, "rb") as f:
            for i in range(count):
                start = i * chunk
                end = size - 1 if i == count - 1 else start + chunk - 1
                f.seek(start)
                data = f.read(end - start + 1)
                for attempt in range(4):
                    r = requests.put(
                        upload_url, data=data, timeout=300,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(data)),
                            "Content-Range": f"bytes {start}-{end}/{size}",
                        },
                    )
                    if r.status_code in (200, 201, 206):
                        break
                    log.warning("Trozo %d/%d falló (%s), reintento...", i + 1, count, r.status_code)
                    time.sleep(2 ** attempt)
                else:
                    raise TikTokError(f"No se pudo subir el trozo {i + 1}: {r.status_code} {r.text[:200]}")

    def upload(self, path, caption, mode="direct", privacy_level="SELF_ONLY",
               disable_comment=False, disable_duet=False, disable_stitch=False):
        path = Path(path)
        size = path.stat().st_size
        chunk, count = self._chunks(size)
        source = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk,
            "total_chunk_count": count,
        }

        if mode == "draft":
            data = self._post("/post/publish/inbox/video/init/", {"source_info": source})
        else:
            info = self.creator_info()
            options = info.get("privacy_level_options") or ["SELF_ONLY"]
            if privacy_level not in options:
                fallback = "SELF_ONLY" if "SELF_ONLY" in options else options[0]
                log.warning("Privacidad %s no permitida aún (opciones: %s). Uso %s.",
                            privacy_level, options, fallback)
                privacy_level = fallback
            payload = {
                "post_info": {
                    "title": caption[:2200],
                    "privacy_level": privacy_level,
                    "disable_comment": disable_comment or bool(info.get("comment_disabled")),
                    "disable_duet": disable_duet or bool(info.get("duet_disabled")),
                    "disable_stitch": disable_stitch or bool(info.get("stitch_disabled")),
                    "video_cover_timestamp_ms": 1000,
                },
                "source_info": source,
            }
            data = self._post("/post/publish/video/init/", payload)

        publish_id = data["publish_id"]
        self._upload_file(data["upload_url"], path, size, chunk, count)
        log.info("Vídeo subido a TikTok (publish_id=%s), esperando procesado...", publish_id)
        return publish_id, self.wait_status(publish_id)

    def wait_status(self, publish_id, timeout=600):
        deadline = time.time() + timeout
        status = "PROCESSING_UPLOAD"
        while time.time() < deadline:
            data = self._post("/post/publish/status/fetch/", {"publish_id": publish_id})
            status = data.get("status", status)
            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                return status
            if status == "FAILED":
                raise TikTokError(f"TikTok rechazó el vídeo: {data.get('fail_reason')}")
            time.sleep(8)
        return status
