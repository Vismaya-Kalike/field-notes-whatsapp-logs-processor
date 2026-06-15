import fs from 'node:fs';
import path from 'node:path';

export function startOutboxWatcher({ outboxDir, selfJid, sock, logger, intervalMs = 15000 }) {
  fs.mkdirSync(outboxDir, { recursive: true });

  async function drain() {
    if (!selfJid) return;
    const files = fs.readdirSync(outboxDir).filter((f) => f.endsWith('.json'));
    for (const file of files) {
      const full = path.join(outboxDir, file);
      try {
        const payload = JSON.parse(fs.readFileSync(full, 'utf-8'));
        await sock.sendMessage(selfJid, { text: payload.message });
        fs.unlinkSync(full);
        logger.info({ file }, 'outbox message sent');
      } catch (err) {
        logger.error({ err, file }, 'failed to send outbox message');
      }
    }
  }

  const timer = setInterval(drain, intervalMs);
  return () => clearInterval(timer);
}
