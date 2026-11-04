// Проверка worker/idei.js (форма «Предложить идею») без сети: Turnstile и GitHub подменены.
//   node .github/scripts/proverka_idei.mjs
// Проверяется: подпись ключом приложения GitHub (PKCS#1 и PKCS#8), настройки, отказ чужому сайту, неполные данные,
// робот (Turnstile отказал), карточка через приложение и через запасной ключ, метки, ничего лишнего в тексте.
import {generateKeyPairSync, createVerify} from 'node:crypto';
import {idei, appJwt} from '../../worker/idei.js';
import vhod from '../../worker/vhod.js';

let bad = 0;
const ok = (c, m) => { if (c) console.log('✓ ' + m); else { bad++; console.log('✖ ' + m); } };
const {privateKey, publicKey} = generateKeyPairSync('rsa', {modulusLength: 2048});
const pem1 = privateKey.export({type: 'pkcs1', format: 'pem'}), pem8 = privateKey.export({type: 'pkcs8', format: 'pem'});

for (const [n, pem] of [['PKCS#1', pem1], ['PKCS#8', pem8]]){
  const jwt = await appJwt('12345', pem, 1700000000);
  const [h, b, s] = jwt.split('.');
  const v = createVerify('RSA-SHA256'); v.update(`${h}.${b}`);
  const sig = Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
  const body = JSON.parse(Buffer.from(b, 'base64url').toString());
  ok(v.verify(publicKey, sig) && body.iss === '12345' && body.exp - body.iat === 600, `подпись ключом приложения (${n})`);
}

// подменённая сеть
let calls = [], turnstileOk = true;
globalThis.fetch = async (u, o = {}) => {
  u = String(u); calls.push({u, o});
  const j = (d, s = 200) => new Response(JSON.stringify(d), {status: s, headers: {'Content-Type': 'application/json'}});
  if (u.includes('turnstile/v0/siteverify')) return j({success: turnstileOk});
  if (u.endsWith('/repos/HaMiNik91/tsifrovaya-kopiya-shablon/installation')) return j({id: 77});
  if (u.endsWith('/app/installations/77/access_tokens')) return j({token: 'ghs_inst'});
  if (u.endsWith('/repos/HaMiNik91/tsifrovaya-kopiya-shablon/issues')) return j({number: 42}, 201);
  return j({message: 'не подменено ' + u}, 404);
};
const SITE = 'https://tsifrovaya-kopiya.example.workers.dev';
const env = {TURNSTILE_SITEKEY: '0x4AAA', TURNSTILE_SECRET: 'sec', IDEI_REPO: 'HaMiNik91/tsifrovaya-kopiya-shablon', IDEI_APP_ID: '12345', IDEI_APP_KEY: pem1,
  GITHUB_CLIENT_ID: 'x', GITHUB_APP_SLUG: 'y', ASSETS: {fetch: async () => new Response('страница')}};
const post = (body, origin = SITE, e = env) => vhod.fetch(new Request(SITE + '/idei', {method: 'POST', headers: {'Origin': origin, 'Content-Type': 'application/json', 'CF-Connecting-IP': '1.2.3.4'}, body: JSON.stringify(body)}), e);

let r = await vhod.fetch(new Request(SITE + '/idei/config', {headers: {Origin: SITE}}), env);
let d = await r.json();
ok(r.status === 200 && d.sitekey === '0x4AAA' && d.ready === true, 'настройки формы');
r = await vhod.fetch(new Request(SITE + '/idei/config'), {...env, TURNSTILE_SECRET: ''}); d = await r.json();
ok(d.ready === false, 'без секрета Turnstile форма «не готова»');
r = await post({vid: 'идея', text: 'Хочу тёмную тему', token: 't'}, 'https://chuzhoy.example');
ok(r.status === 403, 'чужой сайт — отказ');
r = await post({vid: 'спам', text: 'Хочу тёмную тему', token: 't'});
ok(r.status === 400, 'неизвестный вид — отказ');
r = await post({vid: 'идея', text: 'коротко', token: 't'});
ok(r.status === 400, 'слишком короткий текст — отказ');
turnstileOk = false; calls = [];
r = await post({vid: 'идея', text: 'Хочу тёмную тему на телефоне', token: 't'});
ok(r.status === 403 && !calls.some(c => c.u.includes('/issues')), 'робот: Turnstile отказал — карточки нет');
turnstileOk = true; calls = [];
r = await post({vid: 'ошибка', text: 'Не сохраняется оценка\nпосле входа с телефона', token: 'tok', versiya: '1.4'}); d = await r.json();
const iss = calls.find(c => c.u.endsWith('/issues')), ib = iss && JSON.parse(iss.o.body);
const ts = calls.find(c => c.u.includes('siteverify'));
ok(r.status === 200 && d.number === 42, 'карточка создана (приложение GitHub)');
ok(iss && iss.o.headers.Authorization === 'token ghs_inst', 'писали ключом установки приложения');
ok(ib && ib.title === 'Ошибка: Не сохраняется оценка' && ib.labels[0] === 'ошибка' && ib.body.includes('версия копии 1.4'), 'заголовок, метка, версия');
ok(ib && !ib.body.includes('1.2.3.4') && ts && ts.o.body.get('remoteip') === '1.2.3.4' && ts.o.body.get('response') === 'tok', 'IP — только в Turnstile, не в карточку');
calls = [];
r = await post({vid: 'идея', text: 'Хочу тёмную тему на телефоне', token: 't'}, SITE, {...env, IDEI_APP_ID: '', IDEI_APP_KEY: '', IDEI_TOKEN: 'github_pat_x'});
const iss2 = calls.find(c => c.u.endsWith('/issues'));
ok(r.status === 200 && iss2.o.headers.Authorization === 'token github_pat_x' && !calls.some(c => c.u.includes('installation')), 'запасной ключ IDEI_TOKEN');
r = await vhod.fetch(new Request(SITE + '/index.html'), env);
ok(await r.text() === 'страница', 'страница по-прежнему отдаётся');
console.log(bad ? `Не прошло: ${bad}` : 'Все проверки прошли.');
process.exit(bad ? 1 : 0);
