import nodemailer from 'nodemailer';

export async function sendLogoutEmail(reason) {
  const to = process.env.ALERT_EMAIL_TO;
  if (!to || !process.env.SMTP_HOST) {
    console.error('Email not configured; logout reason:', reason);
    return;
  }
  const transport = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 587),
    secure: process.env.SMTP_SECURE === 'true',
    auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
  });
  await transport.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to,
    subject: 'Vika WhatsApp bridge logged out — re-scan QR needed',
    text: `The WhatsApp bridge session ended (${reason}). SSH/exec into the bridge and re-scan the QR from the logs.`,
  });
}
