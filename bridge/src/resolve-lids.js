import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  Browsers,
  DisconnectReason,
} from '@whiskeysockets/baileys';
import fs from 'node:fs';
import path from 'node:path';
import pino from 'pino';

const logger = pino({ level: 'silent' });
const AUTH_DIR = process.env.AUTH_DIR || path.resolve(process.cwd(), 'auth_info');
const CONFIG_PATH = process.env.BRIDGE_CONFIG || path.resolve(process.cwd(), 'config.json');
const FACILITATORS_JSON = process.argv[2] || process.env.FACILITATORS_JSON;
const REPORT_PATH = process.env.REPORT_PATH || path.resolve(process.cwd(), 'lid_report.json');

if (!FACILITATORS_JSON) {
  console.error('usage: node src/resolve-lids.js <facilitators.json>');
  process.exit(1);
}

const digits = (v) => String(v || '').split('@')[0].split(':')[0].replace(/\D/g, '');
const maskNum = (v) => digits(v).replace(/\d(?=\d{2})/g, '*');

const facilitators = JSON.parse(fs.readFileSync(FACILITATORS_JSON, 'utf-8')).filter((f) => f.contact_number);
const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
const allowlistedJids = new Set(Object.keys(config.chats || {}));
const numberToFacilitator = new Map(facilitators.map((f) => [digits(f.contact_number), f]));

async function run(sock) {
  const groups = await sock.groupFetchAllParticipating();

  const jidToName = {};
  const matchedNumbers = new Set();
  const unknownMembers = [];
  const groupSizes = {};

  for (const g of Object.values(groups)) {
    if (!allowlistedJids.has(g.id)) continue;
    const participants = g.participants || [];
    groupSizes[g.subject] = participants.length;

    for (const p of participants) {
      const num = digits(p.jid || p.id);
      const fac = numberToFacilitator.get(num);
      if (fac) {
        jidToName[p.id] = fac.name;
        matchedNumbers.add(num);
      } else {
        unknownMembers.push({ group: g.subject, lid: p.id, phone: maskNum(p.jid) });
      }
    }
  }

  const facilitatorsNotInGroups = facilitators
    .filter((f) => !matchedNumbers.has(digits(f.contact_number)))
    .map((f) => f.name);

  config.jidToName = { ...(config.jidToName || {}), ...jidToName };
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2) + '\n', 'utf-8');

  const report = {
    facilitators_total: facilitators.length,
    mapped_in_allowlisted_groups: Object.keys(jidToName).length,
    facilitators_not_found_in_groups: facilitatorsNotInGroups,
    unknown_members_count: unknownMembers.length,
    unknown_members: unknownMembers,
    group_roster_sizes: groupSizes,
  };
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2) + '\n', 'utf-8');

  console.log('=== LID resolution (phone-jid match) ===');
  console.log(`facilitators with numbers:            ${report.facilitators_total}`);
  console.log(`mapped inside allowlisted groups:     ${report.mapped_in_allowlisted_groups}`);
  console.log(`facilitators NOT found in any group:  ${facilitatorsNotInGroups.length}${facilitatorsNotInGroups.length ? ' -> ' + facilitatorsNotInGroups.join(', ') : ''}`);
  console.log(`unknown members (non-facilitators):   ${unknownMembers.length}`);
  console.log('per group roster size:', groupSizes);
  console.log(`\nconfig.json jidToName updated. Full report: ${REPORT_PATH}`);
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({ version, auth: state, logger, browser: Browsers.macOS('Chrome') });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async (u) => {
    if (u.connection === 'open') {
      try {
        await run(sock);
        process.exit(0);
      } catch (err) {
        console.error('resolve failed:', err?.message || err);
        process.exit(1);
      }
    }
    if (u.connection === 'close') {
      const code = u.lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        console.error('logged out — re-link first');
        process.exit(1);
      }
    }
  });
}

start().catch((err) => {
  console.error('startup failed:', err?.message || err);
  process.exit(1);
});
