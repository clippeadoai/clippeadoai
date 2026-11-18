import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    broadcaster TEXT,
    title TEXT,
    url TEXT,
    views INTEGER,
    vod_id TEXT,
    vod_offset INTEGER,
    created_at TEXT,
    status TEXT,          -- ready | uploaded | failed | skipped
    output_path TEXT,
    caption TEXT,
    publish_id TEXT,
    error TEXT,
    updated REAL
);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id TEXT,
    ts REAL
);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def seen(self, clip_id):
        return self.conn.execute("SELECT 1 FROM clips WHERE id=?", (clip_id,)).fetchone() is not None

    def near_duplicate(self, vod_id, vod_offset, window):
        """¿Ya tenemos un clip del mismo VOD en ese mismo momento? (la gente clipea lo mismo varias veces)"""
        if not vod_id or vod_offset is None:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM clips WHERE vod_id=? AND vod_offset IS NOT NULL AND ABS(vod_offset-?)<=?",
            (vod_id, vod_offset, window),
        ).fetchone()
        return row is not None

    def add(self, clip, status, **fields):
        self.conn.execute(
            """INSERT OR REPLACE INTO clips
               (id, broadcaster, title, url, views, vod_id, vod_offset, created_at,
                status, output_path, caption, publish_id, error, updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                clip["id"], clip.get("broadcaster_name"), clip.get("title"), clip.get("url"),
                clip.get("view_count"), clip.get("video_id") or None, clip.get("vod_offset"),
                clip.get("created_at"), status, fields.get("output_path"), fields.get("caption"),
                fields.get("publish_id"), fields.get("error"), time.time(),
            ),
        )
        self.conn.commit()

    def update(self, clip_id, **fields):
        fields["updated"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE clips SET {cols} WHERE id=?", (*fields.values(), clip_id))
        self.conn.commit()

    def next_ready(self):
        # Primero el clip con más views de entre los listos
        return self.conn.execute(
            "SELECT * FROM clips WHERE status='ready' ORDER BY views DESC, updated ASC LIMIT 1"
        ).fetchone()

    def log_upload(self, clip_id):
        self.conn.execute("INSERT INTO uploads (clip_id, ts) VALUES (?,?)", (clip_id, time.time()))
        self.conn.commit()

    def uploads_last_24h(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM uploads WHERE ts > ?", (time.time() - 86400,)
        ).fetchone()[0]

    def last_upload_ts(self):
        row = self.conn.execute("SELECT MAX(ts) FROM uploads").fetchone()
        return row[0] or 0

    def counts(self):
        return dict(self.conn.execute("SELECT status, COUNT(*) FROM clips GROUP BY status").fetchall())

    def recent(self, limit=15):
        return self.conn.execute(
            "SELECT * FROM clips ORDER BY updated DESC LIMIT ?", (limit,)
        ).fetchall()
