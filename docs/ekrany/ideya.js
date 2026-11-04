// Экран «Предложить идею» (апгрейд 5.1): без входа; пожелание или ошибка → карточка в Issues открытого шаблона
// (помощник Cloudflare, worker/idei.js). От роботов — Cloudflare Turnstile. Карточки видны всем — личного не писать.
'use strict';
(window.EKRANY = window.EKRANY || {}).ideya = (() => {
  const base = () => OAUTH.replace(/\/vhod$/, '') + '/idei';   // OAUTH — из основного скрипта (он грузится позже)
  const st = {cfg: undefined, vid: 'идея', token: '', sent: null, busy: false, widget: null, err: ''};
  async function config(){
    try {
      const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 4000);
      const r = await fetch(`${base()}/config`, {cache: 'no-store', signal: ctl.signal}); clearTimeout(t);
      st.cfg = r.ok ? await r.json() : null;
    } catch(e){ st.cfg = null; }
    if (route()[0] === 'ideya') render();
  }
  function mountTurnstile(){ // виджет «я не робот»: скрипт Cloudflare грузится только на этом экране
    const box = document.getElementById('ts'); if (!box || !st.cfg || !st.cfg.sitekey) return;
    const go = () => { st.token = ''; st.widget = window.turnstile.render(box, {sitekey: st.cfg.sitekey, language: 'ru', theme: 'auto',
      callback: t => { st.token = t; const b = document.getElementById('ideaSend'); if (b) b.disabled = false; },
      'expired-callback': () => { st.token = ''; }, 'error-callback': () => { st.token = ''; }}); };
    if (window.turnstile) return go();
    window.onTurnstile = go;
    if (!document.getElementById('tsScript')){
      const s = document.createElement('script'); s.id = 'tsScript'; s.async = true;
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onTurnstile';
      document.head.appendChild(s);
    }
  }
  async function send(){
    const ta = document.getElementById('ideaText'), text = (ta.value || '').trim();
    if (text.length < 10){ toast('Напишите чуть подробнее — хотя бы одно предложение'); return; }
    if (!st.token){ toast('Дождитесь проверки «я не робот»'); return; }
    st.busy = true; const b = document.getElementById('ideaSend'); b.disabled = true; b.textContent = 'Отправляю…';
    let d = {};
    try {
      const v = S.files && view('00 Старт/Что нового.md'), versiya = v ? String(readFm(v)['версия'] || '') : '';
      const r = await fetch(base(), {method: 'POST', cache: 'no-store', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({vid: st.vid, text, token: st.token, versiya})});
      d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) throw new Error(d.error_description || d.error || `ошибка ${r.status}`);
      st.sent = {number: d.number, vid: st.vid}; st.err = '';
    } catch(e){
      st.err = e.message; st.saved = text;
    }
    st.busy = false; st.token = ''; render();
  }
  function screen(){
    const [o, n] = CFG.template.split('/'), issues = `https://github.com/${o}/${n}/issues`;
    let h = `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Предложить идею</span></nav>`;
    h += head(null, 'Предложить идею', 'Что улучшить в «Цифровой копии» или что работает не так', null, 'идея', '');
    if (st.sent) return h + `<div class="step"><b class="t">Спасибо! Получено № ${esc(st.sent.number)}</b>
      <p class="desc" style="color:inherit">${st.sent.vid === 'ошибка' ? 'Ошибку посмотрят и исправят в следующей версии.' : 'Когда идею сделают, она появится на странице «Что нового».'} Все пожелания видны здесь: <a href="${issues}" target="_blank" rel="noopener">${esc(issues)}</a></p>
      <div class="pick"><button class="btn" data-act="ideya:new">Написать ещё</button><a class="btn" href="#/">К колесу</a></div></div>`;
    if (S.mode === 'embedded') return h + `<div class="note">Это демо: форма работает на странице заполнения.</div>`;
    if (st.cfg === undefined) return h + `<div class="center">Проверяю форму…</div>`;
    if (!st.cfg || !st.cfg.ready) return h + `<div class="note">Форма пока не настроена. Пожелание можно оставить на GitHub: <a href="${issues}/new" target="_blank" rel="noopener">${esc(issues)}/new</a></div>`;
    if (st.err) h += `<div class="note err">Не отправилось: ${esc(st.err)}. Текст сохранён — попробуйте ещё раз.</div>`;
    return h + `<div class="card">
      <div class="pick" role="group" aria-label="Что это">${['идея', 'ошибка'].map(v => `<button class="btn ${st.vid === v ? 'on' : ''}" data-act="ideya:vid" data-v="${v}">${v === 'идея' ? 'Идея или пожелание' : 'Что-то не работает'}</button>`).join('')}</div>
      <label>Что предложить или что случилось<textarea id="ideaText" maxlength="3000" placeholder="Например: хочу видеть на колесе, как оценки менялись за год">${esc(st.saved || '')}</textarea></label>
      <div class="note"><b>Не пишите личного</b> — имени, почты, здоровья, оценок. Пожелания видны всем на GitHub. Ответ не придёт: что сделано — смотрите в «Что нового».</div>
      <div id="ts"></div>
      <div class="pick"><button class="btn main" id="ideaSend" data-act="ideya:send" disabled>Отправить</button></div></div>`;
  }
  return {
    free: true,   // открыт и без входа
    menu: {title: 'Предложить идею', order: 95, sub: 'Что улучшить или что работает не так — без входа'},
    view(){ return screen(); },
    after(){ if (st.cfg === undefined){ config(); return; } if (!st.sent) mountTurnstile(); },
    act(a, b){
      if (a === 'vid'){ st.vid = b.dataset.v; for (const x of b.parentNode.children) x.classList.toggle('on', x === b); return; } // без перерисовки: виджет остаётся
      if (a === 'send'){ if (!st.busy) send(); return; }
      if (a === 'new'){ st.sent = null; st.saved = ''; render(); return; }
    },
  };
})();
