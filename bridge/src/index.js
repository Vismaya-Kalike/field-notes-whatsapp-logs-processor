import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} from '@whiskeysockets/baileys';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import { loadConfig } from './config.js';
import { storeMessage } from './chatStore.js';
import { startOutboxWatcher } from './outbox.js';
import { sendLogoutEmail } from './email.js';
import { recordSender } from './senders.js';
import { startIngestScheduler } from './ingest.js';

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const cfg = loadConfig();

function extractText(message) {
  return (
    message?.conversation ||
    message?.extendedTextMessage?.text ||
    message?.imageMessage?.caption ||
    ''
  );
}

function toDate(messageTimestamp) {
  const seconds =
    typeof messageTimestamp === 'number'
      ? messageTimestamp
      : Number(messageTimestamp?.toNumber ? messageTimestamp.toNumber() : messageTimestamp);
  return new Date(seconds * 1000);
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(cfg.authDir);
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    browser: Browsers.macOS('Chrome'),
    printQRInTerminal: false,
  });

  startOutboxWatcher({ outboxDir: cfg.outboxDir, selfJid: cfg.selfJid, sock, logger });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) qrcode.generate(qr, { small: true });
    if (connection === 'open') logger.info('bridge connected');
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        logger.error('logged out — re-scan QR required');
        await sendLogoutEmail('loggedOut');
      } else {
        logger.warn({ code }, 'connection closed, reconnecting');
        start();
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const m of messages) {
      const jid = m.key?.remoteJid;
      const chatName = cfg.chats[jid];
      if (!chatName) continue;

      const participant = m.key?.participant || m.participant || jid;
      const pushName = m.pushName || null;
      const sender = cfg.jidToName[participant] || pushName || participant;
      const ts = toDate(m.messageTimestamp);
      const text = extractText(m.message);
      const imageMessage = m.message?.imageMessage || null;

      recordSender({ liveDir: cfg.liveDir, chat: chatName, participant, pushName });

      await storeMessage({
        ...cfg,
        chatName,
        ts,
        sender,
        text,
        imageMessage,
        sock,
        logger,
      });
    }
  });
}

startIngestScheduler({ logger });

start().catch((err) => {
  logger.error({ err }, 'bridge crashed');
  process.exit(1);
});
