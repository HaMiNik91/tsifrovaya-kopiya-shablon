// Помощник «Войти через GitHub» для страницы заполнения «Цифровой копии».
// Работает на Cloudflare Workers (бесплатный тариф). Делает две вещи:
//  1) раздаёт саму страницу из папки docs (настройка "assets" в wrangler.jsonc);
//  2) меняет одноразовый код от GitHub на ключ входа и продлевает ключ.
// Секрет приложения GitHub нужен только для обмена кода (так требует GitHub) — он хранится
// в настройках Cloudflare (Variables and Secrets → GITHUB_CLIENT_SECRET), а не в хранилище.
// Сам помощник ничего не хранит: ни ключей, ни оценок. Ключ уходит в браузер человека.
//
// Пути:
//   GET  /vhod/config   → {client_id, slug} — страница узнаёт, что вход через GitHub есть
//   POST /vhod/token    ← {code, code_verifier, redirect_uri} → ключ (обмен кода, PKCE)
//   POST /vhod/refresh  ← {refresh_token} → новый ключ (ключ живёт 8 часов, обновление — 6 месяцев)
//
// Настройки (vars в wrangler.jsonc): GITHUB_CLIENT_ID, GITHUB_APP_SLUG,
// ALLOWED_ORIGINS — через запятую другие адреса страницы (например, GitHub Pages открытого шаблона).

const GH_TOKEN_URL = 'https://github.com/login/oauth/access_token';
const KEEP = ['access_token', 'expires_in', 'refresh_token', 'refresh_token_expires_in', 'token_type', 'error', 'error_description'];

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname.startsWith('/vhod/')) return vhod(req, env, url);
    return env.ASSETS.fetch(req);
  },
};

function allowedOrigins(env, url) {
  const list = String(env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim().replace(/\/+$/, '')).filter(Boolean);
  return new Set([url.origin, ...list]);
}

function reply(body, status, origin) {
  const h = {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
  };
  if (origin) Object.assign(h, {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  });
  return new Response(body == null ? null : JSON.stringify(body), {status, headers: h});
}

async function vhod(req, env, url) {
  const origin = req.headers.get('Origin');
  const okOrigins = allowedOrigins(env, url);
  // Чужие сайты не могут пользоваться помощником из браузера
  if (origin && !okOrigins.has(origin)) return reply({error: 'origin_not_allowed'}, 403, null);
  const cors = origin || null;
  const path = url.pathname;

  if (req.method === 'OPTIONS') return reply(null, 204, cors);

  if (!env.GITHUB_CLIENT_ID || !env.GITHUB_APP_SLUG) return reply({error: 'not_configured', error_description: 'В настройках помощника нет GITHUB_CLIENT_ID или GITHUB_APP_SLUG'}, 503, cors);

  if (path === '/vhod/config' && req.method === 'GET') {
    return reply({client_id: env.GITHUB_CLIENT_ID, slug: env.GITHUB_APP_SLUG, ready: !!env.GITHUB_CLIENT_SECRET}, 200, cors);
  }

  if (req.method !== 'POST' || (path !== '/vhod/token' && path !== '/vhod/refresh')) return reply({error: 'not_found'}, 404, cors);
  if (!env.GITHUB_CLIENT_SECRET) return reply({error: 'not_configured', error_description: 'В настройках помощника нет секрета GITHUB_CLIENT_SECRET'}, 503, cors);

  let input;
  try {
    const raw = await req.text();
    if (raw.length > 4096) throw new Error('big');
    input = JSON.parse(raw);
    if (!input || typeof input !== 'object') throw new Error('bad');
  } catch (e) {
    return reply({error: 'bad_request'}, 400, cors);
  }
  const str = (v, max) => typeof v === 'string' && v.length > 0 && v.length <= max ? v : null;

  const form = {client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET};
  if (path === '/vhod/token') {
    const code = str(input.code, 200), verifier = str(input.code_verifier, 200), back = str(input.redirect_uri, 500);
    if (!code) return reply({error: 'bad_request', error_description: 'нет кода'}, 400, cors);
    if (back) {
      // адрес возврата — только наша страница (тот же сайт или разрешённые адреса)
      let bo; try { bo = new URL(back).origin; } catch (e) { bo = null; }
      if (!bo || !okOrigins.has(bo)) return reply({error: 'bad_redirect'}, 400, cors);
      form.redirect_uri = back;
    }
    form.code = code;
    if (verifier) form.code_verifier = verifier;
  } else {
    const rt = str(input.refresh_token, 500);
    if (!rt) return reply({error: 'bad_request', error_description: 'нет ключа обновления'}, 400, cors);
    form.grant_type = 'refresh_token';
    form.refresh_token = rt;
  }

  let data;
  try {
    const r = await fetch(GH_TOKEN_URL, {
      method: 'POST',
      headers: {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'tsifrovaya-kopiya-vhod'},
      body: new URLSearchParams(form).toString(),
    });
    data = await r.json();
  } catch (e) {
    return reply({error: 'github_unreachable'}, 502, cors);
  }
  const out = {};
  for (const k of KEEP) if (data[k] != null) out[k] = data[k];
  return reply(out, out.access_token ? 200 : 400, cors);
}
