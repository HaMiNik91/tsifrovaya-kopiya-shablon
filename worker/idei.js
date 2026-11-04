// Форма «Предложить идею» (апгрейд 5.1): пожелание или ошибка со страницы → карточка в Issues открытого шаблона.
// Без входа; от роботов — Cloudflare Turnstile (проверка на сервере, secret — только в настройках Cloudflare).
// Писать в Issues можно двумя способами (что настроено — то и работает):
//   1) приложение GitHub только для идей (права — Issues: Read and write, поставлено только на шаблон):
//      IDEI_APP_ID (vars) + IDEI_APP_KEY (secret, закрытый ключ .pem) — ключ не истекает, автор карточки — бот;
//   2) запасной: IDEI_TOKEN (secret) — fine-grained ключ на шаблон с правом Issues: Read and write.
// Пути:
//   GET  /idei/config → {sitekey, ready}
//   POST /idei        ← {vid, text, token} → {ok, number}
// Настройки (vars): TURNSTILE_SITEKEY, IDEI_REPO ("владелец/шаблон"), IDEI_APP_ID; секреты: TURNSTILE_SECRET, IDEI_APP_KEY или IDEI_TOKEN.
// Ничего не хранит; адрес IP человека уходит только в Turnstile (так проверяется робот) и в карточку не пишется.

const VIDY = {'идея': 'идея', 'ошибка': 'ошибка'};
const MAX = 3000;

function json(body, status, origin){
  const h = {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'};
  if (origin) Object.assign(h, {'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type', 'Vary': 'Origin'});
  return new Response(body == null ? null : JSON.stringify(body), {status, headers: h});
}

// ───── Ключ приложения GitHub: .pem (PKCS#1 или PKCS#8) → подпись RS256 ─────
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const b64uStr = s => b64u(new TextEncoder().encode(s));
function derLen(n){ if (n < 128) return [n]; const b = []; while (n){ b.unshift(n & 255); n >>= 8; } return [0x80 | b.length, ...b]; }
function pkcs1to8(der){ // PrivateKeyInfo { version 0, AlgorithmIdentifier rsaEncryption, OCTET STRING (ключ PKCS#1) }
  const alg = [0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00];
  const oct = [0x04, ...derLen(der.length), ...der];
  const body = [0x02, 0x01, 0x00, ...alg, ...oct];
  return new Uint8Array([0x30, ...derLen(body.length), ...body]);
}
export async function appKey(pem){
  const pkcs1 = /BEGIN RSA PRIVATE KEY/.test(pem);
  const raw = Uint8Array.from(atob(pem.replace(/-----[^-]+-----/g, '').replace(/\s+/g, '')), c => c.charCodeAt(0));
  return crypto.subtle.importKey('pkcs8', pkcs1 ? pkcs1to8(raw) : raw, {name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256'}, false, ['sign']);
}
export async function appJwt(appId, pem, now = Math.floor(Date.now() / 1000)){
  const head = b64uStr(JSON.stringify({alg: 'RS256', typ: 'JWT'}));
  const body = b64uStr(JSON.stringify({iat: now - 60, exp: now + 540, iss: String(appId)}));
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', await appKey(pem), new TextEncoder().encode(`${head}.${body}`));
  return `${head}.${body}.${b64u(sig)}`;
}
async function gh(url, token, opts = {}, scheme = 'token'){
  const r = await fetch('https://api.github.com' + url, {...opts, headers: {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'tsifrovaya-kopiya-idei', 'Authorization': `${scheme} ${token}`, ...(opts.body ? {'Content-Type': 'application/json'} : {})}});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(d.message || `GitHub ${r.status}`), {status: r.status});
  return d;
}
async function issuesToken(env){
  if (env.IDEI_APP_ID && env.IDEI_APP_KEY){
    const jwt = await appJwt(env.IDEI_APP_ID, env.IDEI_APP_KEY);
    const inst = await gh(`/repos/${env.IDEI_REPO}/installation`, jwt, {}, 'Bearer');
    return (await gh(`/app/installations/${inst.id}/access_tokens`, jwt, {method: 'POST'}, 'Bearer')).token;
  }
  if (env.IDEI_TOKEN) return env.IDEI_TOKEN;
  return null;
}
const ready = env => !!(env.TURNSTILE_SITEKEY && env.TURNSTILE_SECRET && env.IDEI_REPO && ((env.IDEI_APP_ID && env.IDEI_APP_KEY) || env.IDEI_TOKEN));

export async function idei(req, env, url, okOrigins){
  const origin = req.headers.get('Origin');
  if (origin && !okOrigins.has(origin)) return json({error: 'origin_not_allowed'}, 403, null);
  const cors = origin || null;
  if (req.method === 'OPTIONS') return json(null, 204, cors);
  if (url.pathname === '/idei/config' && req.method === 'GET') return json({sitekey: env.TURNSTILE_SITEKEY || null, ready: ready(env)}, 200, cors);
  if (url.pathname !== '/idei' || req.method !== 'POST') return json({error: 'not_found'}, 404, cors);
  if (!ready(env)) return json({error: 'not_configured', error_description: 'Форма ещё не настроена'}, 503, cors);

  let input;
  try { const raw = await req.text(); if (raw.length > 12000) throw 0; input = JSON.parse(raw); } catch(e){ return json({error: 'bad_request'}, 400, cors); }
  const vid = VIDY[input && input.vid], text = typeof input.text === 'string' ? input.text.replace(/\r\n/g, '\n').trim() : '';
  if (!vid || text.length < 10 || text.length > MAX || typeof input.token !== 'string' || input.token.length > 4096)
    return json({error: 'bad_request', error_description: `Нужен вид и текст от 10 до ${MAX} знаков`}, 400, cors);

  // робот или человек — спрашиваем Cloudflare (токен одноразовый)
  const form = new FormData();
  form.append('secret', env.TURNSTILE_SECRET); form.append('response', input.token);
  const ip = req.headers.get('CF-Connecting-IP'); if (ip) form.append('remoteip', ip);
  let ts;
  try { ts = await (await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {method: 'POST', body: form})).json(); }
  catch(e){ return json({error: 'turnstile_unreachable'}, 502, cors); }
  if (!ts.success) return json({error: 'turnstile_failed', error_description: 'Проверка «я не робот» не прошла — попробуйте ещё раз'}, 403, cors);

  const first = text.split('\n').find(l => l.trim()) || text;
  const title = (vid === 'ошибка' ? 'Ошибка: ' : 'Идея: ') + (first.length > 80 ? first.slice(0, 77).trim() + '…' : first.trim());
  const ver = typeof input.versiya === 'string' && /^\d+(\.\d+)*$/.test(input.versiya) ? input.versiya : '';
  const body = `${text}\n\n---\n*Прислано через «Предложить идею» на странице заполнения${ver ? `, версия копии ${ver}` : ''}. Без входа и без данных об отправителе.*`;
  try {
    const token = await issuesToken(env);
    const issue = await gh(`/repos/${env.IDEI_REPO}/issues`, token, {method: 'POST', body: JSON.stringify({title, body, labels: [vid]})});
    return json({ok: true, number: issue.number}, 200, cors);
  } catch(e){
    return json({error: 'github_failed', error_description: e.message}, 502, cors);
  }
}
