import fs from 'node:fs';
import path from 'node:path';
import { downloadMediaMessage } from '@whiskeysockets/baileys';
import { formatLines } from './format.js';
import { slugify } from './config.js';

const IMG_EXT = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif' };

function chatDir(liveDir, chatName) {
  const dir = path.join(liveDir, slugify(chatName));
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function appendLines(dir, lines) {
  fs.appendFileSync(path.join(dir, '_chat.txt'), lines.join('\n') + '\n', 'utf-8');
}

function mediaFilename(ts, mime) {
  const ext = IMG_EXT[mime];
  if (!ext) return null;
  const y = ts.getFullYear();
  const m = String(ts.getMonth() + 1).padStart(2, '0');
  const d = String(ts.getDate()).padStart(2, '0');
  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();
  return `IMG-${y}${m}${d}-WA${rand}.${ext}`;
}

export async function storeMessage({ liveDir, chatName, ts, sender, text, imageMessage, sock, logger }) {
  const dir = chatDir(liveDir, chatName);

  let attachmentFilename = null;
  if (imageMessage) {
    attachmentFilename = mediaFilename(ts, imageMessage.mimetype);
    if (attachmentFilename) {
      try {
        const buffer = await downloadMediaMessage(
          { message: { imageMessage } }, 'buffer', {},
          { logger, reuploadRequest: sock.updateMediaMessage },
        );
        fs.writeFileSync(path.join(dir, attachmentFilename), buffer);
      } catch (err) {
        logger.error({ err }, 'media download failed');
        attachmentFilename = null;
      }
    }
  }

  appendLines(dir, formatLines({ ts, sender, text, attachmentFilename }));
}
