// Экран «Следующий шаг» (апгрейд 5.1) — то же правило, что .github/scripts/sled_shag.py (CLAUDE.md, п. 5.5):
// у сфер-приоритетов самый слабый луч → его самые слабые зоны → «Шаг вверх» → помощники ровно под уровень
// (N ≤ уровень < M); нет помощника под уровень — ближайший луч сферы с помощником; шаги, уже взятые в «Путь».
// «Взять в Путь» создаёт файл шага так же, как `sled_shag.py --vzyat`. Оценки страница считает сама (свежее, чем файл).
'use strict';
(window.EKRANY = window.EKRANY || {}).shag = (() => {
  const POM = '60 Помощники/';
  const STEP = /^\*\*Шаг вверх \((\d+) → (\d+)\):\*\*\s*(.+)/;
  const isPom = p => p.startsWith(POM) && /^Помощник — .+\.md$/.test(p.slice(POM.length));
  const isPut = p => /^10 Сферы\/[^/]+\/Путь\/[^/]+\.md$/.test(p);
  const st = {open: null};

  function section(text, title){
    const m = text.match(new RegExp(`^## ${title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\n([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, 'm'));
    return m ? m[1].trim() : '';
  }
  const firstPractice = t => (section(t, 'Что делать').split('\n').map(l => l.trim().replace(/^[-•]\s*/, '').trim()).find(Boolean) || '');
  const uroven = s => { const m = String(s || '').trim().match(/^(\d+)\s*→\s*(\d+)$/); if (!m) return null; const n = +m[1], k = +m[2]; return 1 <= n && n < k && k <= 10 ? [n, k] : null; };
  const podhodit = (u, l) => { const x = uroven(u); return !!x && l != null && x[0] <= l && l < x[1]; };

  function helpers(){
    return S.paths.filter(isPom).map(p => ({p, t: view(p)})).filter(x => x.t).map(({p, t}) => {
      const fm = readFm(t);
      if (fm['тип'] !== 'помощник' || flag(fm['скрыт'])) return null;
      return {path: p, name: p.slice(POM.length).replace(/\.md$/, ''), luch: fm['луч'] || '', urovni: fm['уровни'] || '',
        pomosh: fm['помощь'] || '', nauch: fm['научность'] || '', practice: firstPractice(t), text: t};
    }).filter(Boolean);
  }
  function stepsOf(ray){ // «Шаг вверх» по зонам; вне зоны — шаг луча
    const out = {}, t = view(ray.path) || ''; let cur = null;
    for (const ln of t.replace(FM, '').split('\n')){
      const z = ln.match(ZONE_H); if (z){ cur = z[1].trim(); continue; }
      if (ln.startsWith('## ')){ cur = null; continue; }
      const m = ln.match(STEP); if (m){ const k = cur || ray.name; if (!out[k]) out[k] = [+m[1], +m[2], m[3].trim()]; }
    }
    return out;
  }
  function targets(ray, H){ // зоны (или сам луч) от слабой к сильной: уровень, шаг, помощники
    const steps = stepsOf(ray), out = [];
    const elems = ray.zones.length ? ray.zones : [{name: ray.name, score: ray.score, whole: true}];
    for (const z of elems){
      if (z.score == null) continue;
      const keys = new Set([ray.kod]); if (!z.whole) keys.add(`${ray.kod} / ${z.name}`);
      const hs = H.filter(h => keys.has(h.luch) && podhodit(h.urovni, h.luch === ray.kod ? ray.score : z.score));
      out.push({zone: z.whole ? null : z.name, lvl: z.score, step: steps[z.name] || steps[ray.name] || null, helpers: hs});
    }
    return out.sort((a, b) => a.lvl - b.lvl);
  }
  function pathSteps(sp){
    return S.paths.filter(p => isPut(p) && p.startsWith(`${SPH_DIR}/${sp.dir}/Путь/`)).map(p => ({p, t: view(p)})).filter(x => x.t).map(({p, t}) => {
      const fm = readFm(t); return {path: p, file: p.split('/').pop().replace(/\.md$/, ''), luch: fm['луч'] || '', status: fm['статус'] || 'не начат', tip: fm['тип'], text: t};
    }).filter(x => x.tip === 'шаг' && x.status !== 'готово');
  }

  function helperRow(h, sp){
    const taken = pathSteps(sp).find(x => x.text.includes(`[[${h.name}]]`));
    const open = st.open === h.name, title = h.name.replace(/^Помощник — /, '');
    let s = `<div class="card pom"><div class="twh"><b>${esc(title)}</b><span class="legend">${esc(h.pomosh)} · ${esc(h.urovni)}</span></div>`;
    s += `<p class="desc">${esc(h.practice)}</p>`;
    s += `<div class="legend">${h.nauch === 'популярное' ? 'популярное — слабо проверено' : esc(h.nauch)}</div>`;
    if (open){
      for (const sec of ['Что даёт', 'Что знать', 'Что делать', 'Осторожно', 'Как понять, что помогло']){
        const x = section(h.text, sec); if (x) s += `<div class="prose"><b>${esc(sec)}</b>${md(x)}</div>`;
      }
    }
    s += `<div class="pick"><button class="btn" data-act="shag:open" data-id="${esc(h.name)}">${open ? 'Свернуть' : 'Подробнее'}</button>` +
      (taken ? `<span class="chip strong">в «Пути»: ${esc(taken.status)}</span>` : `<button class="btn main" data-act="shag:vzyat" data-id="${esc(h.name)}">Взять в Путь</button>`) + `</div></div>`;
    return s;
  }

  function screen(){
    const H = helpers(), today_ = today();
    let h = `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Следующий шаг</span></nav>`;
    h += head(null, 'Следующий шаг', 'У сфер-приоритетов — самый слабый луч, его шаг вверх и помощники ровно под ваш уровень', null, 'шаг', '');
    if (S.mode !== 'live') h += `<div class="note">Демо: «Взять в Путь» здесь не сохраняется.</div>`;
    const prio = S.spheres.filter(s => s.prio).sort((a, b) => a.prio - b.prio);
    if (!prio.length) h += `<div class="step"><b class="t">Сферы-приоритеты не выбраны</b><p class="desc" style="color:inherit">Выберите до трёх сфер, которые двигать первыми, — тогда здесь появится их самый слабый луч и что с ним делать.</p><div class="pick"><a class="btn main" href="#/vremya">Время и внимание</a></div></div>`;
    for (const sp of prio){
      const vis = sp.rays.filter(r => r.score != null);
      if (!vis.length){ h += `<div class="card"><h2>${sp.prio}. ${esc(sp.name)}</h2><p class="desc">Лучи сферы ещё не оценены. <a href="#/${sp.nn}">Оценить</a> или пройти <a href="#/opros">опросник</a>.</p></div>`; continue; }
      const low = Math.min(...vis.map(r => r.score));
      for (const ray of vis.filter(r => r.score === low)){
        const ri = sp.rays.indexOf(ray);
        h += `<h2>${sp.prio}. ${esc(sp.name)} — луч «<a href="#/${sp.nn}/${ri}">${esc(ray.name)}</a>», ${ray.score} из 10${ray.approx ? ' (примерно)' : ''}</h2>`;
        const tg = targets(ray, H); let shown = 0;
        for (const e of tg){
          if (shown >= 2 || (shown && !e.helpers.length)) break;
          h += `<div class="step"><b class="t">${e.zone ? `Зона «${esc(e.zone)}» — ${e.lvl}` : `Уровень ${e.lvl}`}</b>`;
          if (e.step) h += `<div><b>Шаг вверх ${e.step[0]} → ${e.step[1]}:</b> ${esc(e.step[2])}</div>`;
          h += `</div>`;
          h += e.helpers.length ? e.helpers.map(x => helperRow(x, sp)).join('') : `<p class="legend">Помощника под этот уровень пока нет.</p>`;
          shown++;
        }
        if (!tg.some(e => e.helpers.length)){
          for (const other of [...vis].sort((a, b) => a.score - b.score)){
            if (other === ray) continue;
            const e = targets(other, H).find(x => x.helpers.length);
            if (e){
              h += `<div class="card"><b>Ближайший луч с помощником: <a href="#/${sp.nn}/${sp.rays.indexOf(other)}">${esc(other.name)}</a>${e.zone ? `, зона «${esc(e.zone)}»` : ''} — ${e.lvl} из 10</b></div>` + e.helpers.map(x => helperRow(x, sp)).join('');
              break;
            }
          }
        }
        const mine = pathSteps(sp).filter(p => p.luch === ray.name);
        if (mine.length) h += `<p class="legend"><b>Уже в «Пути»:</b> ${mine.map(p => `${esc(p.file.replace(/^\d\d Шаг — /, ''))} (${esc(p.status)})`).join('; ')}</p>`;
      }
    }
    const rest = S.spheres.filter(s => !s.prio).map(sp => {
      const vis = sp.rays.filter(r => r.score != null); if (!vis.length) return null;
      const ray = vis.reduce((a, b) => b.score < a.score ? b : a);
      return {sp, ray, n: targets(ray, H).reduce((a, e) => a + e.helpers.length, 0)};
    }).filter(Boolean);
    if (rest.length){
      h += `<h2>Остальные сферы</h2><div class="rows">` + rest.map(({sp, ray, n}) => `<a class="row" href="#/${sp.nn}/${sp.rays.indexOf(ray)}"><span class="name">${esc(sp.nn)} ${esc(ray.name)}<em>${n ? `помощников: ${n}` : 'помощника под уровень пока нет'}</em></span><span class="bar"><i style="width:${ray.score * 10}%"></i></span><span class="num">${ray.score}</span><span class="arrow">›</span></a>`).join('') + `</div>`;
    } else if (!prio.length) h += `<p class="desc">Оценок ещё нет — начните с <a href="#/opros">опросника</a> или Шкалы, тогда здесь появится самый слабый луч каждой сферы.</p>`;
    return h + `<p class="legend">Помощник подбирается под ваш уровень: советы для верхних ступеней не показываются. «Взять в Путь» создаёт шаг в папке «Путь» сферы; задачу в менеджере задач поставит Claude, если попросите.</p>`;
  }

  // «Взять в Путь» — как sled_shag.py --vzyat
  function vzyat(name){
    const h = helpers().find(x => x.name === name); if (!h){ toast('Помощник не найден или скрыт'); return; }
    const kod = h.luch.split(' / ')[0], zone = h.luch.includes(' / ') ? h.luch.split(' / ').slice(1).join(' / ') : null;
    const sp = S.spheres.find(s => s.kod === kod.split('.')[0]), ray = sp && sp.rays.find(r => r.kod === kod);
    if (!ray){ toast(`Луча ${kod} нет`); return; }
    const taken = pathSteps(sp).find(x => x.text.includes(`[[${name}]]`)); if (taken){ toast(`Уже взят: ${taken.file}`); return; }
    const title = name.split('—').slice(1).join('—').trim();
    const path = `${SPH_DIR}/${sp.dir}/Путь/${sp.kod} Шаг — ${title}.md`;
    if (S.paths.includes(path)){ toast('Такой шаг уже есть'); return; }
    const z = zone ? ray.zones.find(x => x.name === zone) : null, lvl = zone ? (z ? z.score : null) : ray.score, step = stepsOf(ray)[zone || ray.name];
    const d = today(), stem = ray.stem;
    const body = [`# ${title}`, '', `Помощник: [[${name}]] · Луч: [[${stem}]]` + (zone ? `, зона «${zone}»` : ''), ''];
    if (lvl != null) body.push(`Сейчас — ${lvl} из 10; помощник для отрезка ${h.urovni}.`);
    if (step) body.push(`Шаг вверх (${step[0]} → ${step[1]}): ${step[2]}`);
    body.push('', '## Первая практика', '', h.practice || '— (см. карточку помощника)', '', `*Взято в «Путь» ${d} через «Следующий шаг».*`, '');
    const fm = ['---', 'тип: шаг', `сфера: "[[${sp.dir}]]"`, `луч: ${ray.name}`, 'важность:', 'простота: 4', 'статус: в работе', `обновлено: ${d}`, '---'];
    change(path, {type: 'create', content: [...fm, ...body].join('\n')}, `Шаг в Путь: ${title}`);
    const same = pathSteps(sp).filter(x => x.luch === ray.name && x.path !== path);
    toast(same.length ? `Шаг взят. По этому лучу уже есть шагов: ${same.length}` : 'Шаг взят в «Путь»');
  }

  return {
    menu: {title: 'Следующий шаг', order: 20, sub: () => {
      const pr = S.spheres.filter(s => s.prio).sort((a, b) => a.prio - b.prio);
      return pr.length ? `Что делать дальше: ${pr.map(s => s.name).join(', ')}` : 'Самый слабый луч сфер-приоритетов и помощники под ваш уровень';
    }},
    need: p => isPom(p) || isPut(p),
    view(){ return screen(); },
    act(a, b){
      if (a === 'open'){ st.open = st.open === b.dataset.id ? null : b.dataset.id; render(); return; }
      if (a === 'vzyat'){ vzyat(b.dataset.id); return; }
    },
  };
})();
