// Экран «Анкета» (апгрейд 2, этап 2, 2026-11-25): знакомство при первом входе и «Обо мне» — те же вопросы,
// ответы можно поменять. Правила — CLAUDE.md, п. 5.2 «Профиль» и раздел 10.
// Страница пишет ТОЛЬКО «00 Старт/Профиль.md» — одним коммитом, вместе с `анкета пройдена` (дата и время).
// Всё остальное (модули, набор, скрыть луч «Совместная жизнь», приоритеты сфер, валюта) делает программа
// nastroyka.py в GitHub Actions — одно место логики. Страница ждёт `анкета применена` = `анкета пройдена`,
// загружает копию заново и ведёт в опросник. Пропуск вопроса оставляет прежний ответ — ничего не затирается.
'use strict';
(window.EKRANY = window.EKRANY || {}).anketa = (() => {
  const NAB = '80 Шаблоны/Наборы/';
  const isNab = p => p.startsWith(NAB) && /^Набор — .+\.md$/.test(p.slice(NAB.length));
  const one = v => Array.isArray(v) ? (v[0] || '') : String(v ?? '').trim();
  const list = v => (Array.isArray(v) ? v : (v ? [v] : [])).map(x => String(x).trim()).filter(Boolean);
  const SOB = [['переезд', 'Переезд'], ['новый питомец', 'Новый питомец'], ['ребёнок', 'Ребёнок'], ['нет', 'Нет']];
  const ETAP = ['учёба', 'работа', 'своё дело', 'декрет', 'пенсия'];
  const CHASY = ['1', '2', '3', '5', '7', '10'];
  const st = {i: 0, a: null, wait: null};

  const pfm = () => readFm(view(PROFIL) || '');
  const passed = () => !!one(pfm()['анкета пройдена']);
  const age = god => { const y = parseInt(god, 10); return isFinite(y) ? new Date().getFullYear() - y : null; };
  const allSph = () => [...S.spheres, ...S.hidden].sort((a, b) => a.order - b.order || a.dir.localeCompare(b.dir));
  const sn = (kod, def) => `«${(allSph().find(s => s.kod === kod) || {}).name || def}»`; // название сферы по коду: владелец мог переименовать
  function nabor(name){ // набор: скрытые сферы (коды)
    const t = view(`${NAB}Набор — ${name}.md`); if (t == null) return null;
    return {name, hidden: list(readFm(t)['скрытые сферы'])};
  }

  function load(){ // черновик ответов — из «Профиля» и того, что уже настроено в копии
    const fm = pfm(), mods = list(fm['модули']), was = passed();
    const prio = list(fm['приоритеты']).length ? list(fm['приоритеты'])
      : allSph().filter(s => s.prio != null).sort((a, b) => a.prio - b.prio).map(s => s.kod);
    const a = {imya: one(fm['имя']), god: one(fm['год рождения']), pol: one(fm['пол']), strana: one(fm['страна']),
      para: one(fm['пара']), deti: one(fm['дети']), zdor: one(fm['ограничения здоровья']), etap: one(fm['этап жизни']),
      chasy: one(fm['часов в неделю']), sob: one(fm['событие']), nabor: one(fm['набор']) || 'Полный', prio: prio.slice(0, 3),
      tsikl: mods.includes('Цикл') ? 'да' : (was ? 'нет' : ''), pit: mods.includes('Питомцы') ? 'да' : (was ? 'нет' : ''), mods};
    if (!a.para){ const r = allSph().flatMap(s => s.hiddenRays).find(r => r.kod === '06.04'); if (r) a.para = 'нет'; }
    return a;
  }
  const A = () => st.a || (st.a = load());

  function steps(){
    const a = A(), out = ['intro', 'imya', 'god', 'pol'];
    if (a.pol === 'женский') out.push('tsikl');
    out.push('strana', 'para', 'deti', 'pit', 'zdor', 'etap', 'chasy', 'sob', 'nabor', 'prio', 'itog');
    return out;
  }
  const go = i => { st.i = Math.max(0, Math.min(i, steps().length - 1)); render(); scrollTo(0, 0); };

  // ───────── Экран ─────────
  function card(inner){
    const all = steps(), i = Math.min(st.i, all.length - 1);
    return `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>${passed() ? 'Обо мне' : 'Анкета'}</span></nav>` +
      `<div class="sub">${i && i < all.length - 1 ? `Вопрос ${i} из ${all.length - 2}` : (passed() ? 'Обо мне' : 'Знакомство')}</div>` +
      `<div class="bar" aria-hidden="true"><i style="width:${Math.round(i / (all.length - 1) * 100)}%"></i></div>` + inner;
  }
  const nav = (i, noSkip) => `<div class="pick">${noSkip ? '' : `<button class="btn" data-act="anketa:go" data-i="${i + 1}">Пропустить</button>`}${i > 0 ? `<button class="btn" data-act="anketa:go" data-i="${i - 1}">Назад</button>` : ''}</div>`;
  const opts = (k, items, cur) => `<div class="pick">${items.map(([v, t]) => `<button class="btn ${cur === v ? 'on' : ''}" data-act="anketa:set" data-k="${k}" data-v="${esc(v)}">${esc(t)}</button>`).join('')}</div>`;
  const txt = (k, cur, ph, mode) => `<label><input type="text" data-an="${k}" value="${esc(cur)}" placeholder="${esc(ph)}" ${mode ? `inputmode="${mode}"` : ''} autocomplete="off"></label><div class="pick"><button class="btn main" data-act="anketa:txt" data-k="${k}">Дальше</button></div>`;
  const q = (title, legend, body) => `<div class="card"><h2>${title}</h2>${legend ? `<p class="legend">${legend}</p>` : ''}${body}`;

  function screen(){
    if (st.wait) return waitView();
    const all = steps(), i = Math.min(st.i, all.length - 1), k = all[i], a = A();
    const demo = S.mode !== 'live' ? `<div class="note">Демо: ответы здесь не сохраняются.</div>` : '';
    if (k === 'intro') return card(`${head(null, passed() ? 'Обо мне' : 'Давайте познакомимся', '2–3 минуты: по ответам копия настроится под вас', null, 'старт', '')}${demo}
      <div class="card"><p class="desc" style="color:inherit">Несколько вопросов о вас: какие части копии включить, какие лучи скрыть, с каких сфер начать. Любой вопрос можно пропустить.</p>
      <p class="legend">${passed() ? 'Здесь ваши прежние ответы — поменяйте то, что изменилось. Оценки, файлы и включённое ничего не затрёт.' : 'Ответы хранятся только в вашем хранилище, в файле «Профиль». Поменять их можно потом на экране «Обо мне».'}</p>
      <div class="pick"><button class="btn main" data-act="anketa:go" data-i="1">${passed() ? 'Пройти' : 'Начать'}</button><a class="btn" href="#/">Позже</a></div></div>`);
    if (k === 'imya') return card(q('Как к вам обращаться?', 'Имя или как вам привычнее — страница будет здороваться.', txt('imya', a.imya, 'например, Анна')) + nav(i) + '</div>');
    if (k === 'god') return card(q('Ваш год рождения?', 'Год, а не возраст: возраст устаревает. Пригодится для линеек под ваш возраст.', txt('god', a.god, 'например, 1990', 'numeric')) + nav(i) + '</div>');
    if (k === 'pol') return card(q('Ваш пол?', '', opts('pol', [['мужской', 'Мужской'], ['женский', 'Женский'], ['', 'Не указывать']], a.pol)) + nav(i) + '</div>');
    if (k === 'tsikl') return card(q('Хотите отмечать месячный цикл?', `Включится модуль «Цикл»: луч в сфере ${sn('01', 'Здоровье и молодость')} и календарь отметок. Выключить можно в любой момент — записи сохранятся.`, opts('tsikl', [['да', 'Да'], ['нет', 'Нет']], a.tsikl)) + nav(i) + '</div>');
    if (k === 'strana') return card(q('В какой стране вы живёте?', 'По ней программа выберет валюту в «Деньгах» (если её ещё нет), а ветки событий подскажут «по закону своей страны».', txt('strana', a.strana, 'например, Испания')) + nav(i) + '</div>');
    if (k === 'para') return card(q('Есть ли у вас сейчас пара?', `Если нет — луч «Совместная жизнь» скроется (вернуть можно в сфере ${sn('06', 'Пара, любовь и сексуальность')}), а опросник задаст вопросы «без пары».`, opts('para', [['да', 'Есть'], ['нет', 'Нет']], a.para)) + nav(i) + '</div>');
    if (k === 'deti') return card(q('Есть ли у вас дети?', 'Если нет — вопросы о своих детях не зададутся; в луче «Дети» останутся готовность, принципы и дети рядом.', opts('deti', [['да', 'Есть'], ['нет', 'Нет']], a.deti)) + nav(i) + '</div>');
    if (k === 'pit') return card(q('Есть ли у вас домашние животные?', `Если есть — включится модуль «Питомцы»: луч в сфере ${sn('07', 'Семья')} и медкарта питомца.`, opts('pit', [['да', 'Есть'], ['нет', 'Нет']], a.pit)) + nav(i) + '</div>');
    if (k === 'zdor') return card(q('Есть ли ограничения по здоровью для физических нагрузок?', 'Только да или нет — без подробностей. Если да, у физических лучей появится напоминание посоветоваться с врачом.', opts('zdor', [['да', 'Есть'], ['нет', 'Нет']], a.zdor)) + nav(i) + '</div>');
    if (k === 'etap') return card(q('Чем вы сейчас живёте?', 'Выберите или напишите своими словами.', opts('etap', ETAP.map(x => [x, x[0].toUpperCase() + x.slice(1)]), a.etap) + txt('etap', ETAP.includes(a.etap) ? '' : a.etap, 'своими словами')) + nav(i) + '</div>');
    if (k === 'chasy') return card(q('Сколько часов в неделю готовы уделять копии и себе?', 'Блоки внимания на сферы — без работы за деньги. Можно начать с малого.', opts('chasy', CHASY.map(x => [x, `${x} ч`]), a.chasy)) + nav(i) + '</div>');
    if (k === 'sob') return card(q('Ждёт ли вас в ближайшие месяцы большое событие?', 'Для таких событий есть готовые ветки: подготовка, сам день и привыкание.', opts('sob', SOB, a.sob) + txt('sob', SOB.some(x => x[0] === a.sob) ? '' : a.sob, 'другое — своими словами')) + nav(i) + '</div>');
    if (k === 'nabor'){
      const ag = age(a.god), items = [['Полный', `Все сферы (${allSph().length})`], ['Лёгкий старт', '6 главных сфер, остальные потом']];
      if ((ag != null && ag < 18) || a.nabor === 'Подросток') items.push(['Подросток', 'Все сферы без «взрослых» лучей']);
      if (a.nabor === 'Пара') items.push(['Пара', 'Вдвоём, у каждого своя копия']);
      return card(q('С чего начать?', 'Скрытое не удаляется: сферы можно открыть в любой момент внизу колеса.', opts('nabor', items, a.nabor)) + nav(i) + '</div>');
    }
    if (k === 'prio'){
      const nb = nabor(a.nabor), vis = allSph().filter(s => nb && a.nabor !== one(pfm()['набор применён']) ? !nb.hidden.includes(s.kod) : !s.hiddenSphere);
      return card(q('Какие сферы сейчас важнее всего?', 'Выберите до трёх — по порядку: первая — главная. По ним сразу заработает «Следующий шаг».',
        `<div class="pick">${vis.map(s => { const n = a.prio.indexOf(s.kod); return `<button class="btn ${n >= 0 ? 'on' : ''}" data-act="anketa:prio" data-v="${esc(s.kod)}">${n >= 0 ? `${n + 1} · ` : ''}${esc(s.name)}</button>`; }).join('')}</div>
        <div class="pick"><button class="btn main" data-act="anketa:go" data-i="${i + 1}">Дальше</button></div>`) + nav(i, true) + '</div>');
    }
    return card(itog());
  }

  // «Вот что мы настроим»
  function plan(){
    const a = A(), fm = pfm(), out = [], mods = [...a.mods.filter(m => !['Питомцы', 'Цикл'].includes(m))];
    if (!mods.includes('Основа')) mods.unshift('Основа');
    const want = {Питомцы: a.pit, Цикл: a.pol === 'женский' ? a.tsikl : (a.mods.includes('Цикл') ? 'да' : '')};
    for (const m of ['Питомцы', 'Цикл']){
      const was = a.mods.includes(m), on = want[m] === 'да' || (want[m] === '' && was);
      if (on) mods.push(m);
      if (on && !was) out.push(`Включится модуль «${m}»${m === 'Питомцы' ? ` — луч «Домашние животные» в сфере ${sn('07', 'Семья')}` : ` — луч «Цикл» в сфере ${sn('01', 'Здоровье и молодость')}`}.`);
      if (!on && was) out.push(`Модуль «${m}» выключится — его файлы и оценки уйдут в архив, вернуть можно здесь же.`);
    }
    const nb = nabor(a.nabor);
    if (nb && a.nabor !== one(fm['набор применён'])){
      const hid = allSph().filter(s => nb.hidden.includes(s.kod)).map(s => s.name);
      out.push(hid.length ? `Начнём с набора «${a.nabor}»: скроются сферы ${hid.map(x => `«${x}»`).join(', ')}.` : `Набор «${a.nabor}»: все сферы на колесе.`);
    }
    const para = allSph().flatMap(s => [...s.rays, ...s.hiddenRays]).find(r => r.kod === '06.04');
    if (para && a.para === 'нет' && !para.hidden) out.push(`Скроется луч «Совместная жизнь» — вернуть его можно в сфере ${sn('06', 'Пара, любовь и сексуальность')}.`);
    if (para && a.para === 'да' && para.hidden) out.push('Вернётся луч «Совместная жизнь».');
    if (a.deti === 'нет') out.push('В опроснике — вопросы для тех, у кого пока нет детей.');
    if (a.prio.length){ const byK = Object.fromEntries(allSph().map(s => [s.kod, s.name])); out.push(`В приоритете: ${a.prio.map((k, n) => `${n + 1} — ${byK[k] || k}`).join(', ')}. Часы на них — в «Время и внимание».`); }
    if (a.strana) out.push(`Страна — ${a.strana}: программа поставит валюту в «Деньгах», если её там ещё нет.`);
    if (a.zdor === 'да') out.push(`У физических лучей сферы ${sn('01', 'Здоровье и молодость')} — напоминание «Сначала посоветуйтесь с врачом».`);
    const sob = vetka(a.sob); if (sob) out.push(`На «Следующем шаге» — подсказка про ветку «${sob}».`);
    return {out, mods};
  }
  function itog(){
    const a = A(), {out} = plan(), i = steps().length - 1;
    return `${head(null, a.imya ? `${a.imya}, вот что мы настроим` : 'Вот что мы настроим', 'Проверьте и нажмите «Всё верно»', null, 'итог', '')}
      <div class="card">${out.length ? `<ul>${out.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="desc">Менять ничего не нужно — ответы просто сохранятся.</p>'}
      <p class="legend">Сохранится файл «Профиль»; настройку сделает программа на GitHub — это около минуты. Потом — быстрый опросник по сферам.</p>
      <div class="pick"><button class="btn main" data-act="anketa:save">Всё верно</button><button class="btn" data-act="anketa:go" data-i="${i - 1}">Назад</button></div></div>`;
  }

  // ───────── Запись «Профиля» одним коммитом ─────────
  function fmSet(text, key, value, after){ // строка или список в шапке: заменить или вставить после `after`
    const m = text.match(FM); if (!m) throw new Error('у «Профиля» нет шапки');
    const lines = m[1].split('\n'), neu = Array.isArray(value) ? [`${key}:`, ...value.map(x => `  - "${x}"`)] : [value === '' ? `${key}:` : `${key}: ${value}`];
    let i = lines.findIndex(l => !l.startsWith(' ') && l.split(':')[0].trim() === key);
    if (i >= 0){ let j = i + 1; while (j < lines.length && /^\s+-\s/.test(lines[j])) j++; lines.splice(i, j - i, ...neu); }
    else { i = lines.findIndex(l => !l.startsWith(' ') && l.split(':')[0].trim() === after); let j = i + 1; while (i >= 0 && j < lines.length && /^\s+-\s/.test(lines[j])) j++; lines.splice(i >= 0 ? j : lines.length, 0, ...neu); }
    return `---\n${lines.join('\n')}\n---\n` + text.slice(m[0].length);
  }
  const stamp = () => { const d = new Date(); return `${today()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
  function save(){
    const a = A(), {mods} = plan(), when = stamp(), q_ = v => /[:#"]/.test(v) ? `"${v.replace(/"/g, "'")}"` : v;
    const sets = [['имя', q_(a.imya), 'тип'], ['год рождения', a.god, 'имя'], ['пол', a.pol, 'год рождения'], ['страна', q_(a.strana), 'пол'],
      ['пара', a.para, 'страна'], ['дети', a.deti, 'пара'], ['ограничения здоровья', a.zdor, 'дети'], ['этап жизни', q_(a.etap), 'ограничения здоровья'],
      ['часов в неделю', a.chasy, 'этап жизни'], ['приоритеты', a.prio, 'часов в неделю'], ['событие', q_(a.sob), 'приоритеты'],
      ['набор', a.nabor, 'событие'], ['модули', mods, 'набор'], ['анкета пройдена', `"${when}"`, 'модули включены'], ['обновлено', today(), 'статус']];
    const base = ['---', 'тип: профиль', 'статус: в работе', `обновлено: ${today()}`, '---', '# Профиль', '', '*Данные о владельце для настройки копии (CLAUDE.md, п. 5.2, «Профиль»).*', ''].join('\n');
    const op = view(PROFIL) == null ? {type: 'create', content: sets.reduce((t, [k, v, af]) => fmSet(t, k, v, af), base)}
      : {type: 'fn', fn: text => sets.reduce((t, [k, v, af]) => fmSet(t, k, v, af), text)};
    change(PROFIL, op, passed() ? 'Обо мне: ответы анкеты обновлены' : 'Анкета знакомства: ответы в «Профиль»');
    if (S.mode !== 'live'){ toast('Демо: ответы не сохраняются'); st.a = null; st.i = 0; location.hash = '#/opros'; return; }
    st.wait = {when, n: 0, done: false, late: false}; render(); poll();
  }
  function poll(){ // ждём, пока GitHub Actions применит анкету (nastroyka.py пишет `анкета применена`)
    const w = st.wait; if (!w) return;
    setTimeout(async () => {
      if (st.wait !== w) return;
      try {
        if (!S.busy){ await refreshFile(PROFIL); if (one(pfm()['анкета применена']) === w.when){ w.done = true; finish(); return; } }
      } catch(e){}
      w.n++; if (w.n === 36){ w.late = true; render(); } // ~3 минуты
      poll();
    }, w.n ? 5000 : 8000);
  }
  function finish(next){
    st.wait = null; st.a = null; st.i = 0;
    const noScores = S.spheres.every(s => s.rays.every(r => r.score == null));
    location.hash = next || (noScores ? '#/opros' : '#/');
    start('live'); // копия настроена — прочитать её заново (модули, скрытые сферы и лучи)
  }
  function waitView(){
    const w = st.wait;
    return `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Настройка</span></nav>${head(null, 'Настраиваю копию…', 'Программа на GitHub раскладывает модули и скрывает лишнее', null, 'итог', '')}
      <div class="card"><div class="bar" aria-hidden="true"><i style="width:${Math.min(95, 10 + w.n * 3)}%"></i></div>
      ${w.late ? `<p class="desc">GitHub настраивает дольше обычного. Можно продолжить сейчас — изменения появятся, когда вы обновите страницу.</p>
        <div class="pick"><button class="btn main" data-act="anketa:dalshe" data-v="#/opros">К опроснику</button><button class="btn" data-act="anketa:dalshe" data-v="#/">На колесо</button></div>`
        : '<p class="legend">Обычно это меньше минуты. Страница сама перейдёт к опроснику.</p>'}</div>`;
  }

  return {
    menu: {title: 'Обо мне', order: 5, sub: () => passed() ? `${one(pfm()['имя']) ? one(pfm()['имя']) + ': ' : ''}ответы анкеты — можно поменять` : 'Анкета знакомства — 2–3 минуты, с неё удобно начать'},
    need: p => p === PROFIL || isNab(p),
    passed,
    view(){ return screen(); },
    act(k, b){
      const a = A(), all = steps(), i = Math.min(st.i, all.length - 1);
      if (k === 'go'){ go(+b.dataset.i); return; }
      if (k === 'set'){ a[b.dataset.k] = b.dataset.v; if (b.dataset.k === 'pol' && a.pol !== 'женский' && !a.mods.includes('Цикл')) a.tsikl = ''; go(steps().indexOf(b.dataset.k) + 1); return; }
      if (k === 'txt'){
        const inp = app.querySelector(`[data-an="${b.dataset.k}"]`), v = inp ? inp.value.trim() : '';
        if (b.dataset.k === 'god' && v){ const y = parseInt(v, 10), now = new Date().getFullYear(); if (!/^\d{4}$/.test(v) || y < 1900 || y > now){ toast(`Год — четыре цифры, от 1900 до ${now}`); return; }
          if (now - y < 18 && a.nabor === 'Полный' && !passed()) a.nabor = 'Подросток'; }
        if (v || b.dataset.k !== 'etap') a[b.dataset.k] = v;
        go(i + 1); return;
      }
      if (k === 'prio'){
        const n = a.prio.indexOf(b.dataset.v);
        if (n >= 0) a.prio.splice(n, 1); else if (a.prio.length >= 3){ toast('Не больше трёх — снимите одну'); return; } else a.prio.push(b.dataset.v);
        render(); return;
      }
      if (k === 'save'){ save(); return; }
      if (k === 'dalshe'){ finish(b.dataset.v); return; }
    },
  };
})();

// Подсказка ветки по `событие` «Профиля» (и для «Следующего шага»): имя заготовки в «80 Шаблоны/Ветки»
function vetka(sob){
  const s = String(sob || '').trim().toLowerCase();
  if (!s || s === 'нет') return '';
  return s === 'переезд' ? 'Переезд' : s === 'новый питомец' ? 'Новый питомец' : s === 'ребёнок' || s === 'ребенок' ? 'Беременность' : 'своя';
}
