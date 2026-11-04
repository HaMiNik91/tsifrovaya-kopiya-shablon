// Общее для экранов: разметка Markdown → HTML с таблицами (выгрузка, итоги денег и др.).
// Нужны esc и cells из основного скрипта страницы — они вызываются позже, когда он уже загружен.
'use strict';
// ───────── Markdown → HTML: заголовки, списки, галочки, таблицы, жирный, курсив, ссылки [[…]] ─────────
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
