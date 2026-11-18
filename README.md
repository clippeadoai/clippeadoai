# 🎮 GTA Clipper — Twitch → TikTok en automático

Lo dejas encendido y él solo:

1. **Busca** cada 30 min los clips de GTA VI que los espectadores han creado en Twitch de tus streamers (los más vistos = los mejores momentos).
2. **Quita duplicados**: si 5 personas clipearon el mismo momento, se queda con uno.
3. **Descarga** el clip y lo **pasa a vertical 1080×1920** (fondo desenfocado o facecam arriba + gameplay abajo).
4. Le pone **subtítulos grandes estilo TikTok** (Whisper, en local y gratis) y el **crédito `twitch.tv/streamer`**.
5. **Lo sube a TikTok** con caption y hashtags, respetando un máximo diario y un tiempo mínimo entre vídeos para que no te marquen como spam.

---

## 1. Instalación (una vez)

Necesitas **Python 3.10+** y **ffmpeg**.

- Windows: `winget install Gyan.FFmpeg` y `winget install Python.Python.3.12`
- Mac: `brew install ffmpeg python`

```bash
cd gta-clipper
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

## 2. Claves de Twitch (5 min, gratis)

1. Entra en https://dev.twitch.tv/console/apps → **Register Your Application**
2. Nombre: lo que quieras · OAuth Redirect URL: `http://localhost` · Categoría: *Application Integration*
3. Copia **Client ID**, genera un **Client Secret** y ponlos en `.env`.

## 3. App de TikTok (lo más lento: la revisión de TikTok tarda unos días)

1. https://developers.tiktok.com → crea una cuenta de developer → **Manage apps → Connect an app**.
2. Añade los productos **Login Kit** y **Content Posting API** (activa *Direct Post*).
3. Permisos: `user.info.basic`, `video.upload`, `video.publish`.
4. Configura un **Redirect URI** (en Login Kit). Ponlo exactamente igual en `.env` como `TIKTOK_REDIRECT_URI`.
5. Copia **Client key** y **Client secret** en `.env`.
6. Conecta tu cuenta:

```bash
python -m clipper auth
```

Se abre TikTok → aceptas → copias la URL a la que te redirige y la pegas en la terminal. Listo, se renueva sola.

### ⚠️ Lo que TikTok exige (importante)

| Estado de tu app | Qué pasa al subir |
|---|---|
| **Sin auditar** (al principio) | Los vídeos se publican en **privado** (`SELF_ONLY`). Tú solo cambias a "Todos" con un toque. Puede que TikTok te pida que la cuenta sea privada mientras pruebas. |
| **Auditada** (pides la revisión en el portal de TikTok) | Pon `privacy_level: PUBLIC_TO_EVERYONE` en `config.yaml` y es **100 % automático**. |

Pide la auditoría pronto. Explica que es una herramienta para publicar en tu propia cuenta clips editados con crédito al creador.

## 4. Configura tus streamers

Edita `config.yaml`:

```yaml
streamers:
  - login: ibai
    layout: blur
  - login: auronplay
    layout: split
    facecam: [0.0, 0.0, 0.25, 0.30]   # dónde está su cámara (x, y, ancho, alto en %)
```

Para ajustar la facecam de un streamer: descarga un clip suyo y prueba:

```bash
python -m clipper test-edit clip.mp4 --layout split
```

Mira el resultado en `output/TEST_...mp4` y ajusta los números.

**¿Quieres probarlo ya, antes de que salga GTA VI?** Pon `game: "Grand Theft Auto V"` y lanza un ciclo.

## 5. Uso

```bash
python -m clipper doctor     # comprueba que todo está bien
python -m clipper run        # un ciclo manual (para probar)
python -m clipper daemon     # 🔁 modo automático: déjalo encendido
python -m clipper status     # qué ha procesado y subido
```

Los vídeos editados quedan en `output/` (con su caption en un `.txt`) y el log en `data/clipper.log`.

### Dejarlo 24/7

- **En tu PC**: deja abierta la terminal con `python -m clipper daemon`. En Windows también puedes crear una tarea en el *Programador de tareas* que lo arranque al iniciar sesión.
- **En un VPS** (Hetzner o Contabo, unos 5 €/mes): `nohup python -m clipper daemon &` o un servicio systemd. Sin GPU usa `model: small` o `base` para los subtítulos.

## Ajustes útiles

| Opción | Qué hace |
|---|---|
| `mode: game` | En vez de tu lista, coge los clips más virales de GTA VI de **todo** Twitch |
| `min_views` | Sube el valor para quedarte solo con los momentos más bestias |
| `max_uploads_per_day` | 3-8 al día va bien. Más suele penalizar el alcance |
| `tiktok.mode: draft` | Manda los vídeos a tus borradores de TikTok para revisarlos antes |
| `subtitles.model` | `small` va bien en CPU. `medium` o `large-v3` si tienes una GPU NVIDIA |

## ⚖️ Derechos y normas (léelo, te ahorra baneos)

- El contenido es de los streamers. Lo más seguro y rentable es **unirte a los programas de clipping oficiales**: muchos streamers pagan por views a sus clippers (busca "*nombre* clipping" o programas en Whop o Discord). Así tienes permiso y además cobras.
- Pon siempre el crédito (la app lo hace sola) y no subas streams enteros.
- TikTok penaliza el contenido "no original" reposteado tal cual. Los subtítulos, el formato vertical y unos buenos títulos ayudan. Revisa de vez en cuando qué funciona.
- Si un streamer te pide que pares, quítalo de la lista.
