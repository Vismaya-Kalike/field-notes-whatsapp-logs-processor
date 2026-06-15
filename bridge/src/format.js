function pad(n) {
  return String(n).padStart(2, '0');
}

function stamp(ts) {
  const dd = pad(ts.getDate());
  const mm = pad(ts.getMonth() + 1);
  const yy = pad(ts.getFullYear() % 100);
  const hh = pad(ts.getHours());
  const min = pad(ts.getMinutes());
  return `${dd}/${mm}/${yy}, ${hh}:${min}`;
}

export function formatLines({ ts, sender, text, attachmentFilename }) {
  const head = `${stamp(ts)} - ${sender}:`;
  const caption = (text || '').trim();

  if (attachmentFilename) {
    const lines = [`${head} ${attachmentFilename} (file attached)`];
    if (caption) lines.push(caption);
    return lines;
  }
  return [`${head} ${caption}`];
}
