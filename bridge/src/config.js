import fs from 'node:fs';
import path from 'node:path';

const LIVE_DIR = process.env.LIVE_DIR || path.resolve(process.cwd(), '../data/live');
const OUTBOX_DIR = process.env.OUTBOX_DIR || path.join(LIVE_DIR, 'outbox');
const AUTH_DIR = process.env.AUTH_DIR || path.resolve(process.cwd(), 'auth_info');
const CONFIG_PATH = process.env.BRIDGE_CONFIG || path.resolve(process.cwd(), 'config.json');

export function loadConfig() {
  const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
  return {
    chats: raw.chats || {},
    jidToName: raw.jidToName || {},
    liveDir: LIVE_DIR,
    outboxDir: OUTBOX_DIR,
    authDir: AUTH_DIR,
    selfJid: process.env.SELF_WHATSAPP_JID || null,
  };
}

export function slugify(name) {
  return name.replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_|_$/g, '');
}
