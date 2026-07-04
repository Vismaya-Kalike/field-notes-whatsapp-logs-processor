import fs from 'node:fs';
import path from 'node:path';

export async function dumpRosters({ sock, chats, liveDir, logger }) {
  try {
    const groups = await sock.groupFetchAllParticipating();
    const out = {};
    for (const [jid, name] of Object.entries(chats)) {
      const g = groups[jid];
      if (!g) continue;
      out[name] = {
        jid,
        participants: (g.participants || []).map((p) => ({ id: p.id, jid: p.jid || null })),
      };
    }
    fs.mkdirSync(liveDir, { recursive: true });
    fs.writeFileSync(path.join(liveDir, 'rosters.json'), JSON.stringify(out, null, 2), 'utf-8');
    logger.info('rosters dumped for %d group(s)', Object.keys(out).length);
  } catch (err) {
    logger.warn({ err }, 'roster dump failed');
  }
}
