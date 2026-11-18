"""Cliente mínimo de la API Helix de Twitch (solo lectura, token de aplicación)."""
import logging
import time

import requests

log = logging.getLogger(__name__)

HELIX = "https://api.twitch.tv/helix"


class Twitch:
    def __init__(self, client_id, client_secret):
        if not client_id or not client_secret:
            raise SystemExit("Faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET en .env")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_exp = 0
        self._user_cache = {}

    def _auth(self):
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = requests.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + data.get("expires_in", 3600)
        return self._token

    def _get(self, path, params):
        for attempt in range(4):
            r = requests.get(
                f"{HELIX}{path}",
                params=params,
                headers={"Client-Id": self.client_id, "Authorization": f"Bearer {self._auth()}"},
                timeout=20,
            )
            if r.status_code == 401:
                self._token = None
                continue
            if r.status_code == 429:
                reset = float(r.headers.get("Ratelimit-Reset", time.time() + 5))
                time.sleep(max(1, reset - time.time()))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()

    def user_id(self, login):
        login = login.lower()
        if login not in self._user_cache:
            data = self._get("/users", {"login": login}).get("data", [])
            if not data:
                raise ValueError(f"No existe el usuario de Twitch '{login}'")
            self._user_cache[login] = data[0]["id"]
        return self._user_cache[login]

    def game_id(self, name):
        data = self._get("/games", {"name": name}).get("data", [])
        if not data:
            raise ValueError(
                f"Twitch no tiene la categoría '{name}'. Revisa el nombre exacto en twitch.tv/directory"
            )
        return data[0]["id"]

    def clips(self, started_at, ended_at, broadcaster_id=None, game_id=None, max_items=100):
        """Devuelve clips creados por los espectadores en esa ventana de tiempo."""
        params = {
            "started_at": started_at,
            "ended_at": ended_at,
            "first": 100,
        }
        if broadcaster_id:
            params["broadcaster_id"] = broadcaster_id
        elif game_id:
            params["game_id"] = game_id
        else:
            raise ValueError("Hace falta broadcaster_id o game_id")

        out = []
        while len(out) < max_items:
            data = self._get("/clips", params)
            out.extend(data.get("data", []))
            cursor = data.get("pagination", {}).get("cursor")
            if not cursor:
                break
            params["after"] = cursor
        return out[:max_items]
