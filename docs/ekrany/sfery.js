// Экран «Мои сферы» (апгрейд 2, этап 3, 2026-11-25): переименовать сферу, добавить свою (с лучами), добавить луч,
// порядок на колесе, скрыть и вернуть — без Claude. Правила — CLAUDE.md, п. 4.1 и раздел 10.
// Скрыть и вернуть страница пишет сама (`скрыта` в оглавлении). Остальное — поручение строкой в `заявка`
// файла «00 Старт/Мои сферы.md» одним коммитом; выполняет его nastroyka.py в GitHub Actions (папки, файлы
// и все ссылки — одно место логики). Страница ждёт `заявка выполнена` и читает копию заново.
'use strict';
(window.EKRANY = window.EKRANY || {}).sfery = (() => {
  const MOI = '00 Старт/Мои сферы.md';
  const BAD = /[\\/:*?"<>|#^[\]·;]/;
  const st = {order: null, wait: null, last: null};

  const all = () => [...S.spheres, ...S.hidden].sort((a, b) => a.order - b.order || a.dir.localeCompare(b.dir));
  const byKod = k => all().find(s => s.kod === k);
  const crumbs = (...p) => `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span>${p.length ? `<a href="#/sfery">Мои сферы</a><span>›</span><span>${esc(p[0])}</span>` : '<span>Мои сферы</span>'}</nav>`;
  const one = v => Array.isArray(v) ? (v[0] || '') : String(v ?? '').trim();
  function check(name, what, max){ // то же правило, что в nastroyka.py (chistoe_imya)
    const v = (name || '').trim();
    if (!v) return `Напишите ${what}`;
    if (v.length > max) return `${what[0].toUpperCase() + what.slice(1)} — не длиннее ${max} знаков`;
    if (BAD.test(v) || /^\.|\.$/.test(v)) return `В названии нельзя знаки \\ / : * ? " < > | # ^ [ ] · ; и точку в начале или конце`;
    return '';
  }
  const stamp = () => { const d = new Date(), p = x => String(x).padStart(2, '0'); return `${today()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };

  // ───────── Поручение: строка в `заявка` ─────────
  function addLine(text, line){
    const m = text.match(FM); if (!m) throw new Error('у «Мои сферы» нет шапки');
    const lines = m[1].split('\n');
    let i = lines.findIndex(l => !l.startsWith(' ') && l.split(':')[0].trim() === 'заявка');
    if (i < 0){ lines.splice(1, 0, 'заявка:'); i = 1; }
    else lines[i] = 'заявка:';
    let j = i + 1; while (j < lines.length && /^\s+-\s/.test(lines[j])) j++;
    lines.splice(j, 0, `  - "${line}"`);
    return `---\n${lines.join('\n')}\n---\n` + text.slice(m[0].length);
  }
  function send(parts, message, toastText){
    const when = stamp(), line = [when, ...parts].join(' · ');
    const base = ['---', 'тип: мои сферы', 'заявка:', 'заявка выполнена:', 'статус: в работе', `обновлено: ${today()}`, '---',
      '# Мои сферы', '', '← [[Начни здесь]] · [[Колесо баланса]]', '', '## Что сделано', '', '<!-- sfery: начало -->', '<!-- sfery: конец -->', ''].join('\n');
    const op = view(MOI) == null ? {type: 'create', content: addLine(base, line)} : {type: 'fn', fn: t => addLine(t, line)};
    change(MOI, op, `Мои сферы: ${message}`);
    if (S.mode !== 'live'){ toast('Демо: изменения не сохраняются'); location.hash = '#/sfery'; return; }
    st.wait = {when, what: toastText, n: 0, late: false}; st.order = null;
    location.hash = '#/sfery'; render(); poll();
  }
  function istoriya(when){ // строка «Что сделано» для этого поручения
    const t = view(MOI) || '', a = t.indexOf('<!-- sfery: начало -->'), b = t.indexOf('<!-- sfery: конец -->');
    if (a < 0 || b < a) return '';
    const line = t.slice(a, b).split('\n').find(l => l.startsWith(`- ${when} · `));
    return line ? line.slice(`- ${when} · `.length) : '';
  }
  function poll(){ // ждём, пока GitHub Actions выполнит поручение (nastroyka.py пишет `заявка выполнена`)
    const w = st.wait; if (!w) return;
    setTimeout(async () => {
      if (st.wait !== w) return;
      try {
        if (!S.busy){
          await refreshFile(MOI);
          const done = one(readFm(view(MOI) || '')['заявка выполнена']);
          if (done && done >= w.when){ st.last = istoriya(w.when) || 'готово'; st.wait = null; start('live'); return; }
        }
      } catch(e){}
      w.n++; if (w.n === 36){ w.late = true; if (route()[0] === 'sfery') render(); } // ~3 минуты
      poll();
    }, w.n ? 5000 : 8000);
  }

  // ───────── Экраны ─────────
  function waitView(){
    const w = st.wait;
    return crumbs() + head(null, 'Меняю сферы…', w.what, null, 'сферы', '') +
      `<div class="card"><div class="bar" aria-hidden="true"><i style="width:${Math.min(95, 10 + w.n * 3)}%"></i></div>
      ${w.late ? `<p class="desc">GitHub делает это дольше обычного. Можно уйти на колесо — изменения появятся, когда вы обновите страницу.</p>
        <div class="pick"><button class="btn" data-act="sfery:ujti">На колесо</button></div>`
        : '<p class="legend">Программа на GitHub переносит файлы и исправляет ссылки — обычно меньше минуты. Страница обновится сама.</p>'}</div>`;
  }
  function list(){
    const sp = all(), vis = sp.filter(s => !s.hiddenSphere);
    const ord = st.order || vis.map(s => s.kod), moved = st.order && st.order.join() !== vis.map(s => s.kod).join();
    let h = crumbs() + head(null, 'Мои сферы', `На колесе — ${vis.length}${sp.length > vis.length ? `, скрыто — ${sp.length - vis.length}` : ''}. По умолчанию их 12, но набор — ваш`, null, 'сферы', '');
    if (st.last){ h += `<div class="note${/^не сделано/.test(st.last) ? ' err' : ''}">${esc(st.last)}</div>`; }
    h += '<div class="card"><div class="sub">Порядок на колесе</div>';
    ord.forEach((k, i) => {
      const s = byKod(k); if (!s) return;
      h += `<div class="twh" style="padding:6px 0;border-bottom:1px solid var(--line)"><span><b>${esc(s.name)}</b>${s.title && s.title !== s.name ? `<br><span class="legend">${esc(s.title)}</span>` : ''}</span>
        <span class="pick" style="margin:0;flex-wrap:nowrap">
          <button class="btn" data-act="sfery:up" data-v="${esc(k)}" ${i ? '' : 'disabled'} aria-label="Выше">↑</button>
          <button class="btn" data-act="sfery:down" data-v="${esc(k)}" ${i < ord.length - 1 ? '' : 'disabled'} aria-label="Ниже">↓</button>
          <a class="btn" href="#/sfery/imya/${encodeURIComponent(k)}">Изменить</a></span></div>`;
    });
    h += moved ? `<div class="pick"><button class="btn main" data-act="sfery:order">Сохранить порядок</button><button class="btn" data-act="sfery:reset">Отменить</button></div>` : '<p class="legend">Стрелки меняют место сферы на колесе; потом — «Сохранить порядок».</p>';
    h += '</div>';
    const hid = sp.filter(s => s.hiddenSphere);
    if (hid.length) h += `<div class="card"><div class="sub">Скрытые — не на колесе, ничего не удалено</div>${hid.map(s =>
      `<div class="twh" style="padding:6px 0"><span>${esc(s.name)}</span><button class="btn" data-act="sfery:skryt" data-id="${esc(s.dir)}" data-v="false">Вернуть</button></div>`).join('')}</div>`;
    h += `<div class="pick"><a class="btn main" href="#/sfery/novaya">Добавить свою сферу</a></div>
      <p class="legend">«Изменить» — название сферы, новый луч или «Скрыть». Скрытая сфера уходит с колеса и из среднего, но все записи и оценки остаются — её можно вернуть одним нажатием.</p>`;
    return h;
  }
  function edit(k){
    const s = byKod(k); if (!s) return crumbs('Сфера') + '<div class="note err">Такой сферы нет.</div>';
    return crumbs(s.name) + head(s.score, s.name, s.title !== s.name ? s.title : 'Название, лучи, скрыть', null, 'сфера', s.calc) +
      `<div class="card"><div class="sub">Название</div>
        <label>Короткое — так называется папка и пункт на колесе<input type="text" id="sfShort" value="${esc(s.name)}" maxlength="40" autocomplete="off"></label>
        <label>Полное — заголовок сферы<input type="text" id="sfFull" value="${esc(s.title || s.name)}" maxlength="80" autocomplete="off"></label>
        <div class="pick"><button class="btn main" data-act="sfery:rename" data-v="${esc(k)}">Переименовать</button></div>
        <p class="legend">Номер сферы (${esc(s.nn)}) остаётся: по нему программы и обновления из шаблона узнают сферу. Все ссылки на неё исправятся сами.</p></div>
      <div class="card"><div class="sub">Новый луч</div>
        <label>Название луча — часть сферы, которую хочется мерить отдельно<input type="text" id="sfLuch" maxlength="60" placeholder="например, Путешествия с друзьями" autocomplete="off"></label>
        <div class="pick"><button class="btn main" data-act="sfery:luch" data-v="${esc(k)}">Добавить луч</button></div>
        <p class="legend">Луч появится с пустой линейкой из 10 уровней: откройте его и напишите уровни своими словами (кнопка «Изменить уровень»). Сейчас лучей: ${s.rays.length}.</p></div>
      <div class="pick">${s.hiddenSphere ? `<button class="btn" data-act="sfery:skryt" data-id="${esc(s.dir)}" data-v="false">Вернуть на колесо</button>`
        : `<button class="btn" data-act="sfery:skryt" data-id="${esc(s.dir)}" data-v="true">Скрыть сферу — не моё сейчас</button>`}<a class="btn" href="#/${esc(s.nn)}">Открыть сферу</a></div>`;
  }
  function novaya(){
    return crumbs('Новая сфера') + head(null, 'Своя сфера', 'Чего не хватает в колесе — например, путешествия или служение', null, 'сферы', '') +
      `<div class="card">
        <label>Короткое название<input type="text" id="sfShort" maxlength="40" placeholder="например, Путешествия" autocomplete="off"></label>
        <label>Полное название (можно оставить пустым)<input type="text" id="sfFull" maxlength="80" placeholder="например, Путешествия и открытия" autocomplete="off"></label>
        <label>Лучи — части сферы, по одному на строку (от 1 до 12)<textarea id="sfRays" placeholder="Страны и города&#10;Походы и горы&#10;Деньги на поездки"></textarea></label>
        <div class="pick"><button class="btn main" data-act="sfery:add">Добавить сферу</button><a class="btn" href="#/sfery">Назад</a></div>
        <p class="legend">Сфера получит следующий свободный номер (${esc(String(Math.max(12, ...all().map(s => parseInt(s.kod, 10)).filter(isFinite)) + 1))}) и встанет последней на колесе. У каждого луча — пустая линейка из 10 уровней: напишите их своими словами на странице луча. Вопросов опросника у своей сферы нет — оценка сразу по линейкам.</p></div>`;
  }

  return {
    menu: {title: 'Мои сферы', order: 70, sub: () => { const n = S.spheres.length, h = S.hidden.length; return `На колесе ${n}${h ? `, скрыто ${h}` : ''} — переименовать, добавить, порядок`; }},
    need: p => p === MOI,
    view(r){
      if (st.wait) return waitView();
      if (r[0] === 'imya') return edit(r[1]);
      if (r[0] === 'novaya') return novaya();
      return list();
    },
    after(r){ if (r[0] && st.last) st.last = null; },
    act(k, b){
      if (st.wait && k !== 'ujti') return;
      const val = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
      if (k === 'ujti'){ location.hash = '#/'; return; }
      if (k === 'up' || k === 'down'){
        const ord = st.order || S.spheres.map(s => s.kod), i = ord.indexOf(b.dataset.v), j = k === 'up' ? i - 1 : i + 1;
        if (i < 0 || j < 0 || j >= ord.length) return;
        [ord[i], ord[j]] = [ord[j], ord[i]]; st.order = ord; st.last = null; render(); return;
      }
      if (k === 'reset'){ st.order = null; render(); return; }
      if (k === 'order'){ send(['порядок', st.order.join(', ')], 'порядок на колесе', 'Ставлю новый порядок на колесе'); return; }
      if (k === 'skryt'){
        const v = b.dataset.v === 'true', dir = b.dataset.id;
        change(`${SPH_DIR}/${dir}/${dir}.md`, {type: 'fm', sets: [['скрыта', v ? 'true' : 'false', 'порядок']], date: today()}, `${v ? 'Скрыта' : 'Возвращена'} сфера: ${dir}`);
        toast(v ? 'Сфера скрыта — её можно вернуть здесь же' : 'Сфера возвращена на колесо');
        st.order = null; location.hash = '#/sfery'; render(); return;
      }
      if (k === 'rename'){
        const s = byKod(b.dataset.v), sh = val('sfShort'), full = val('sfFull') || sh;
        const err = check(sh, 'короткое название', 40) || check(full, 'полное название', 80);
        if (err){ toast(err); return; }
        if (all().some(x => x !== s && x.name.toLowerCase() === sh.toLowerCase())){ toast(`Сфера «${sh}» уже есть`); return; }
        if (sh === s.name && full === (s.title || s.name)){ toast('Название не изменилось'); return; }
        send(['переименовать', s.kod, sh, full], `переименовать ${s.nn} ${s.name} → ${sh}`, `«${s.name}» → «${sh}»`); return;
      }
      if (k === 'luch'){
        const s = byKod(b.dataset.v), name = val('sfLuch'), err = check(name, 'название луча', 60);
        if (err){ toast(err); return; }
        if ([...s.rays, ...s.hiddenRays].some(r => r.name.toLowerCase() === name.toLowerCase())){ toast(`Луч «${name}» уже есть`); return; }
        send(['луч', s.kod, name], `новый луч «${name}» в сфере ${s.nn} ${s.name}`, `Добавляю луч «${name}» в сферу «${s.name}»`); return;
      }
      if (k === 'add'){
        const sh = val('sfShort'), full = val('sfFull') || sh, rays = val('sfRays').split('\n').map(x => x.trim()).filter(Boolean);
        const err = check(sh, 'короткое название', 40) || check(full, 'полное название', 80) || rays.map(x => check(x, 'название луча', 60)).find(Boolean)
          || (!rays.length ? 'Напишите хотя бы один луч' : rays.length > 12 ? 'Не больше 12 лучей — начните с главных' : '')
          || (all().some(x => x.name.toLowerCase() === sh.toLowerCase()) ? `Сфера «${sh}» уже есть` : '')
          || (new Set(rays.map(x => x.toLowerCase())).size < rays.length ? 'Два луча с одним названием' : '');
        if (err){ toast(err); return; }
        send(['добавить', sh, full, rays.join('; ')], `новая сфера «${sh}»`, `Создаю сферу «${sh}» и лучей: ${rays.length}`); return;
      }
    },
  };
})();
