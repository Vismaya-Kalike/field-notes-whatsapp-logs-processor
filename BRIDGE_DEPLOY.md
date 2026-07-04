# Bridge Deployment Runbook (Railway)

The bridge and the incremental ingester run as **one Railway service**. Railway
attaches a volume to a single service, so a persistent bridge and a separate cron
service cannot share the volume the ingester needs. Instead, the always-on bridge
schedules the ingest itself via `node-cron` (see `bridge/src/ingest.js`).

- **Project:** `tranquil-freedom` · **Environment:** `production` · **Service:** `field-notes-bridge`
- **Image:** `Dockerfile.combined` (Node 20 + uv-managed Python 3.11 in one image)
- **Volume:** one volume mounted at `/app/data` (holds `auth_info/`, `live/`, `live/outbox/`)

## Environment variables

Config (the group allowlist + `lid → facilitator name` map):
- `BRIDGE_CONFIG_JSON` — the full contents of `bridge/config.json` as a JSON string.
  `loadConfig()` prefers this over the file, so the gitignored `config.json` never
  ships. (Locally, omit it and the file is used.)

Paths (all under the one volume):
- `LIVE_DIR=/app/data/live`
- `OUTBOX_DIR=/app/data/live/outbox`
- `AUTH_DIR=/app/data/auth_info`  ← session lives here, so linking survives restarts

Build:
- `RAILWAY_DOCKERFILE_PATH=Dockerfile.combined`

Ingest schedule (defaults shown; override only if needed):
- `INGEST_CRON=0 2 * * *`  ·  `INGEST_TZ=Asia/Kolkata`
- `INGEST_ARGS` — optional extra flags for `ingest_live.py` (e.g. `--skip-ai`)
- `INGEST_ON_START=true` — optional, run one ingest ~5s after boot (deploy verification)

Pipeline secrets (consumed by the Python ingester):
- `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  `AWS_REGION`, `S3_BUCKET_NAME`, `OPENAI_API_KEY`
- optional: `AI_CLASSIFICATION_MODEL`, `AI_COMMENTARY_MODEL`, `AI_BATCH_SIZE`

Logging:
- `LOG_LEVEL` — the bridge's own logs (default `info`)
- `WA_LOG_LEVEL` — Baileys' internal logs (default `warn`; Baileys is very chatty at `info`)

Alerts (optional):
- `SELF_WHATSAPP_JID` — your number as `<number>@s.whatsapp.net`, for unmatched-sender
  self-messages via the outbox
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `ALERT_EMAIL_TO` —
  for the session-logout email

## Deploying

```bash
railway link --project tranquil-freedom      # once per machine
railway up --no-gitignore                     # from scripts/ (repo root)
```

**`--no-gitignore` is required.** The repo `.gitignore` contains `*.json`, and
`railway up` applies it at upload time — silently dropping `bridge/package.json`
from the build context (git still *tracks* it, so this is easy to miss). The
`.railwayignore` file excludes only real junk and secrets, so uploads stay clean
without the `*.json` rule.

## First-run QR

```bash
railway logs        # a QR renders in the deploy logs; it rotates every ~30–60s
```
On your phone: WhatsApp → Settings → Linked Devices → Link a device → scan.
Expect `code 408` (QR expiry) / `code 515` (post-pair stream restart) — both are
normal Baileys steps. Success looks like `opened connection to WA` → `bridge connected`.
Because `AUTH_DIR` is on the volume, you only scan once.

## Discovering groups & mapping facilitators

1. `AUTH_DIR=auth_info node bridge/src/list-chats.js` — links and prints every group's
   `...@g.us` id + participant ids. Put the target groups into `config.json` → `chats`.
2. Dump facilitators (`id, name, contact_number`) to a JSON file, then
   `node bridge/src/resolve-lids.js <facilitators.json>` — matches each group member's
   phone `jid` (from the roster) to a facilitator `contact_number` and writes
   `lid → name` into `config.json` → `jidToName`.
3. Push the updated config: set the `BRIDGE_CONFIG_JSON` variable to the new
   `config.json` contents (a redeploy picks it up).

Anyone not pre-mapped still gets recorded by `pushName`, and the ingester's
unmatched-sender alert surfaces them so you can add the mapping.

## Manual / verification ingest

The daily run happens in-container at `INGEST_CRON`. To run it on demand:
```bash
railway ssh "cd /app && uv run python ingest_live.py --dry-run --skip-ai"   # safe preview
railway ssh "cd /app && uv run python ingest_live.py"                        # real run
```

Message-capture caveat: WhatsApp only pushes **other** participants' messages to a
linked device (`messages.upsert` type `notify`). A message sent from the linked
phone itself is not captured, so test with a facilitator's phone, not the linked one.

## Re-linking after logout

If the session ends (logout email, or `logged out` in the logs), open `railway logs`;
the service auto-restarts and prints a fresh QR. Re-scan from the phone.

## Watermark reset (re-ingest a window)

Each chat tracks a `.watermark` file under `/app/data/live/<slug>/`. The ingester only
processes messages strictly newer than it, so runs are idempotent. To re-ingest, edit
or delete that file (via `railway ssh`), then trigger a manual ingest. Deleting it
re-ingests the whole `_chat.txt` and will duplicate notes — only do this on a fresh
chat or after clearing those notes.
