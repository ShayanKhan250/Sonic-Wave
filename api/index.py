"""Vercel serverless entrypoint — exposes the SonicWave FastAPI app."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Vercel's filesystem is read-only except /tmp — keep caches & any fallback
# SQLite file there. With DATABASE_URL set (Neon), SQLite is never used.
os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
os.environ.setdefault("SQLITE_PATH", "/tmp/sonicwave.db")

from main import app  # noqa: E402,F401
