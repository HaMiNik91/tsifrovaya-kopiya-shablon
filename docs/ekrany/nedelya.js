// Экран «Эта неделя» (апгрейд 5.1) — план недели по часам, как .github/scripts/nedelya.py (CLAUDE.md, п. 9.6–9.7):
// план — `часы` в «NN Шкала» (у закончившейся недели — снимок из её «Итогов»), сделано — `сделано` в шапке
// «20 Журнал/ГГГГ-ММ-ДД План недели.md» (дата — понедельник). «+30 мин» прибавляет часы (нет файла — создаёт из шаблона);
// раздел «Итоги» пересчитывает GitHub Actions. «В календарь» — файл .ics с блоками внимания сфер-приоритетов.
'use strict';
(window.EKRANY = window.EKRANY || {}).nedelya = (() => {
  const ZH = '20 Журнал/', TPL = '80 Шаблоны/Шаблон — План недели.md';
  const MES = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const DNI = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
  const st = {cal: false, time: '19:00', len: 60};
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const parse = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const monday = d => addDays(d, -((d.getDay() + 6) % 7));
  const label = mon => { const sun = addDays(mon, 6);
    return mon.getMonth() === sun.getMonth() ? `${mon.getDate()}–${sun.getDate()} ${MES[sun.getMonth()]} ${sun.getFullYear()}`
      : `${mon.getDate()} ${MES[mon.getMonth()]} – ${sun.getDate()} ${MES[sun.getMonth()]} ${sun.getFullYear()}`; };
  const hf = x => { const s = (Math.round(x * 100) / 100).toFixed(2).replace(/0+$/, '').replace(/\.$/, ''); return s.replace('.', ','); };
  const num = s => parseFloat(String(s).replace(/\s/g, '').replace(',', '.'));
  const wpath = mon => `${ZH}${iso(mon)} План недели.md`;
  const LINE = /^(\d{2})\b[^:]*:\s*(-?[\d.,]+)\s*$/, ROW = /^\|\s*\[\[(\d{2})[^\]]*\]\]\s*\|\s*([\d.,]+)\s*\|/;

  function done(text){ // сделано: код → часы
    const out = {}; let v = text ? readFm(text)['сделано'] : null; v = Array.isArray(v) ? v : (v ? [v] : []);
    for (const s of v){ const m = s.trim().match(LINE); if (m) out[m[1]] = num(m[2]); }
    return out;
  }
  function snapshot(text){ // план закончившейся недели — из её «Итогов»
    if (!text || !text.includes('<!-- nedelya: начало -->')) return null;
    const blk = text.slice(text.indexOf('<!-- nedelya: начало -->'), text.indexOf('<!-- nedelya: конец -->')), out = {};
    for (const ln of blk.split('\n')){ const m = ln.match(ROW); if (m) out[m[1]] = num(m[2]); }
    return Object.keys(out).length ? out : null;
  }
  function setList(text, key, vals, d){ // свойство-список в шапке (заменить или вставить после `когда`)
    const m = text.match(FM); if (!m) throw new Error('у файла нет шапки');
    const ls = m[1].split('\n'), out = []; let skip = false, put = false;
    const block = vals.length ? [`${key}:`, ...vals.map(v => `  - "${v}"`)] : [`${key}:`];
    for (const l of ls){
      if (skip){ if (/^\s+-\s/.test(l)) continue; skip = false; }
      if (!l.startsWith(' ') && l.split(':')[0].trim() === key){ out.push(...block); skip = true; put = true; continue; }
      out.push(l);
    }
    if (!put){ const i = out.findIndex(l => l.split(':')[0].trim() === 'когда'); out.splice(i >= 0 ? i + 1 : out.length, 0, ...block); }
    return touchFm(`---\n${out.join('\n')}\n---\n` + text.slice(m[0].length), [['обновлено', d, 'статус']]);
  }
  function newWeek(mon){ // как nedelya.py create_week
    let t = view(TPL) || '---\nтип: план недели\nкогда: {{date}}\nсделано:\nстатус: в работе\nобновлено: {{date}}\n---\n# План недели\n\n## Итоги\n<!-- nedelya: начало -->\n<!-- nedelya: конец -->\n';
    return t.replace(/\{\{date\}\}/g, iso(mon)).replace('# План недели', `# План недели ${label(mon)}`);
  }
  function add(mon, nn, h){
    const p = wpath(mon), d = today(), spheres = S.spheres;
    const fn = text => {
      const cur = done(text), v = Math.max(0, Math.round(((cur[nn] || 0) + h) * 100) / 100);
      if (v) cur[nn] = v; else delete cur[nn];
      const vals = Object.keys(cur).sort().map(k => { const s = spheres.find(x => x.nn === k); return `${k} ${s ? s.name : ''}: ${hf(cur[k])}`.replace(/ +:/, ':'); });
      return setList(text, 'сделано', vals, d);
    };
    if (!S.paths.includes(p) && !S.files.has(p)) change(p, {type: 'create', content: newWeek(mon)}, `План недели ${label(mon)}`);
    change(p, {type: 'fn', fn}, `Неделя: ${nn} ${(spheres.find(x => x.nn === nn) || {}).name || ''} ${h > 0 ? '+' : '−'}${hf(Math.abs(h))} ч`);
  }

  function ics(mon){ // блоки внимания сфер-приоритетов на эту неделю, по дням с сегодняшнего
    const pr = S.spheres.filter(s => s.prio && s.hours).sort((a, b) => a.prio - b.prio);
    const now = new Date(), start = Math.max(0, Math.round((parse(iso(now)) - mon) / 864e5));
    const days = [...Array(7).keys()].filter(i => i >= start);
    const blocks = []; for (const s of pr) for (let k = 0; k < Math.ceil(s.hours * 60 / st.len); k++) blocks.push(s);
    const [hh, mm] = st.time.split(':').map(Number), pad = n => String(n).padStart(2, '0');
    const stamp = d => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}00`;
    const L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Tsifrovaya kopiya//RU', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'];
    const per = {}; // если блоков больше, чем дней, — второй блок дня идёт сразу после первого
    blocks.forEach((s, i) => {
      const day = days[i % days.length], n = per[day] = (per[day] || 0) + 1;
      const b = addDays(mon, day); b.setHours(hh, mm + (n - 1) * st.len, 0, 0);
      const e = new Date(b.getTime() + st.len * 6e4);
      L.push('BEGIN:VEVENT', `UID:${iso(mon)}-${s.nn}-${i}@tsifrovaya-kopiya`, `DTSTAMP:${stamp(now)}`, `DTSTART:${stamp(b)}`, `DTEND:${stamp(e)}`,
        `SUMMARY:Блок внимания: ${s.name}`, `DESCRIPTION:${st.len} минут — всё внимание одной сфере (план недели: ${hf(s.hours)} ч). После блока отметьте «+${st.len === 60 ? '1 ч' : st.len + ' мин'}» на странице «Эта неделя».`,
        'BEGIN:VALARM', 'TRIGGER:-PT10M', 'ACTION:DISPLAY', `DESCRIPTION:Блок внимания: ${s.name}`, 'END:VALARM', 'END:VEVENT');
    });
    L.push('END:VCALENDAR');
    return {text: L.map(l => l.length > 74 ? l.match(/.{1,73}/gu).join('\r\n ') : l).join('\r\n') + '\r\n', n: blocks.length, days: days.length};
  }

  function screen(arg){
    const now = parse(today()), mon = arg && /^\d{4}-\d\d-\d\d$/.test(arg) ? monday(parse(arg)) : monday(now), sun = addDays(mon, 6);
    const p = wpath(mon), text = view(p), D = done(text);
    const state = now < mon ? 'ещё не началась' : now > sun ? 'закончилась' : 'идёт';
    const snap = state === 'закончилась' ? snapshot(text) : null;
    const plan = {}; for (const s of S.spheres) plan[s.nn] = snap ? (snap[s.nn] || 0) : (s.hours || 0);
    const tp = Object.values(plan).reduce((a, b) => a + b, 0), td = S.spheres.reduce((a, s) => a + (D[s.nn] || 0), 0);
    let h = `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Эта неделя</span></nav>`;
    h += head(hf(td), `Неделя ${label(mon)}`, `${state[0].toUpperCase() + state.slice(1)} · блоков внимания ${hf(td)} ч из ${hf(tp)} ч плана${tp ? ` (${Math.round(td / tp * 100)} %)` : ''}`, null, 'часов', '');
    h += `<div class="pick"><a class="btn" href="#/nedelya/${iso(addDays(mon, -7))}">‹ Прошлая</a>${state !== 'идёт' ? `<a class="btn" href="#/nedelya">Эта неделя</a>` : ''}<a class="btn" href="#/nedelya/${iso(addDays(mon, 7))}">Следующая ›</a></div>`;
    if (S.mode !== 'live') h += `<div class="note">Демо: отметки здесь не сохраняются.</div>`;
    if (!tp && state !== 'закончилась') h += `<div class="note">План по часам не задан — сколько часов в неделю отдавать каждой сфере, ставится в <a href="#/vremya">«Время и внимание»</a>.</div>`;
    if (snap == null && state === 'закончилась' && text) h += `<p class="legend">План — по нынешним часам сфер: снимка плана этой недели нет.</p>`;
    const rows = S.spheres.filter(s => plan[s.nn] > 0 || D[s.nn] > 0 || s.prio)
      .sort((a, b) => (a.prio || 99) - (b.prio || 99) || (b.imp || 0) - (a.imp || 0) || a.nn.localeCompare(b.nn));
    const others = S.spheres.filter(s => !rows.includes(s));
    const row = s => {
      const pl = plan[s.nn] || 0, dn = D[s.nn] || 0, w = pl ? Math.min(100, dn / pl * 100) : (dn ? 100 : 0);
      const how = !pl ? (dn ? 'сверх плана' : 'без плана') : dn >= pl ? 'готово ✓' : `осталось ${hf(pl - dn)} ч`;
      return `<div class="card wk"><div class="twh"><b>${esc(s.nn)} ${esc(s.name)}${s.prio ? ` <span class="chip strong">место ${s.prio}</span>` : ''}</b><span class="num">${hf(dn)} / ${hf(pl)}</span></div>
        <div class="bar"><i style="width:${w}%;${dn >= pl && pl ? 'background:var(--strong)' : ''}"></i></div>
        <div class="twh"><span class="legend">${how}</span><span class="pick">${dn ? `<button class="btn" data-act="nedelya:add" data-nn="${s.nn}" data-h="-0.5" data-w="${iso(mon)}" aria-label="Убрать 30 минут">−30</button>` : ''}<button class="btn main" data-act="nedelya:add" data-nn="${s.nn}" data-h="0.5" data-w="${iso(mon)}">+30 мин</button></span></div></div>`;
    };
    h += rows.map(row).join('');
    if (others.length) h += `<details><summary>Другие сферы: ${others.length}</summary><div style="display:grid;gap:10px;margin-top:8px">${others.map(row).join('')}</div></details>`;
    const empty = rows.filter(s => s.prio && !D[s.nn]);
    if (state === 'идёт' && empty.length && now.getDay() !== 1 && now.getDay() !== 2) h += `<div class="note">Сферы-приоритеты без времени: ${empty.map(s => esc(s.name)).join(', ')}. Уже ${DNI[(now.getDay() + 6) % 7]}.</div>`;
    if (state === 'закончилась' || (state === 'идёт' && now.getDay() === 0)){
      const ok = rows.filter(s => plan[s.nn] && (D[s.nn] || 0) >= plan[s.nn]), less = rows.filter(s => plan[s.nn] && (D[s.nn] || 0) < plan[s.nn]);
      h += `<div class="step"><b class="t">Итог недели</b><div>Блоков внимания — ${hf(td)} ч из ${hf(tp)} ч плана.</div>` +
        (ok.length ? `<div>По плану: ${ok.map(s => esc(s.name)).join(', ')}.</div>` : '') +
        (less.length ? `<div>Меньше плана: ${less.map(s => `${esc(s.name)} (−${hf(plan[s.nn] - (D[s.nn] || 0))} ч)`).join(', ')}.</div>` : '') +
        `<p class="legend">Что радовало и что поменять на следующей неделе — расскажите Claude на вечернем разборе: он запишет итог в план недели.</p></div>`;
    }
    // календарь
    const pr = S.spheres.filter(s => s.prio && s.hours);
    if (state !== 'закончилась'){
      if (!st.cal) h += `<div class="pick"><button class="btn" data-act="nedelya:cal">Добавить блоки в календарь</button></div>`;
      else if (!pr.length) h += `<div class="note">Для календаря нужны сферы-приоритеты с часами — <a href="#/vremya">«Время и внимание»</a>.</div>`;
      else {
        const c = ics(mon);
        h += `<div class="card"><h2>Блоки внимания в календарь</h2><p class="desc">Файл календаря: ${c.n} ${c.n === 1 ? 'блок' : 'блоков'} по ${st.len} минут для сфер-приоритетов (${pr.map(s => `${esc(s.name)} — ${hf(s.hours)} ч`).join(', ')}), по дням до воскресенья, с напоминанием за 10 минут.</p>
          <label>Начало блока<input type="text" inputmode="numeric" data-ch="nedelya:time" value="${esc(st.time)}" placeholder="19:00"></label>
          <label>Длина блока</label><div class="pick">${[30, 60, 90].map(n => `<button class="btn ${st.len === n ? 'on' : ''}" data-act="nedelya:len" data-v="${n}">${n} мин</button>`).join('')}</div>
          <div class="pick"><button class="btn main" data-act="nedelya:ics" data-w="${iso(mon)}">Скачать файл календаря</button></div>
          <p class="legend">Откройте скачанный файл — телефон предложит добавить события в календарь. Время потом можно сдвинуть в самом календаре.</p></div>`;
      }
    }
    return h + `<p class="legend">Блок внимания — 30, 60 или 90 минут, когда всё внимание отдано одной сфере; работа за деньги не считается. Отметка сохраняется сразу в плане недели; итоги пересчитываются сами.</p>`;
  }

  return {
    menu: {title: 'Эта неделя', order: 30, sub: () => {
      const mon = monday(parse(today())), D = done(view(wpath(mon)));
      const tp = S.spheres.reduce((a, s) => a + (s.hours || 0), 0), td = S.spheres.reduce((a, s) => a + (D[s.nn] || 0), 0);
      return tp ? `Блоков внимания: ${hf(td)} ч из ${hf(tp)} ч` : 'Сколько часов внимания получила каждая сфера — отметка в одно нажатие';
    }},
    need: p => p.startsWith(ZH) && / План недели\.md$/.test(p) || p === TPL,
    view(r){ return screen(r[0]); },
    fon(){ nuzhny(p => p.startsWith(ZH) && / План недели\.md$/.test(p)).then(() => { if (!route()[0]) render(); }).catch(() => {}); },
    act(a, b){
      if (a === 'add'){
        const h = +b.dataset.h, s = S.spheres.find(x => x.nn === b.dataset.nn);
        add(parse(b.dataset.w), b.dataset.nn, h); toast(`${s.name}: ${h > 0 ? '+' : '−'}${hf(Math.abs(h) * 60)} мин`); return;
      }
      if (a === 'cal'){ st.cal = true; render(); return; }
      if (a === 'len'){ st.len = +b.dataset.v; render(); return; }
      if (a === 'ics'){
        const mon = parse(b.dataset.w), c = ics(mon);
        const url = URL.createObjectURL(new Blob([c.text], {type: 'text/calendar;charset=utf-8'}));
        const x = document.createElement('a'); x.href = url; x.download = `Блоки внимания ${iso(mon)}.ics`; document.body.appendChild(x); x.click(); x.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000); toast('Файл календаря скачан — откройте его'); return;
      }
    },
    change(a, el){
      if (a === 'time'){ const m = el.value.trim().match(/^(\d{1,2})[:.]?(\d{2})$/);
        if (!m || +m[1] > 23 || +m[2] > 59){ toast('Время — например, 19:00'); el.value = st.time; return; }
        st.time = `${m[1].padStart(2, '0')}:${m[2]}`; render(); }
    },
  };
})();
