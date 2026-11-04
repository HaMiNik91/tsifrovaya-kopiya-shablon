// Экран «Что нового» (апгрейд 5.1): версии шаблона, своя версия копии, сделанные пожелания людей.
// Источники: «00 Старт/Что нового.md» своей копии и открытого шаблона; пожелания — Issues шаблона с меткой «сделано».
'use strict';
(window.EKRANY = window.EKRANY || {}).novoe = (() => {
  const FILE = '00 Старт/Что нового.md';
  const st = {tpl: null, issues: null, err: ''};          // из открытого шаблона: текст и пожелания
  const ver = t => t ? String(readFm(t)['версия'] || '').trim() : '';
  const cmp = (a, b) => { const x = a.split('.').map(Number), y = b.split('.').map(Number);
    for (let i = 0; i < Math.max(x.length, y.length); i++){ const d = (x[i] || 0) - (y[i] || 0); if (d) return d; } return 0; };
  const versions = t => { // «## 1.4 — ноябрь 2026» → {v, title, body}
    const out = []; let cur = null;
    for (const ln of (t || '').replace(FM, '').split('\n')){
      const m = ln.match(/^## (\d+(?:\.\d+)*)\s*(?:—\s*(.*))?$/);
      if (m){ cur = {v: m[1], when: m[2] || '', body: []}; out.push(cur); }
      else if (cur && !/^#/.test(ln)) cur.body.push(ln);
    }
    return out;
  };
  async function fetchTpl(){
    const [o, n] = CFG.template.split('/');
    try {
      const r = await fetch(`https://raw.githubusercontent.com/${o}/${n}/main/${encPath(FILE)}`, {cache: 'no-store'});
      st.tpl = r.ok ? norm(await r.text()) : '';
    } catch(e){ st.tpl = ''; st.err = 'шаблон не открылся'; }
    try { // без ключа: пожелания открытого шаблона видны всем
      const r = await fetch(`${API}/repos/${o}/${n}/issues?labels=${encodeURIComponent('сделано')}&state=all&per_page=30`, {headers: {'Accept': 'application/vnd.github+json'}});
      st.issues = r.ok ? (await r.json()).filter(i => !i.pull_request) : [];
    } catch(e){ st.issues = []; }
    if (route()[0] === 'novoe') render();
  }
  return {
    menu: {title: 'Что нового', order: 90, sub: () => {
      const mine = ver(view(FILE)), t = ver(st.tpl);
      return t && mine && cmp(t, mine) > 0 ? `Вышла версия ${t} — у вас ${mine}` : 'Что менялось в шаблоне и чьи пожелания уже сделаны';
    }},
    need: p => p === FILE,
    view(){
      const mine = view(FILE), my = ver(mine), tv = ver(st.tpl);
      const text = st.tpl || mine || '';
      let h = `<nav class="crumbs"><a href="#/">Колесо</a><span>›</span><span>Что нового</span></nav>`;
      h += head(tv || my || null, 'Что нового', 'Что менялось в шаблоне — новое сверху', null, 'версия', '');
      if (st.tpl == null && S.mode !== 'embedded') h += `<div class="note">Смотрю, что нового в шаблоне…</div>`;
      if (S.mode === 'live' && my && tv && cmp(tv, my) > 0){
        const url = `https://github.com/${S.owner}/${S.repo}/actions/workflows/obnovlenie.yml`;
        h += `<div class="step"><b class="t">Есть обновление: ${esc(my)} → ${esc(tv)}</b>
          <p class="desc" style="color:inherit">Ваши оценки, записи и правки останутся. На GitHub нажмите <b>Run workflow</b> (Запустить), затем зелёную <b>Run workflow</b> ещё раз. Через 2–3 минуты копия обновится.</p>
          <div class="pick"><a class="btn main" href="${url}" target="_blank" rel="noopener">Обновить копию</a></div></div>`;
      } else if (S.mode === 'live' && my) h += `<p class="legend">Ваша копия — версия ${esc(my)}${tv && cmp(tv, my) === 0 ? ', самая новая' : ''}.</p>`;
      if (st.issues && st.issues.length){
        h += `<div class="card"><h2>Сделано по вашим пожеланиям</h2><div class="prose"><ul>` +
          st.issues.slice(0, 10).map(i => `<li>${esc(i.title)}</li>`).join('') + `</ul></div>
          <p class="legend">Пожелания присылают люди через «Предложить идею»; сделанное попадает сюда.</p></div>`;
      }
      for (const v of versions(text)){
        const isNew = my && cmp(v.v, my) > 0;
        h += `<div class="card"><div class="twh"><h2>${esc(v.v)}</h2><span class="legend">${esc(v.when)}${isNew ? ' · <b>ещё нет у вас</b>' : ''}</span></div><div class="prose">${md(v.body.join('\n').replace(/\s*\(\[\[[^\]]+\]\]\)/g, ''))}</div></div>`;
      }
      if (!text) h += `<div class="note">Файла «Что нового» нет ни в копии, ни в шаблоне.</div>`;
      return h;
    },
    after(){ this.fon(); },
    fon(){ if (st.tpl == null && !st.loading && S.mode !== 'embedded'){ st.loading = true; nuzhny(p => p === FILE).catch(() => {}).then(fetchTpl).then(() => { if (!route()[0]) render(); }); } },
  };
})();
