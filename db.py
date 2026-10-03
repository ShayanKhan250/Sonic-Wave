"""SonicWave database layer — SQLite by default, PostgreSQL (e.g. Neon) when DATABASE_URL is set."""

import hashlib
import os
import re as _re
import secrets
import sqlite3

DB_PATH = os.environ.get("SQLITE_PATH") or os.path.join(os.path.dirname(__file__), "sonicwave.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row
    IntegrityErrors = (sqlite3.IntegrityError, psycopg.errors.UniqueViolation, psycopg.errors.IntegrityError)
else:
    IntegrityErrors = (sqlite3.IntegrityError,)


# ---------- PostgreSQL compatibility shim ----------
# main.py speaks the sqlite3 dialect ("?" params, INSERT OR IGNORE/REPLACE, cur.lastrowid).
# This shim translates all of it so the exact same code runs on Neon/Postgres.

_UPSERT_KEYS = {
    "likes": ("user_id", "song_id"),
    "liked_tracks": ("user_id", "track_id"),
    "user_playlist_tracks": ("playlist_id", "track_id"),
    "playlist_songs": ("playlist_id", "song_id"),
    "tokens": ("token",),
}
_RETURNING_ID_TABLES = {"users", "playlists", "user_playlists", "queue_items", "plays"}


def _pg_sql(sql: str):
    s = sql.replace("?", "%s")
    want_id = False
    m = _re.match(r"\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+(\w+)\s*\(([^)]*)\)", s, _re.I)
    if m:
        verb, table = m.group(1).upper(), m.group(2).lower()
        cols = [c.strip() for c in m.group(3).split(",")]
        keys = _UPSERT_KEYS.get(table)
        s = _re.sub(r"INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", s, count=1, flags=_re.I)
        if keys:
            upd = [c for c in cols if c.lower() not in keys]
            if verb == "REPLACE" and upd:
                s += f" ON CONFLICT ({', '.join(keys)}) DO UPDATE SET " + ", ".join(f"{c}=EXCLUDED.{c}" for c in upd)
            else:
                s += f" ON CONFLICT ({', '.join(keys)}) DO NOTHING"
        else:
            s += " ON CONFLICT DO NOTHING"
        return s, want_id
    m2 = _re.match(r"\s*INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)", s, _re.I)
    if m2 and m2.group(1).lower() in _RETURNING_ID_TABLES and "returning" not in s.lower():
        cols = [c.strip().lower() for c in m2.group(2).split(",")]
        if "id" not in cols:
            s += " RETURNING id"
            want_id = True
    return s, want_id


class _PgCursor:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, n=1):
        return self._cur.fetchmany(n)


class _PgConn:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        s, want_id = _pg_sql(sql)
        cur = self._conn.execute(s, params)
        last = None
        if want_id:
            row = cur.fetchone()
            last = row["id"] if row else None
        return _PgCursor(cur, last)

    def executescript(self, script):
        self._conn.execute(script)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db():
    if IS_PG:
        return _PgConn(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    genre TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    followers INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    genre TEXT NOT NULL,
    tracks INTEGER NOT NULL DEFAULT 0,
    year INTEGER NOT NULL,
    tag TEXT
);

CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    album_id INTEGER NOT NULL REFERENCES albums(id),
    genre TEXT NOT NULL,
    duration TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    plays INTEGER NOT NULL DEFAULT 0,
    chart_rank INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    avatar TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    description TEXT NOT NULL DEFAULT '',
    mood TEXT,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL = SonicWave official
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_songs (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, song_id)
);

CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, song_id)
);

CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS liked_tracks (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, track_id)
);

CREATE TABLE IF NOT EXISTS user_playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    cover TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES user_playlists(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    pos INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    played_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS artists (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    genre TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    followers BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS albums (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id BIGINT NOT NULL REFERENCES artists(id),
    genre TEXT NOT NULL,
    tracks INT NOT NULL DEFAULT 0,
    year INT NOT NULL,
    tag TEXT
);
CREATE TABLE IF NOT EXISTS songs (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id BIGINT NOT NULL REFERENCES artists(id),
    album_id BIGINT NOT NULL REFERENCES albums(id),
    genre TEXT NOT NULL,
    duration TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    plays BIGINT NOT NULL DEFAULT 0,
    chart_rank INT
);
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    avatar TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_username_nocase ON users (LOWER(username));
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS playlists (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🎵',
    description TEXT NOT NULL DEFAULT '',
    mood TEXT,
    owner_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS playlist_songs (
    playlist_id BIGINT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    position INT NOT NULL,
    PRIMARY KEY (playlist_id, song_id)
);
CREATE TABLE IF NOT EXISTS likes (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, song_id)
);
CREATE TABLE IF NOT EXISTS queue_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL REFERENCES songs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS liked_tracks (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, track_id)
);
CREATE TABLE IF NOT EXISTS user_playlists (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    cover TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_playlist_tracks (
    playlist_id BIGINT NOT NULL REFERENCES user_playlists(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    pos INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (playlist_id, track_id)
);
CREATE TABLE IF NOT EXISTS plays (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL,
    title TEXT, artist TEXT, album TEXT, img TEXT, url TEXT, duration TEXT,
    played_at TIMESTAMPTZ DEFAULT now()
);
"""


# ---------- password / token helpers ----------

def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def create_user(conn: sqlite3.Connection, username: str, password: str, display_name: str | None = None):
    salt = secrets.token_hex(16)
    cur = conn.execute(
        "INSERT INTO users (username, display_name, password_hash, salt) VALUES (?, ?, ?, ?)",
        (username, display_name or username, hash_password(password, salt), salt),
    )
    conn.commit()
    return cur.lastrowid


def verify_user(conn: sqlite3.Connection, username: str, password: str):
    row = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    if row and secrets.compare_digest(row["password_hash"], hash_password(password, row["salt"])):
        return row
    return None


def issue_token(conn: sqlite3.Connection, user_id: int) -> str:
    token = "sw_" + secrets.token_hex(24)
    conn.execute("INSERT INTO tokens (token, user_id) VALUES (?, ?)", (token, user_id))
    conn.commit()
    return token


def user_from_token(conn: sqlite3.Connection, token: str):
    return conn.execute(
        """SELECT u.* FROM tokens t JOIN users u ON u.id = t.user_id WHERE t.token = ?""",
        (token,),
    ).fetchone()


# ---------- seeding ----------

def _migrate(conn):
    """Idempotent column additions so existing databases (SQLite file or live Neon)
    upgrade themselves automatically on startup."""
    for tbl, col, typ in (("users", "avatar", "TEXT"), ("user_playlists", "cover", "TEXT")):
        try:
            if IS_PG:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {typ}")
            else:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass  # column already exists (SQLite has no IF NOT EXISTS for columns)


def seed():
    import data

    conn = get_db()
    conn.executescript(SCHEMA_PG if IS_PG else SCHEMA)
    _migrate(conn)

    if conn.execute("SELECT COUNT(*) c FROM songs").fetchone()["c"] > 0:
        conn.close()
        return  # already seeded

    for a in data.ARTISTS:
        conn.execute(
            "INSERT INTO artists (id, name, genre, emoji, followers) VALUES (?, ?, ?, ?, ?)",
            (a["id"], a["name"], a["genre"], a["emoji"], a["followers"]),
        )
    for al in data.ALBUMS:
        conn.execute(
            "INSERT INTO albums (id, title, artist_id, genre, tracks, year, tag) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (al["id"], al["title"], al["artist_id"], al["genre"], al["tracks"], al["year"], al["tag"]),
        )
    for s in data.SONGS:
        conn.execute(
            "INSERT INTO songs (id, title, artist_id, album_id, genre, duration, emoji, plays, chart_rank)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (s["id"], s["title"], s["artist_id"], s["album_id"], s["genre"],
             s["duration"], s["emoji"], s["plays"], s["chart_rank"]),
        )

    # catalog is in — commit it before the guarded sections below so a skipped
    # section can never roll the catalog back
    conn.commit()

    # demo account owns the "You" playlists and the classic liked songs.
    # Guarded: if a users row already exists (partially-initialised database),
    # skip the demo account instead of crashing the whole seed.
    try:
        demo_salt = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO users (id, username, display_name, password_hash, salt) VALUES (1, 'demo', 'Demo Listener', ?, ?)",
            (hash_password("demo123", demo_salt), demo_salt),
        )
        for sid in data.LIKED_SONG_IDS:
            conn.execute("INSERT INTO likes (user_id, song_id) VALUES (1, ?)", (sid,))
        conn.commit()
    except IntegrityErrors:
        try:
            conn.rollback()
        except Exception:
            pass

    try:
        for p in data.PLAYLISTS:
            owner = None if p["creator"] == "SonicWave" else 1
            conn.execute(
                "INSERT INTO playlists (id, name, emoji, description, mood, owner_id) VALUES (?, ?, ?, ?, ?, ?)",
                (p["id"], p["name"], p["emoji"], p["description"], p["mood"], owner),
            )
            for pos, sid in enumerate(p["song_ids"], 1):
                conn.execute(
                    "INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)",
                    (p["id"], sid, pos),
                )
        conn.commit()
    except IntegrityErrors:
        try:
            conn.rollback()
        except Exception:
            pass

    if IS_PG:
        # explicit-id seed rows don't advance Postgres sequences — fix them so the
        # next INSERT without an id can never collide
        for tbl in ("users", "playlists"):
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{tbl}','id'), "
                f"GREATEST((SELECT COALESCE(MAX(id),1) FROM {tbl}), 1))"
            )

    conn.commit()
    conn.close()
    print("Database seeded ✔")


if __name__ == "__main__":
    seed()
