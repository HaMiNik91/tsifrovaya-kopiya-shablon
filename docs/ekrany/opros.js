// Экран «Опросник» (апгрейд 5.1): колесо за 10–15 минут. Правила — «80 Шаблоны/Опросник/Опросник.md».
// Шаг 1 — общий вопрос сферы: ответ ставит свой уровень всем видимым лучам сферы в строки `оценки`, где `нет`,
//   и пометку `точность: примерно`; поставленные оценки не трогаются.
// Шаг 2 — уточнения (`уточнить`): простой ответ → кусок линейки полными словами → свой уровень.
//   Луч без зон уточнён — `точность` пустая; зона уточнена — луч остаётся «примерно».
// В начале — «Есть пара?» и «Есть дети?»: без пары скрывается луч «Совместная жизнь» (06.04),
//   без детей не трогается зона «Свои дети» (07.01) — у неё остаётся `нет`.
'use strict';
(window.EKRANY = window.EKRANY || {}).opros = (() => {
  const DIR = '80 Шаблоны/Опросник/';
  const PARA = '06.04', DETI = {kod: '07.01', zone: 'Свои дети'};
  const KUSKI = {plo: [1, 4, 'Скорее плохо'], sre: [4, 7, 'Средне'], hor: [7, 10, 'Хорошо']};
  const st = {i: null, bucket: null};
  const key = () => `op.${S.owner || 'demo'}/${S.repo || ''}`;
  const pos = () => { if (st.i == null){ const v = parseInt(LS.get(key() + '.i'), 10); st.i = isFinite(v) ? v : 0; } return st.i; };
  const go = i => { st.i = i; st.bucket = null; LS.set(key() + '.i', String(i)); render(); scrollTo(0, 0); };
  const noKids = () => LS.get(key() + '.deti') === 'нет';

  const lines = v => Array.isArray(v) ? v : (v ? [v] : []);
  const rayBy = kod => { for (const sp of S.spheres) for (const r of sp.rays) if (r.kod === kod) return {sp, r}; return null; };
  function opros(sp){ // файл опросника сферы по её коду
    const p = S.paths.find(x => x.startsWith(DIR) && /^\d\d Опросник\.md$/.test(x.slice(DIR.length)) && readFm(view(x) || '')['код'] === sp.kod);
    if (!p) return null;
    const fm = readFm(view(p));
    const stup = lines(fm['ступени']).map(s => s.match(/^(\d+) — (.+)$/)).filter(Boolean).map(m => ({lvl: +m[1], text: m[2]}));
    const ut = lines(fm['уточнить']).map(s => s.match(/^(\d{2}\.\d{2})(?: \/ (.+?))? — (.+)$/)).filter(Boolean).map(m => ({kod: m[1], zone: m[2] || null, q: m[3]}));
    return {q: fm['вопрос'] || '', stup, ut};
  }
  function steps(){ // весь путь: начало, пара, дети, по сфере — общий вопрос и уточнения (у зоны с признаками — по признаку), конец
    const out = [{k: 'intro'}, {k: 'para'}, {k: 'deti'}];
    for (const sp of S.spheres){
      const o = opros(sp); if (!o || !o.stup.length) continue;
      out.push({k: 'main', sp, o});
      for (const u of o.ut){
        const hit = rayBy(u.kod); if (!hit) continue;
        if (noKids() && u.kod === DETI.kod && u.zone === DETI.zone) continue;
        const zone = u.zone ? hit.r.zones.find(z => z.name === u.zone) : null;
        if (u.zone && !zone) continue;
        if (zone && zone.signs.length) for (const sg of zone.signs) out.push({k: 'ut', sp, u, ray: hit.r, zone, sign: sg});
        else out.push({k: 'ut', sp, u, ray: hit.r, zone, sign: null});
      }
    }
    out.push({k: 'end'});
    return out;
  }
  const leafScore = s => s.sign ? s.sign.score : s.zone ? s.zone.score : s.ray.score;

  // Общий ответ: всем видимым лучам сферы — уровень в строки `нет`, `точность: примерно`
  function setMain(sp, lvl){
    const d = today(); let n = 0;
    for (const r of sp.rays){
      const skip = r.kod === DETI.kod && noKids() ? `${DETI.zone}` : null;
      const empty = r.leaves.filter(x => x.score == null && !(skip && (x.zone || x.name) === skip));
      if (!empty.length) continue;
      n++;
      change(r.path, {type: 'fn', fn: text => {
        const m = text.match(FM); if (!m) throw new Error('у файла нет шапки');
        const ls = m[1].split('\n').map(l => {
          const x = l.match(/^(\s+-\s+)"?(.+?):\s*нет"?\s*$/);
          if (!x || (skip && x[2].split(' / ')[0].trim() === skip)) return l;
          return `${x[1]}"${x[2]}: ${lvl}"`;
        });
        return touchFm(`---\n${ls.join('\n')}\n---\n` + text.slice(m[0].length), [['точность', 'примерно', 'вопрос'], ['оценено', d, 'луч'], ['обновлено', d, 'статус']]);
      }}, `Опросник: ${r.name} — примерно ${lvl}`);
    }
    return n;
  }

  function card(s, inner){
    const all = steps(), i = Math.min(pos(), all.length - 1), done = all.slice(0, i).filter(x => x.k === 'main').length, total = all.filter(x => x.k === 'main').length;
    return `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Опросник</span></nav>` +
      `<div class="sub">${s.sp ? `Сфера ${done + (s.k === 'main' ? 1 : 0)} из ${total} · ${esc(s.sp.nn)} ${esc(s.sp.name)}` : 'Опросник'}</div>` +
      `<div class="bar" aria-hidden="true"><i style="width:${Math.round(i / (all.length - 1) * 100)}%"></i></div>` + inner;
  }
  const back = i => i > 0 ? `<button class="btn" data-act="opros:go" data-i="${i - 1}">Назад</button>` : '';
  const skipBtns = (i, nobody) => `<div class="pick">${nobody ? `<button class="btn" data-act="opros:nobody" data-i="${i}">Нет такого человека</button>` : ''}<button class="btn" data-act="opros:go" data-i="${i + 1}">Не знаю</button><button class="btn" data-act="opros:go" data-i="${i + 1}">Пропустить</button>${back(i)}</div>`;

  function screen(){
    const all = steps(), i = Math.min(pos(), all.length - 1), s = all[i];
    const demo = S.mode !== 'live' ? `<div class="note">Демо: ответы здесь не сохраняются.</div>` : '';
    if (s.k === 'intro') return card(s, `${head(null, 'Опросник', 'Колесо за 10–15 минут: один вопрос на сферу и 2–3 уточнения', null, 'старт', '')}${demo}
      <div class="card"><p class="desc" style="color:inherit"><b>Оценки примерные.</b> Потом зайдите в каждую сферу и проверьте линейки — точную оценку даёт только чтение всей линейки.</p>
      <p class="legend">Любой вопрос можно пропустить и вернуться к нему позже. Уже поставленные оценки опросник не меняет. Можно прерваться — страница запомнит, где вы остановились.</p>
      <div class="pick"><button class="btn main" data-act="opros:go" data-i="1">Начать</button></div></div>`);
    if (s.k === 'para') return card(s, `<div class="card"><h2>Есть ли у вас сейчас пара?</h2>
      <p class="legend">Если пары нет, луч «Совместная жизнь» скроется — его можно вернуть в сфере 06.</p>
      <div class="pick"><button class="btn" data-act="opros:para" data-v="да">Есть</button><button class="btn" data-act="opros:para" data-v="нет">Нет</button><button class="btn" data-act="opros:go" data-i="${i + 1}">Пропустить</button>${back(i)}</div></div>`);
    if (s.k === 'deti') return card(s, `<div class="card"><h2>Есть ли у вас дети?</h2>
      <p class="legend">Если детей нет, вопросы о своих детях не зададутся — в луче «Дети» останутся готовность, принципы и дети рядом.</p>
      <div class="pick"><button class="btn" data-act="opros:deti" data-v="да">Есть</button><button class="btn" data-act="opros:deti" data-v="нет">Нет</button><button class="btn" data-act="opros:go" data-i="${i + 1}">Пропустить</button>${back(i)}</div></div>`);
    if (s.k === 'main'){
      const filled = s.sp.rays.filter(r => r.leaves.some(x => x.score == null)).length;
      return card(s, `<div class="card"><h2>${esc(s.o.q)}</h2>
        <div class="opr">${[...s.o.stup].reverse().map(x => `<button class="lv" data-act="opros:main" data-v="${x.lvl}"><b>${x.lvl}</b><span>${esc(x.text)}</span></button>`).join('')}</div>
        <p class="legend">${filled ? `Ответ поставит примерную оценку ${filled} ${filled === 1 ? 'лучу' : 'лучам'} сферы без оценки.` : 'У всех лучей сферы оценки уже есть — ответ их не изменит.'}</p>
        ${skipBtns(i, false)}</div>`);
    }
    if (s.k === 'ut'){
      const who = s.sign ? ` — ${s.sign.name}` : '', cur = leafScore(s);
      let h = `<div class="card"><h2>${esc(s.u.q)}${esc(who)}</h2><p class="legend">Луч «${esc(s.ray.name)}»${s.zone ? `, зона «${esc(s.zone.name)}»` : ''}${cur != null ? ` · сейчас ${cur}${s.ray.approx ? ' (примерно)' : ''}` : ''}</p>`;
      if (!st.bucket){
        h += `<div class="pick">${Object.entries(KUSKI).map(([k, v]) => `<button class="btn" data-act="opros:bucket" data-v="${k}">${v[2]}</button>`).join('')}</div>`;
        return card(s, h + skipBtns(i, !!s.sign) + `</div>`);
      }
      const [lo, hi] = KUSKI[st.bucket], o = ladderSpec(s.sp, s.ray, s.zone, s.sign);
      h += `<p class="desc">Выберите уровень, который про вас. Колеблетесь между двумя — берите нижний.</p><div class="opr">`;
      for (let l = hi; l >= lo; l--) h += `<button class="lv ${l === cur ? 'cur' : ''}" data-act="opros:lvl" data-v="${l}"><b>${l}</b><span>${esc(o.levels[l] ?? '—')}</span></button>`;
      h += `</div><div class="pick"><button class="btn" data-act="opros:bucket" data-v="">Другой ответ</button><button class="btn" data-act="opros:go" data-i="${i + 1}">Пропустить</button></div></div>`;
      return card(s, h);
    }
    // конец: какие 2–3 сферы проверить первыми — самые низкие и с наибольшим числом «примерных» лучей
    const rated = S.spheres.filter(x => x.score != null).map(x => ({x, ap: x.rays.filter(r => r.approx).length}))
      .sort((a, b) => a.x.score - b.x.score || b.ap - a.ap).slice(0, 3);
    const w = wheelScore();
    return card(s, `${head(w.score, 'Колесо заполнено', `Оценено сфер: ${w.rated} из ${S.spheres.length}`, null, 'жизнь', w.calc)}
      <div class="card"><h2>Что проверить первым</h2>${rated.length ? `<div class="rows">${rated.map(({x, ap}) => `<a class="row" href="#/${x.nn}"><span class="name">${esc(x.nn)} ${esc(x.name)}<em>${ap ? `примерно: ${ap} из ${x.rays.length} лучей` : 'всё по линейке'}</em></span><span class="bar"><i style="width:${x.score * 10}%"></i></span><span class="num">${x.score}</span><span class="arrow">›</span></a>`).join('')}</div>` : '<p class="desc">Оценок пока нет.</p>'}
      <p class="legend">Зайдите в сферу, пройдите линейки «примерных» лучей и поставьте свою цифру. Дальше — выбрать приоритеты в «Время и внимание».</p>
      <div class="pick"><a class="btn main" href="#/vremya">Время и внимание</a><button class="btn" data-act="opros:go" data-i="0">Пройти заново</button></div></div>`);
  }

  return {
    menu: {title: 'Опросник', order: 10, sub: () => {
      const all = S.spheres.flatMap(s => s.rays), none = all.filter(r => r.score == null).length;
      return none === all.length ? 'Заполнить колесо за 10–15 минут — с этого удобно начать' : `Быстро оценить лучи без оценки (${none} из ${all.length})`;
    }},
    need: p => p.startsWith(DIR),
    view(){ return screen(); },
    act(a, b){
      const all = steps(), i = Math.min(pos(), all.length - 1), s = all[i];
      if (a === 'go'){ go(+b.dataset.i); return; }
      if (a === 'para'){
        LS.set(key() + '.para', b.dataset.v);
        const hit = S.spheres.flatMap(x => [...x.rays, ...x.hiddenRays]).find(r => r.kod === PARA);
        if (hit && b.dataset.v === 'нет' && !hit.hidden){
          change(hit.path, {type: 'fm', sets: [['скрыт', 'true', 'код']], date: today()}, `Опросник: нет пары — скрыт луч «${hit.name}»`);
          toast(`Луч «${hit.name}» скрыт`);
        }
        go(i + 1); return;
      }
      if (a === 'deti'){ LS.set(key() + '.deti', b.dataset.v); go(i + 1); return; }
      if (a === 'main'){
        const n = setMain(s.sp, +b.dataset.v);
        toast(n ? `${s.sp.name}: примерно ${b.dataset.v} — лучей ${n}` : `${s.sp.name}: все лучи уже оценены`);
        go(i + 1); return;
      }
      if (a === 'bucket'){ st.bucket = b.dataset.v || null; render(); return; }
      if (a === 'lvl' || a === 'nobody'){
        const val = a === 'lvl' ? +b.dataset.v : null, k = s.sign ? s.sign.key : s.zone ? s.zone.key : s.ray.key;
        change(s.ray.path, {type: 'score', key: k, val, date: today(), exact: !s.zone},
          `Опросник: ${s.ray.name}${k !== s.ray.name ? ' — ' + k : ''}: ${val == null ? 'нет' : val}`);
        toast(val == null ? 'Отмечено: такого человека нет' : `${s.sign ? s.sign.name : s.zone ? s.zone.name : s.ray.name}: ${val}`);
        go(i + 1); return;
      }
    },
  };
})();
