// Экран «Деньги» (апгрейд 5.1) — запись в учёт «откуда → куда» (CLAUDE.md, п. 5.2, «10 Деньги»).
// Пишет строки в файл месяца «10 ГГГГ-ММ Деньги.md» (нет файла — создаёт из шаблона): «Операции», «Сверка»,
// в первом месяце — «Начальные остатки»; счета — в настройках «10 Деньги». Итоги, остатки и прогноз считает
// .github/scripts/dengi.py (GitHub Actions после каждой записи) — экран показывает его раздел «Итоги».
'use strict';
(window.EKRANY = window.EKRANY || {}).dengi = (() => {
  const isDen = p => /^10 Сферы\/10 [^/]+\/Деньги\/[^/]+\.md$/.test(p);
  const TPL = '80 Шаблоны/Шаблон — Деньги месяц.md';
  const KINDS = ['наличные', 'банк', 'баланс', 'долг', 'запас'];
  const VIDY = {rash: 'Расход', doh: 'Доход', per: 'Перевод', voz: 'Возврат'};
  const MON = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
  const st = {vid: 'rash', form: null, ym: null};
  const ymNow = () => today().slice(0, 7);
  const ymLabel = ym => `${MON[+ym.slice(5) - 1]} ${ym.slice(0, 4)}`;
  const ymAdd = (ym, k) => { let [y, m] = ym.split('-').map(Number); m += k; y += Math.floor((m - 1) / 12); m = ((m - 1) % 12 + 12) % 12 + 1; return `${y}-${String(m).padStart(2, '0')}`; };
  const clean = s => String(s || '').replace(/\|/g, '/').replace(/\s+/g, ' ').trim();
  const amount = s => { const v = parseFloat(String(s).replace(/[\s €]/g, '').replace(',', '.')); return isFinite(v) ? Math.round(v * 100) / 100 : NaN; };
  const money = v => { const s = Math.abs(v).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ' ').replace('.', ','); return (v < 0 ? '−' : '') + s.replace(/,00$/, ''); };
  const cellSum = v => v.toFixed(2).replace('.', ',').replace(/,00$/, '');

  function settings(){
    const p = S.paths.find(x => isDen(x) && readFm(view(x) || '')['тип'] === 'деньги');
    if (!p) return null;
    const fm = readFm(view(p)), acc = [];
    for (const l of (Array.isArray(fm['счета']) ? fm['счета'] : [])){ const i = l.lastIndexOf(':'); if (i > 0) acc.push({name: l.slice(0, i).trim(), kind: l.slice(i + 1).trim()}); }
    return {path: p, dir: p.split('/').slice(0, 3).join('/'), acc, budget: fm['бюджет'] || 'личный'};
  }
  const months = () => S.paths.filter(p => isDen(p) && readFm(view(p) || '')['тип'] === 'деньги-месяц').map(p => ({p, ym: readFm(view(p))['месяц']})).filter(x => /^\d{4}-\d\d$/.test(x.ym)).sort((a, b) => a.ym.localeCompare(b.ym));
  function rows(text, title){ // строки таблицы раздела «## title»
    const out = []; let sec = null, head = false;
    for (const ln of (text || '').split('\n')){
      if (ln.startsWith('## ')){ sec = ln.slice(3).trim(); head = false; continue; }
      if (sec !== title || !/^\|.*\|\s*$/.test(ln)) continue;
      const c = cells(ln); if (c.every(x => !x || /^:?-+:?$/.test(x))){ head = true; continue; }
      if (head) out.push({c, line: ln});
    }
    return out;
  }
  function addRow(text, title, row){ // дописать строку в конец таблицы раздела (раздела нет — создать перед «Итоги»)
    const L = text.split('\n'); let i = L.findIndex(l => l.trim() === `## ${title}`);
    if (i < 0){
      const it = L.findIndex(l => l.trim() === '## Итоги'), at = it < 0 ? L.length : it;
      const cols = title === 'Сверка' ? ['Дата', 'Счёт', 'По факту'] : ['Дата', 'Сумма', 'Откуда', 'Куда', 'Что'];
      L.splice(at, 0, `## ${title}`, '', `| ${cols.join(' | ')} |`, `|${cols.map(() => '---').join('|')}|`, row, '');
      return L.join('\n');
    }
    let j = i + 1, last = -1;
    while (j < L.length && !L[j].startsWith('## ')){ if (/^\|/.test(L[j])) last = j; j++; }
    if (last < 0) throw new Error(`в разделе «${title}» нет таблицы`);
    L.splice(last + 1, 0, row); return L.join('\n');
  }
  const stamp = (text, d) => touchFm(text, [['обновлено', d, 'статус']]);
  function monthPath(set, ym){ return `${set.dir}/10 ${ym} Деньги.md`; }
  function newMonth(set, ym, first){
    let t = view(TPL) || '---\nтип: деньги-месяц\nсфера: "[[10 Финансы]]"\nмесяц: ""\nстатус: в работе\nобновлено:\n---\n# Деньги — месяц\n\n## Операции\n\n| Дата | Сумма | Откуда | Куда | Что |\n|---|---|---|---|---|\n\n## Сверка\n\n| Дата | Счёт | По факту |\n|---|---|---|\n\n## Итоги\n\n<!-- dengi: начало -->\n<!-- dengi: конец -->\n';
    t = touchFm(t, [['месяц', `"${ym}"`, 'сфера'], ['обновлено', today(), 'статус']]).replace(/^# Деньги — месяц$/m, `# Деньги — ${ymLabel(ym)}`);
    if (!first) t = t.replace(/## Начальные остатки[\s\S]*?(?=## Операции)/, ''); // остатки переносит программа
    return t;
  }
  function write(set, ym, fn, msg){
    const p = monthPath(set, ym), first = !months().length;
    if (!S.paths.includes(p) && !S.files.has(p)) change(p, {type: 'create', content: newMonth(set, ym, first)}, `Деньги: новый месяц ${ym}`);
    change(p, {type: 'fn', fn}, msg);
  }
  const statyi = (kind) => { const set = new Set(); for (const m of months()) for (const r of rows(view(m.p), 'Операции')) for (const x of [r.c[2], r.c[3]]){ const mm = (x || '').match(new RegExp(`^${kind}:\\s*(.+)$`)); if (mm) set.add(mm[1].trim()); } return [...set].sort(); };

  function screen(){
    const set = settings(), ym = st.ym || ymNow();
    let h = `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Деньги</span></nav>`;
    if (!set) return h + `<div class="note">Файла настроек учёта денег («10 Деньги», папка «Деньги» сферы 10) нет.</div>`;
    const M = months(), cur = M.find(m => m.ym === ym), text = cur ? view(cur.p) : null, fm = text ? readFm(text) : {};
    const n = v => v != null && v !== '' && !Array.isArray(v) ? money(amount(v)) : '—';
    h += `<div class="head"><div class="big" style="font-size:34px">${text ? n(fm['расход']) : '—'}<small>расход</small></div><div><h1>Деньги — ${esc(ymLabel(ym))}</h1><div class="sub">Доход ${text ? n(fm['доход']) : '—'}${fm['неучтено'] && !Array.isArray(fm['неучтено']) ? ` · неучтено ${n(fm['неучтено'])}` : ''}</div></div></div>`;
    h += `<div class="pick"><button class="btn" data-act="dengi:ym" data-v="${ymAdd(ym, -1)}">‹ ${esc(ymLabel(ymAdd(ym, -1)))}</button>${ym !== ymNow() ? `<button class="btn" data-act="dengi:ym" data-v="${ymNow()}">Этот месяц</button>` : ''}${ym < ymNow() ? `<button class="btn" data-act="dengi:ym" data-v="${ymAdd(ym, 1)}">${esc(ymLabel(ymAdd(ym, 1)))} ›</button>` : ''}</div>`;
    if (S.mode !== 'live') h += `<div class="note">Демо: записи здесь не сохраняются.</div>`;
    if (!set.acc.length) h += `<div class="note">Сначала добавьте счёт — внизу, «Счета».</div>`;
    const first = !M.length;
    // форма записи
    if (set.acc.length && first) h += startForm(set);
    else if (set.acc.length) h += opForm(set, ym);
    // операции месяца
    const ops = rows(text, 'Операции');
    if (ops.length){
      h += `<div class="card"><h2>Операции: ${ops.length}</h2><div class="ops">` + [...ops].reverse().slice(0, st.all ? 999 : 12).map(r => {
        const [d, s, f, t, w] = r.c, out = /^Расход/.test(t), inn = /^(Доход|Возврат)/.test(f);
        return `<div class="op"><span class="legend">${esc(d.slice(8))}.${esc(d.slice(5, 7))}</span><span><b>${esc((out ? t : inn ? f : `${f} → ${t}`).replace(/^(Расход|Доход|Возврат):\s*/, ''))}</b>${w ? ` <span class="legend">${esc(w)}</span>` : ''}<br><span class="legend">${esc(out ? f : inn ? t : 'перевод')}</span></span><span class="num ${out ? 'minus' : inn ? 'plus' : ''}">${out ? '−' : inn ? '+' : ''}${esc(s)}</span><button class="icon" data-act="dengi:del" data-ym="${ym}" data-line="${esc(r.line)}" aria-label="Удалить строку">✕</button></div>`;
      }).join('') + `</div>${ops.length > 12 && !st.all ? `<button class="btn" data-act="dengi:all">Показать все</button>` : ''}</div>`;
    } else if (text) h += `<p class="legend">В этом месяце операций пока нет.</p>`;
    // итоги программы
    if (text && text.includes('<!-- dengi: начало -->')){
      const blk = text.slice(text.indexOf('<!-- dengi: начало -->') + 22, text.indexOf('<!-- dengi: конец -->')).trim();
      h += blk ? `<details ${ops.length ? 'open' : ''}><summary>Итоги месяца</summary><div class="print-doc dn">${mdFull(blk)}</div></details>` : '';
      if (S.busy || (fm['обновлено'] === today() && !blk)) h += `<p class="legend">Итоги, остатки и прогноз пересчитываются сами через минуту-две после записи.</p>`;
    }
    // сверка
    if (set.acc.length && text) h += `<details><summary>Сверка: сколько по факту на счетах</summary><div style="display:grid;gap:10px;margin-top:8px">
      <p class="legend">Раз в месяц впишите, сколько денег на самом деле на каждом счёте. Разницу с посчитанным программа запишет как «неучтённое».</p>
      ${set.acc.map(a => `<label>${esc(a.name)} <span class="legend">${esc(a.kind)}</span><input type="text" inputmode="decimal" data-sv="${esc(a.name)}" placeholder="например, 1520,40"></label>`).join('')}
      <div class="pick"><button class="btn main" data-act="dengi:sverka" data-ym="${ym}">Записать сверку</button></div></div></details>`;
    // счета
    h += `<details ${set.acc.length ? '' : 'open'}><summary>Счета: ${set.acc.length}</summary><div style="display:grid;gap:10px;margin-top:8px">
      <p class="desc">${set.acc.map(a => `${esc(a.name)} — ${esc(a.kind)}`).join(' · ') || 'Счетов пока нет.'}</p>
      <label>Новый счёт — название<input type="text" id="dnAcc" placeholder="например, Карта, Кошелёк, Копилка"></label>
      <label>Вид</label><div class="pick" role="group">${KINDS.map(k => `<button class="btn ${(st.kind || 'банк') === k ? 'on' : ''}" data-act="dengi:kind" data-v="${k}">${k}</button>`).join('')}</div>
      <p class="legend">наличные · банк · баланс (ваши деньги у другого) · долг (вам должны) · запас.</p>
      <div class="pick"><button class="btn" data-act="dengi:acc">Добавить счёт</button></div></div></details>`;
    return h + `<p class="legend">Перевод между своими счетами — не доход и не расход. Номера карт и счетов сюда не пишутся.</p>`;
  }
  function startForm(set){
    return `<div class="step"><b class="t">Начало учёта</b><p class="desc" style="color:inherit">Сколько денег сейчас на каждом счёте? Это точка отсчёта; дальше остатки программа считает сама.</p>
      ${set.acc.map(a => `<label>${esc(a.name)} <span class="legend">${esc(a.kind)}</span><input type="text" inputmode="decimal" data-st="${esc(a.name)}" placeholder="0"></label>`).join('')}
      <div class="pick"><button class="btn main" data-act="dengi:start">Начать учёт</button></div></div>`;
  }
  function opForm(set, ym){
    const v = st.vid, acc = set.acc.map(a => `<option>${esc(a.name)}</option>`).join('');
    const stat = v === 'rash' || v === 'voz' ? statyi('Расход').concat(statyi('Возврат')) : statyi('Доход');
    const d = ym === ymNow() ? today() : `${ym}-01`;
    let f = `<div class="card"><h2>Записать</h2><div class="pick" role="group">${Object.entries(VIDY).map(([k, n]) => `<button class="btn ${v === k ? 'on' : ''}" data-act="dengi:vid" data-v="${k}">${n}</button>`).join('')}</div>`;
    f += `<label>Сумма<input type="text" inputmode="decimal" id="dnSum" placeholder="например, 12,50" autocomplete="off"></label>`;
    if (v === 'per') f += `<label>Откуда<select id="dnFrom">${acc}</select></label><label>Куда<select id="dnTo">${set.acc.map((a, i) => `<option ${i === 1 ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}</select></label>`;
    else f += `<label>${v === 'rash' ? 'С какого счёта' : 'На какой счёт'}<select id="dnAcc2">${acc}</select></label>
      <label>${v === 'doh' ? 'Откуда доход (статья)' : 'Статья расхода'}<input type="text" id="dnStat" list="dnStatList" placeholder="${v === 'doh' ? 'например, Зарплата' : 'например, Еда'}" autocomplete="off"><datalist id="dnStatList">${stat.map(x => `<option value="${esc(x)}">`).join('')}</datalist></label>`;
    if (set.budget !== 'личный' && v === 'rash') f += `<label>Чей расход</label><div class="pick" role="group">${['моё', 'общее', 'партнёра'].map(x => `<button class="btn ${(st.whose || 'моё') === x ? 'on' : ''}" data-act="dengi:whose" data-v="${x}">${x}</button>`).join('')}</div>`;
    f += `<label>Что (по желанию)<input type="text" id="dnWhat" placeholder="коротко" autocomplete="off"></label>
      <label>Дата<input type="date" id="dnDate" value="${d}" min="${ym}-01" max="${ym}-31"></label>
      <div class="pick"><button class="btn main" data-act="dengi:add" data-ym="${ym}">Записать</button></div></div>`;
    return f;
  }
  const val = id => (document.getElementById(id) || {}).value || '';

  return {
    menu: {title: 'Деньги', order: 40, sub: () => { const M = months(), c = M.find(m => m.ym === ymNow()), fm = c ? readFm(view(c.p)) : null;
      return fm && fm['расход'] && !Array.isArray(fm['расход']) ? `${ymLabel(ymNow())}: расход ${money(amount(fm['расход']))}, доход ${money(amount(fm['доход'] || 0))}` : 'Доходы и расходы «откуда → куда»: запись в одно касание'; }},
    need: p => isDen(p) || p === TPL,
    view(){ return screen(); },
    fon(){ nuzhny(isDen).then(() => { if (!route()[0]) render(); }).catch(() => {}); },
    act(a, b){
      const set = settings();
      if (a === 'ym'){ st.ym = b.dataset.v; st.all = false; render(); return; }
      if (a === 'all'){ st.all = true; render(); return; }
      if (a === 'vid'){ st.vid = b.dataset.v; render(); return; }
      if (a === 'kind' || a === 'whose'){ st[a] = b.dataset.v; for (const x of b.parentNode.children) x.classList.toggle('on', x === b); return; }
      if (a === 'add'){
        const ym = b.dataset.ym, s = amount(val('dnSum')), d = val('dnDate'), what = clean(val('dnWhat'));
        if (!(s > 0)){ toast('Сумма — число больше нуля'); return; }
        if (!/^\d{4}-\d\d-\d\d$/.test(d) || d.slice(0, 7) !== ym){ toast(`Дата — из месяца ${ymLabel(ym)}`); return; }
        let from, to;
        if (st.vid === 'per'){ from = val('dnFrom'); to = val('dnTo'); if (from === to){ toast('Откуда и куда — разные счета'); return; } }
        else {
          const stat = clean(val('dnStat')).replace(/:/g, ' '); if (!stat){ toast(st.vid === 'doh' ? 'Откуда доход? Например, Зарплата' : 'Статья — например, Еда'); return; }
          const mark = st.vid === 'rash' && set.budget !== 'личный' && st.whose && st.whose !== 'моё' ? ` (${st.whose})` : '';
          const end = `${VIDY[st.vid]}: ${stat}${mark}`, acc = val('dnAcc2');
          [from, to] = st.vid === 'rash' ? [acc, end] : [end, acc];
        }
        const row = `| ${d} | ${cellSum(s)} | ${clean(from)} | ${clean(to)} | ${what} |`;
        write(set, ym, t => stamp(addRow(t, 'Операции', row), today()), `Деньги: ${clean(from)} → ${clean(to)} ${cellSum(s)}`);
        toast(`Записано: ${money(s)}`); return;
      }
      if (a === 'del'){
        if (!confirm('Удалить эту строку из учёта?')) return;
        const line = b.dataset.line;
        write(set, b.dataset.ym, t => { const L = t.split('\n'), i = L.indexOf(line); if (i < 0) throw new Error('строка уже изменена'); L.splice(i, 1); return stamp(L.join('\n'), today()); }, 'Деньги: удалена строка');
        toast('Строка удалена'); return;
      }
      if (a === 'start'){
        const d = today(), vals = [...document.querySelectorAll('[data-st]')].map(i => [i.dataset.st, i.value.trim() === '' ? 0 : amount(i.value)]);
        if (vals.some(([, v]) => !isFinite(v))){ toast('Суммы — числами'); return; }
        write(set, d.slice(0, 7), t => {
          if (!/## Начальные остатки/.test(t)) t = t.replace(/## Операции/, '## Начальные остатки\n\nНа: ГГГГ-ММ-ДД\n\n| Счёт | Сумма |\n|---|---|\n\n## Операции');
          t = t.replace(/^\*Только в первом месяце учёта.*\n\n?/m, '').replace(/^На: .*$/m, `На: ${d}`);
          for (const [k, v] of vals) t = addRow(t, 'Начальные остатки', `| ${clean(k)} | ${cellSum(v)} |`);
          return stamp(t, d);
        }, `Деньги: начальные остатки на ${d}`);
        toast('Учёт начат'); return;
      }
      if (a === 'sverka'){
        const d = b.dataset.ym === ymNow() ? today() : `${b.dataset.ym}-28`;
        const vals = [...document.querySelectorAll('[data-sv]')].filter(i => i.value.trim() !== '').map(i => [i.dataset.sv, amount(i.value)]);
        if (!vals.length){ toast('Впишите хотя бы один счёт'); return; }
        if (vals.some(([, v]) => !isFinite(v))){ toast('Суммы — числами'); return; }
        write(set, b.dataset.ym, t => { for (const [k, v] of vals) t = addRow(t, 'Сверка', `| ${d} | ${clean(k)} | ${cellSum(v)} |`); return stamp(t, today()); }, `Деньги: сверка ${d}`);
        toast('Сверка записана'); return;
      }
      if (a === 'acc'){
        const name = clean(val('dnAcc')).replace(/:/g, ' '), kind = st.kind || 'банк';
        if (!name){ toast('Название счёта'); return; }
        if (set.acc.some(x => x.name.toLowerCase() === name.toLowerCase())){ toast('Такой счёт уже есть'); return; }
        change(set.path, {type: 'fn', fn: t => {
          const m = t.match(FM), L = m[1].split('\n'); let i = L.findIndex(l => l.split(':')[0].trim() === 'счета' && !l.startsWith(' '));
          if (i < 0) throw new Error('в настройках нет свойства `счета`');
          L[i] = 'счета:'; let j = i + 1; while (j < L.length && /^\s+-\s/.test(L[j])) j++;
          L.splice(j, 0, `  - "${name}: ${kind}"`);
          return stamp(`---\n${L.join('\n')}\n---\n` + t.slice(m[0].length), today());
        }}, `Деньги: новый счёт ${name}`);
        toast(`Счёт «${name}» добавлен`); return;
      }
    },
  };
})();
