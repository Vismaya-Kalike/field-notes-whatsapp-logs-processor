import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
} from '@whiskeysockets/baileys';
import path from 'node:path';
import pino from 'pino';
import qrcode from 'qrcode-terminal';

const logger = pino({ level: 'silent' });
const AUTH_DIR = process.env.AUTH_DIR || path.resolve(process.cwd(), 'auth_info');

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const sock = makeWASocket({ auth: state, logger, printQRInTerminal: false });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) qrcode.generate(qr, { small: true });
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) start();
      else { console.error('Logged out — delete auth_info and re-run to re-link.'); process.exit(1); }
    }
    if (connection === 'open') {
      console.log('\nConnected. Fetching groups...\n');
      const groups = await sock.groupFetchAllParticipating();
      const entries = Object.values(groups);
      if (entries.length === 0) console.log('(no groups found)');
      for (const g of entries) {
        console.log(`GROUP  ${g.id}`);
        console.log(`  subject: ${g.subject}`);
        const parts = (g.participants || []).map((p) => p.id);
        console.log(`  participants (${parts.length}): ${parts.join(', ')}`);
        console.log('');
      }
      console.log('Copy the GROUP ids you want into config.json "chats", and the participant');
      console.log('ids into "jidToName" mapped to facilitator names. Then Ctrl-C.');
      process.exit(0);
    }
  });
}

start().catch((err) => {
  console.error('list-chats failed:', err);
  process.exit(1);
});
