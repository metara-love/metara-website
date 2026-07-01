/**
 * METARA Contact Form — Cloudflare Worker
 * Receives form submissions from metara.co.za and sends formatted email via Resend.
 *
 * Deploy with: wrangler deploy
 * Requires: RESEND_API_KEY secret, and TO_EMAIL / FROM_EMAIL vars (see wrangler.toml)
 */
const ENABLE_RATE_LIMIT = false;
const ALLOWED_ORIGIN = 'https://metara.co.za'; // update if using www. or different domain

export default {
  async fetch(request, env, ctx) {
    // ── CORS PREFLIGHT ──
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    if (request.method !== 'POST') {
      return jsonResponse({ error: 'Method not allowed' }, 405);
    }

    // ── PARSE & VALIDATE ──
    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return jsonResponse({ error: 'Invalid JSON' }, 400);
    }

    const { intent, name, email, location, fields, wantsWhatsapp, whatsappPhone } = payload;

    if (!intent || !name || !email || !fields) {
      return jsonResponse({ error: 'Missing required fields' }, 400);
    }

    // basic email format check
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return jsonResponse({ error: 'Invalid email address' }, 400);
    }

    // ── RATE LIMITING (simple IP-based, using Cloudflare KV) ──
    const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
    if (ENABLE_RATE_LIMIT && env.RATE_LIMIT_KV) {
      const rateLimitKey = `rl:${clientIP}`;
      const recent = await env.RATE_LIMIT_KV.get(rateLimitKey);
      if (recent && parseInt(recent) >= 100) {
        return jsonResponse({ error: 'Too many submissions. Please try again later.' }, 429);
      }
      const count = recent ? parseInt(recent) + 1 : 1;
      await env.RATE_LIMIT_KV.put(rateLimitKey, String(count), { expirationTtl: 3600 }); // 1 hour window
    }

    // ── BUILD EMAIL CONTENT ──
    const fieldsHtml = Object.entries(fields)
      .filter(([_, v]) => v && v.trim())
      .map(([label, value]) => `
        <tr>
          <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#9A9A9A;font-size:13px;vertical-align:top;width:220px;">${escapeHtml(label)}</td>
          <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#E8E4D8;font-size:14px;">${escapeHtml(value).replace(/\n/g, '<br>')}</td>
        </tr>`)
      .join('');

    const emailHtml = `
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0A0E1A;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto;padding:32px 16px;">
    <tr><td>
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-family:Georgia,serif;font-size:24px;letter-spacing:4px;color:#C8A96E;">METARA</span>
      </div>
      <div style="background:#0D1530;border:1px solid #2A2A2A;border-radius:4px;overflow:hidden;">
        <div style="background:#C8A96E;padding:14px 20px;">
          <span style="color:#0A0E1A;font-weight:bold;font-size:15px;letter-spacing:1px;">${escapeHtml(intent.toUpperCase())} — New Contact Form Submission</span>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#9A9A9A;font-size:13px;vertical-align:top;width:220px;">Name</td>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#E8E4D8;font-size:14px;font-weight:bold;">${escapeHtml(name)}</td>
          </tr>
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#9A9A9A;font-size:13px;vertical-align:top;">Email</td>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#E8E4D8;font-size:14px;"><a href="mailto:${escapeHtml(email)}" style="color:#7FC3E8;">${escapeHtml(email)}</a></td>
          </tr>
          ${location ? `<tr>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#9A9A9A;font-size:13px;vertical-align:top;">Location</td>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#E8E4D8;font-size:14px;">${escapeHtml(location)}</td>
          </tr>` : ''}
          ${wantsWhatsapp ? `<tr>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#9A9A9A;font-size:13px;vertical-align:top;">WhatsApp Community</td>
            <td style="padding:10px 16px;border-bottom:1px solid #2A2A2A;color:#25D366;font-size:14px;font-weight:bold;">Yes — ${escapeHtml(whatsappPhone)}</td>
          </tr>` : ''}
          ${fieldsHtml}
        </table>
      </div>
      <p style="text-align:center;color:#666;font-size:11px;margin-top:20px;">
        Submitted ${new Date().toUTCString()} · METARA Contact Form
      </p>
    </td></tr>
  </table>
</body>
</html>`;

    const emailText = `METARA — ${intent} submission\n\nName: ${name}\nEmail: ${email}\n${location ? 'Location: ' + location + '\n' : ''}${wantsWhatsapp ? 'WhatsApp Community: Yes — ' + whatsappPhone + '\n' : ''}\n` +
      Object.entries(fields).filter(([_, v]) => v && v.trim()).map(([k, v]) => `${k}: ${v}`).join('\n');

    // ── SEND VIA RESEND ──
    try {
      const resendRes = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.RESEND_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: env.FROM_EMAIL,           // e.g. "METARA Website <noreply@metara.co.za>"
          to: env.TO_EMAIL,               // e.g. "love@metara.co.za"
          reply_to: email,                // lets you hit "reply" and respond directly to the visitor
          subject: `[${intent}] New message from ${name}`,
          html: emailHtml,
          text: emailText,
        }),
      });

      if (!resendRes.ok) {
        const errBody = await resendRes.text();
        console.error('Resend error:', errBody);
        console.error("Returning 502 to browser");
        return jsonResponse({ error: 'Failed to send email' }, 502);
      }

    } catch (err) {
      console.error('Worker error:', err);
      return jsonResponse({ error: 'Internal error' }, 500);
    }
	console.log("Returning success to browser");
    return jsonResponse({ success: true });
  },
};

// ── HELPERS ──

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders(),
    },
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
