# 🚀 SonicWave — Deploy to Render + Neon (100% free, step-by-step)

Everything in this folder is **already prepared and fully tested** against a real
PostgreSQL database. You only need to click through the steps below — no code
changes, no terminal commands.

**What you end up with**

| Piece | Service | Cost |
|---|---|---|
| App (API + website) | Render (free web service) | $0 |
| Database (permanent) | Neon (free Postgres, 0.5 GB) | $0 |

The same code runs on SQLite automatically when `DATABASE_URL` is not set, so
nothing breaks locally.

---

## Step 1 — Create the free database on Neon (≈2 minutes)

1. Go to **https://neon.tech** → **Sign up** (use "Continue with GitHub" — fastest).
2. It asks you to create a project. Enter:
   - Project name: `sonicwave`
   - Postgres version: leave default
   - Region: pick the one closest to you (e.g. **AWS Asia Pacific (Singapore)**)
   - Click **Create project**.
3. You land on the project dashboard. Find the **Connection string** box
   (sometimes behind a **Connect** button).
4. Make sure the dropdown shows **Postgres** (a plain connection string, *not*
   "psql" and *not* "Pooled" vs "Direct" matters little — either works).
5. Click the **copy** icon. The string looks like:

   ```
   postgresql://neondb_owner:AbC123xyz@ep-cool-sky-a1b2c3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

6. **Paste it somewhere safe** (Notepad). You need it in Step 3.

> That's all for Neon. The app creates all tables and seed data by itself on
> first start — you never have to touch SQL.

---

## Step 2 — Put the code on GitHub (≈3 minutes, no git needed)

1. Go to **https://github.com/new**.
2. Repository name: `sonicwave` → keep it **Public** (or Private, both work) →
   click **Create repository**.
3. On the empty-repo page click the link **"uploading an existing file"**.
4. Unzip `sonicwave-render.zip` on your computer, then **drag ALL the files and
   folders inside it** (main.py, db.py, data.py, requirements.txt, render.yaml,
   Dockerfile, the `static` folder, …) into the GitHub upload box.
   - Important: drag the *contents*, not the outer folder, so `main.py` sits at
     the top level of the repo.
5. Click **Commit changes** and wait for the upload to finish.

---

## Step 3 — Deploy on Render (≈4 minutes)

1. Go to **https://render.com** → **Sign up** → choose **"GitHub"** so Render
   can see your repos.
2. Click **New +** (top right) → **Web Service**.
3. Pick your **sonicwave** repository → **Connect**.
4. Render reads `render.yaml` and pre-fills everything. Check these values:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance type:** **Free**
5. Scroll to **Environment Variables** → **Add Environment Variable**:
   - Key: `DATABASE_URL`
   - Value: *paste the Neon connection string from Step 1*
6. Click **Deploy Web Service** (or **Create Web Service**).
7. Wait 2–5 minutes while it builds. When the log says
   `Application startup complete` and the status turns **Live**, click the URL
   at the top — something like:

   ```
   https://sonicwave.onrender.com
   ```

   🎉 That's your site — login wall, accounts, likes, playlists, lyrics,
   charts, recommendations — all stored permanently in Neon.

---

## Step 4 — Two small finishing touches

1. **reCAPTCHA** — the invisible security check activates automatically on
   `*.onrender.com`, but Google must know your domain:
   - Open https://www.google.com/recaptcha/admin → select your site key →
     **Settings → Domains** → add `sonicwave.onrender.com` (your actual
     Render hostname) → Save.
   - Until you add it, logins still work — the app safely skips the check if
     Google rejects the domain.
2. **Keep it awake (optional)** — free Render services sleep after 15 minutes
   idle (first visit after sleep takes ~40 s to wake). To avoid that:
   - Sign up free at https://cron-job.org → **Create cronjob** →
     URL: `https://YOUR-APP.onrender.com/api/health` (or just `/`) →
     schedule: every **10 minutes** → Save.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails on `psycopg` | Make sure `requirements.txt` was uploaded and contains `psycopg[binary]>=3.1`. |
| "Application startup" never completes | Check the `DATABASE_URL` value — it must start with `postgresql://` and be the full string copied from Neon. |
| Site loads but login says "Security check failed" | Add your Render domain in the reCAPTCHA admin console (Step 4.1). |
| First visit very slow | Free instance waking from sleep — normal; use the cron-job pinger. |
| Want to update the site later | Edit/replace files in your GitHub repo (web editor or re-upload) — Render redeploys automatically on every commit. |

## How the database switching works (FYI)

- `DATABASE_URL` set → the app talks to Neon/Postgres (psycopg 3), creates the
  schema (`SCHEMA_PG`), seeds the catalog + demo account, and fixes the ID
  sequences automatically.
- `DATABASE_URL` absent → it uses a local `sonicwave.db` SQLite file, exactly
  as before.
- Demo account on a fresh database: **demo / demo123**.
