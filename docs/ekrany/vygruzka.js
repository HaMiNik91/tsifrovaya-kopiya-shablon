// Экран «Выгрузка» (апгрейд 5.1): всё или часть копии одним файлом — PDF (печать страницы → «Сохранить как PDF»)
// или текстом (.md). Например, только Медкарту — для врача. Всё собирается в браузере; на сервер ничего не уходит.
'use strict';
(window.EKRANY = window.EKRANY || {}).vygruzka = (() => {
  const isMd = p => p.endsWith('.md');
  const NOT = /^(80 Шаблоны|60 Помощники|90 Архив|docs|worker|\.github|\.obsidian)\//;
  const sph = p => (p.match(/^10 Сферы\/(\d\d [^/]+)\//) || [])[1];
  // части: имя → {title, sub, test}; сферы добавляются сами
  function parts(){
    const out = [
      {k: 'koleso', title: 'Колесо и оценки', sub: 'сферы, лучи, зоны — одной таблицей', gen: true},
      {k: 'medkarta', title: 'Медкарта', sub: 'для врача: проблемы, обследования, документы, замеры', test: p => /^10 Сферы\/01 [^/]+\/Медкарта\//.test(p) || /^10 Сферы\/01 [^/]+\/01 Медкарта\.md$/.test(p)},
      {k: 'pitomcy', title: 'Медкарты питомцев', sub: 'для ветеринара', test: p => /^10 Сферы\/07 [^/]+\/Медкарта\//.test(p)},
      {k: 'dengi', title: 'Деньги', sub: 'настройки и месяцы', test: p => /^10 Сферы\/10 [^/]+\/Деньги\//.test(p)},
      {k: 'zhurnal', title: 'Журнал и планы недели', sub: '20 Журнал', test: p => p.startsWith('20 Журнал/')},
      {k: 'lyudi', title: 'Люди', sub: '40 Люди', test: p => p.startsWith('40 Люди/')},
      {k: 'vetki', title: 'Ветки событий', sub: '70 Ветки', test: p => p.startsWith('70 Ветки/')},
      {k: 'start', title: 'Старт', sub: 'Профиль, Время и внимание, Летопись жизни и др.', test: p => p.startsWith('00 Старт/')},
    ];
    for (const s of [...S.spheres, ...S.hidden]) out.push({k: 's' + s.nn, title: `${s.nn} ${s.name}`, sub: 'вся сфера', sphere: s.dir,
      test: p => sph(p) === s.dir});
    return out.map(x => ({...x, files: x.gen ? [] : S.paths.filter(p => isMd(p) && !NOT.test(p) && x.test(p)).sort()}));
  }
  const st = {pick: new Set(['koleso']), built: null, busy: false};

  // ───────── Markdown → HTML для печати: заголовки, списки, галочки, таблицы, жирный, курсив, ссылки [[…]] ─────────
  const inl = s => esc(s).replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '$2').replace(/\[\[([^\]]+)\]\]/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>').replace(/`([^`]+)`/g, '<code>$1</code>');
  function mdFull(text){
    const L = text.split('\n'); let out = '', i = 0, list = null;
    const close = () => { if (list){ out += `</${list}>`; list = null; } };
    while (i < L.length){
      const ln = L[i], t = ln.trim();
      if (/^```/.test(t)){ close(); i++; while (i < L.length && !/^```/.test(L[i].trim())) i++; i++; continue; } // таблицы Obsidian (base) — не печатаются
      if (/^<!--.*-->$/.test(t) || /^← /.test(t)){ i++; continue; }
      const h = t.match(/^(#{1,6})\s+(.*)$/);
      if (h){ close(); const n = Math.min(h[1].length + 1, 5); out += `<h${n}>${inl(h[2])}</h${n}>`; i++; continue; }
      if (/^\|.*\|$/.test(t)){
        close(); const rows = [];
        while (i < L.length && /^\|.*\|$/.test(L[i].trim())){ rows.push(cells(L[i])); i++; }
        const body = rows.filter((r, k) => !(k === 1 && r.every(c => /^:?-{2,}:?$/.test(c))));
        out += `<table>${body.map((r, k) => `<tr>${r.map(c => k === 0 && rows.length > 1 && rows[1].every(x => /^:?-{2,}:?$/.test(x)) ? `<th>${inl(c)}</th>` : `<td>${inl(c)}</td>`).join('')}</tr>`).join('')}</table>`;
        continue;
      }
      const li = t.match(/^(?:[-*]|\d+\.)\s+(.*)$/);
      if (li){ const tag = /^\d/.test(t) ? 'ol' : 'ul'; if (list !== tag){ close(); out += `<${tag}>`; list = tag; }
        out += `<li>${inl(li[1]).replace(/^\[ \]\s*/, '☐ ').replace(/^\[x\]\s*/i, '☑ ')}</li>`; i++; continue; }
      close();
      if (t) out += `<p>${inl(t)}</p>`;
      i++;
    }
    close(); return out;
  }
  const SKIP = new Set(['aliases', 'сфера', 'обновлено', 'тип']);
  function fmLine(text){ // шапка — одной строкой мелко: статус, даты, оценки
    const fm = readFm(text), parts_ = [];
    for (const [k, v] of Object.entries(fm)){
      if (SKIP.has(k) || v == null || (Array.isArray(v) && !v.length) || v === '' || v === '""') continue;
      parts_.push(`<b>${esc(k)}:</b> ${esc(Array.isArray(v) ? v.join('; ') : v).replace(/\[\[([^\]|]+)(\|[^\]]+)?\]\]/g, '$1')}`);
    }
    return parts_.length ? `<p class="fm">${parts_.join(' · ')}</p>` : '';
  }
  function kolesoHtml(){
    let h = `<h2>Колесо и оценки</h2><p class="fm">на ${esc(today())}; оценка — среднее нижних уровней (,5 и меньше — вниз)</p><table><tr><th>Сфера / луч / зона</th><th>Оценка</th></tr>`;
    const w = wheelScore(); h += `<tr><td><b>Колесо</b></td><td><b>${fmt(w.score)}</b></td></tr>`;
    for (const s of S.spheres){
      h += `<tr><td><b>${esc(s.nn)} ${esc(s.name)}</b></td><td><b>${fmt(s.score)}</b></td></tr>`;
      for (const r of s.rays){
        h += `<tr><td>&nbsp;&nbsp;${esc(r.name)}${r.approx ? ' (примерно)' : ''}</td><td>${fmt(r.score)}</td></tr>`;
        for (const z of r.zones) h += `<tr><td>&nbsp;&nbsp;&nbsp;&nbsp;— ${esc(z.name)}</td><td>${fmt(z.score)}</td></tr>`;
      }
    }
    return h + `</table>`;
  }
  function kolesoMd(){
    const w = wheelScore(); let m = `# Колесо и оценки (${today()})\n\n| Сфера / луч / зона | Оценка |\n|---|---|\n| **Колесо** | ${fmt(w.score)} |\n`;
    for (const s of S.spheres){ m += `| **${s.nn} ${s.name}** | ${fmt(s.score)} |\n`;
      for (const r of s.rays){ m += `| ${r.name}${r.approx ? ' (примерно)' : ''} | ${fmt(r.score)} |\n`; for (const z of r.zones) m += `| — ${z.name} | ${fmt(z.score)} |\n`; } }
    return m;
  }
  async function build(){
    const P = parts().filter(x => st.pick.has(x.k)), files = [...new Set(P.flatMap(x => x.files))];
    st.busy = true; render();
    try { await nuzhny(p => files.includes(p)); } finally { st.busy = false; }
    let html = '', md_ = `<!-- Выгрузка «Цифровой копии» ${today()} -->\n\n`;
    for (const x of P){
      if (x.gen){ html += `<section>${kolesoHtml()}</section>`; md_ += kolesoMd() + '\n'; continue; }
      html += `<section><h2>${esc(x.title)}</h2>`; md_ += `# ${x.title}\n\n`;
      for (const p of x.files){
        const t = view(p); if (t == null) continue;
        const name = p.split('/').pop().replace(/\.md$/, '');
        const body = t.replace(FM, '').replace(/^# .*\n/, '');
        html += `<article><h3>${esc(name)}</h3><p class="fm path">${esc(p)}</p>${fmLine(t)}${mdFull(body)}</article>`;
        md_ += `## ${name}\n\n*${p}*\n\n${t.replace(FM, '').replace(/^# .*\n/, '').trim()}\n\n---\n\n`;
      }
      html += `</section>`;
    }
    st.built = {html, md: md_, n: files.length, parts: P.map(x => x.title)};
    render();
  }

  function screen(){
    const P = parts();
    let h = `<nav class="crumbs noprint"><a href="#/">Колесо</a><span>›</span><span>Выгрузка</span></nav>`;
    if (st.built){
      h += `<div class="noprint">${head(st.built.n || null, 'Выгрузка готова', st.built.parts.join(', '), null, 'файлов', '')}
        <div class="pick"><button class="btn main" data-act="vygruzka:print">Сохранить PDF / печать</button><button class="btn" data-act="vygruzka:md">Скачать текстом (.md)</button><button class="btn" data-act="vygruzka:back">Выбрать другое</button></div>
        <p class="legend">PDF: в окне печати выберите «Сохранить как PDF». Файл остаётся только у вас — отдать его врачу или кому-то ещё решаете вы.</p></div>
        <div class="print-doc"><h1>Цифровая копия — выгрузка ${esc(today())}</h1>${st.built.html}</div>`;
      return h;
    }
    h += head(null, 'Выгрузка', 'Всё или часть копии одним файлом — PDF или текстом', null, 'файл', '');
    h += `<p class="desc">Отметьте, что выгрузить. Например, для врача — только Медкарту. Всё собирается здесь, в браузере.</p><div class="card">`;
    for (const x of P){
      if (!x.gen && !x.files.length) continue;
      h += `<label class="chk"><input type="checkbox" data-ch="vygruzka:pick" value="${x.k}" ${st.pick.has(x.k) ? 'checked' : ''}><span><b>${esc(x.title)}</b> <span class="legend">${esc(x.sub)}${x.gen ? '' : ` · файлов: ${x.files.length}`}</span></span></label>`;
    }
    h += `<div class="pick"><button class="btn" data-act="vygruzka:all">Отметить всё</button><button class="btn" data-act="vygruzka:none">Снять всё</button></div></div>`;
    const n = new Set(P.filter(x => st.pick.has(x.k)).flatMap(x => x.files)).size;
    h += `<div class="pick"><button class="btn main" data-act="vygruzka:build" ${st.pick.size && !st.busy ? '' : 'disabled'}>${st.busy ? 'Собираю…' : `Собрать${n ? ` (файлов: ${n})` : ''}`}</button></div>`;
    return h;
  }

  return {
    menu: {title: 'Выгрузка', order: 80, sub: 'Всё или часть одним файлом — например, Медкарта для врача'},
    view(){ return screen(); },
    act(a){
      if (a === 'build'){ build().catch(e => { st.busy = false; toast(`Не собралось: ${e.message}`); render(); }); return; }
      if (a === 'all'){ for (const x of parts()) if (x.gen || x.files.length) st.pick.add(x.k); render(); return; }
      if (a === 'none'){ st.pick.clear(); render(); return; }
      if (a === 'back'){ st.built = null; render(); return; }
      if (a === 'print'){ window.print(); return; }
      if (a === 'md'){
        const url = URL.createObjectURL(new Blob([st.built.md], {type: 'text/markdown;charset=utf-8'}));
        const x = document.createElement('a'); x.href = url; x.download = `Цифровая копия ${today()}.md`; document.body.appendChild(x); x.click(); x.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000); toast('Файл скачан'); return;
      }
    },
    change(a, el){ if (a === 'pick'){ el.checked ? st.pick.add(el.value) : st.pick.delete(el.value); render(); } },
  };
})();
