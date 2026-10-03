---
title: SonicWave
emoji: 🎵
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# SonicWave 🎵

Full music streaming web app — accounts, likes, playlists, synced lyrics,
charts and recommendations. FastAPI backend + single-page frontend.

- Set a **Secret** named `DATABASE_URL` (Settings → Variables and secrets)
  with your Neon Postgres connection string for permanent storage.
- Without it, the app falls back to a local SQLite file (wiped on rebuild).
- Demo account on a fresh database: **demo / demo123**.
