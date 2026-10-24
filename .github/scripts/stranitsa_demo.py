#!/usr/bin/env python3
"""Демо страницы заполнения: docs/index.html + встроенные файлы лучей этого хранилища.

    python3 .github/scripts/stranitsa_demo.py OUT.html

Получается одна страница без входа и без сети к GitHub: колесо, лучи, линейки — как у пустого шаблона.
Оценки и правки в демо живут только до перезагрузки. Нужна для просмотра, пока шаблон закрыт
(GitHub Pages для закрытых хранилищ недоступен), и для проверок программой.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "index.html"
WANT = re.compile(r"^10 Сферы/\d\d [^/]+/(Шкала/[^/]+\.md|\d\d Шкала\.md)$")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    files = {}
    for p in sorted(ROOT.rglob("*.md")):
        rel = p.relative_to(ROOT).as_posix()
        if WANT.match(rel) or rel == "80 Шаблоны/Шаблон — Шаг.md":
            files[rel] = p.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    page = re.sub(r"<!--CSP-->.*?<!--/CSP-->\n?", "", page, flags=re.S)  # чужая обёртка страницы — без своих запретов
    # страница-артефакт: оболочку (doctype, html, head, body, charset, viewport) добавляет сам Claude
    for tag in (r"<!doctype html>\n", r"<html[^>]*>\n", r"</?head>\n", r"</?body>\n", r"</html>\n?",
                r'<meta charset="utf-8">\n', r'<meta name="viewport"[^>]*>\n'):
        page = re.sub(tag, "", page, count=2, flags=re.I)
    page = page.replace("<title>Цифровая копия</title>", "<title>Демо Цифровой копии</title>", 1)
    data = json.dumps(files, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("<script>\n'use strict';", f"<script>window.DEMO_FILES = {data};</script>\n<script>\n'use strict';", 1)
    pathlib.Path(sys.argv[1]).write_text(page, encoding="utf-8")
    rays = sum(1 for k in files if "/Шкала/" in k)
    print(f"демо: {sys.argv[1]} — лучей {rays}, файлов {len(files)}")


if __name__ == "__main__":
    main()
