# Bridge Deployment Runbook (Railway)

## Services
1. **bridge** (persistent service)
   - Dockerfile: `Dockerfile.bridge`
   - Volume mounted at `/app/data/live` AND `/app/bridge/auth_info`
     (use two mount paths on one volume, or one volume per path).
   - Env: `SELF_WHATSAPP_JID`, `LIVE_DIR=/app/data/live`,
     `OUTBOX_DIR=/app/data/live/outbox`, `AUTH_DIR=/app/bridge/auth_info`,
     `BRIDGE_CONFIG=/app/bridge/config.json`,
     `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `ALERT_EMAIL_TO`.
   - `config.json`: commit a real one as a Railway file mount or bake via a config var.

2. **ingest** (cron job)
   - Dockerfile: `Dockerfile.ingest`
   - Schedule: `0 2 * * *` (02:00 daily).
   - Same volume mounted at `/app/data/live`.
   - Env: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `AWS_ACCESS_KEY_ID`,
     `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`, `OPENAI_API_KEY`,
     `LIVE_DIR=/app/data/live`, `OUTBOX_DIR=/app/data/live/outbox`.

## First run
1. Deploy **bridge**. Open its logs.
2. A QR code renders. On your phone: WhatsApp → Settings → Linked Devices → Link a device → scan.
3. Log shows `bridge connected`. Send a test message in a facilitator group;
   confirm a line appears in the volume (`/app/data/live/<slug>/_chat.txt`).
4. Deploy **ingest** cron. Trigger it once manually; verify notes land in Supabase
   and the handbook updates.

## Getting group JIDs
Temporarily set `LOG_LEVEL=debug` and log `m.key.remoteJid` in `messages.upsert`,
send a message in each target group, copy the `...@g.us` ids into `config.json`.

## Re-linking after logout
If you get the logout email: open the bridge logs, a fresh QR will be printing
(the service auto-restarts and waits). Re-scan from the phone.

## Watermark reset (re-ingest a window)
Edit/delete `/app/data/live/<slug>/.watermark` on the volume, then trigger the
ingest cron. Deleting it re-ingests the whole `_chat.txt` (will duplicate notes —
only do this on a fresh chat or after clearing those notes).
