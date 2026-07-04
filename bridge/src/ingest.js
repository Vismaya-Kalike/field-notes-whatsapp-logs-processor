import cron from 'node-cron';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export function startIngestScheduler({ logger }) {
  const cronExpr = process.env.INGEST_CRON || '0 2 * * *';
  const timezone = process.env.INGEST_TZ || 'Asia/Kolkata';
  const extraArgs = (process.env.INGEST_ARGS || '').split(' ').filter(Boolean);

  if (!cron.validate(cronExpr)) {
    throw new Error(`invalid INGEST_CRON: ${cronExpr}`);
  }

  let running = false;

  function runIngest(reason) {
    if (running) {
      logger.warn('ingest already running; skipping trigger (%s)', reason);
      return;
    }
    running = true;
    logger.info('ingest starting (%s): ingest_live.py %s', reason, extraArgs.join(' '));

    const child = spawn('uv', ['run', 'python', 'ingest_live.py', ...extraArgs], {
      cwd: REPO_ROOT,
      env: process.env,
    });
    child.stdout.on('data', (d) => logger.info('[ingest] %s', d.toString().trimEnd()));
    child.stderr.on('data', (d) => logger.info('[ingest] %s', d.toString().trimEnd()));
    child.on('close', (code) => {
      running = false;
      logger.info('ingest finished (exit %d)', code);
    });
    child.on('error', (err) => {
      running = false;
      logger.error({ err }, 'ingest failed to spawn');
    });
  }

  cron.schedule(cronExpr, () => runIngest('schedule'), { timezone });
  logger.info('ingest scheduler armed: "%s" (%s)', cronExpr, timezone);

  if (process.env.INGEST_ON_START === 'true') {
    setTimeout(() => runIngest('startup'), 5000);
  }

  return runIngest;
}
