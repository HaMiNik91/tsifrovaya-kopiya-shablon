#!/usr/bin/env python3
"""Инструменты сфер: проверка формы и подсчёты. Правила — CLAUDE.md, пп. 5.3 («Инструменты»), 5.4.

Запуск из корня хранилища:
    python3 .github/scripts/instrumenty.py           — проверить и показать посчитанное (ничего не пишет)
    python3 .github/scripts/instrumenty.py --write   — записать посчитанное в файлы

Смотрит папки «Инструменты» всех сфер (10 Сферы/*/Инструменты/*.md) и свойство `тип`:
  • инструмент — карточка `NN Инструмент — Название.md`: `вид` одно из VIDY, `научность` одно из NAUCH
                 (пусто — предупреждение), `перепройти` — целое число месяцев или пусто, `сфера` — своя сфера,
                 `скрыт` — true/false. Таблица вопросов в разделе «## Вопросы»
                 (`| № | Вопрос | Оригинал | Шкала | Наоборот |`): номера подряд с 1, вопрос и шкала не пустые,
                 «Наоборот» — пусто или «да»; показывает число вопросов по шкалам. Таблицы нет — предупреждение.
                 Пишет `последнее` — дата самого позднего прохождения ("" — ещё не проходил) и `следующее` =
                 последнее + перепройти ("ГГГГ-ММ"; "" — если нет прохождений или срока). Срок прошёл — предупреждение.
  • результат  — прохождение `NN ГГГГ-ММ-ДД Тест — Название.md`: `инструмент` — ссылка на карточку из любой сферы,
                 `когда` — "ГГГГ-ММ-ДД", `результаты` — строки «Шкала: значение» (число или слово, «нет» — не посчитано).
                 Пишет в тело, между строками-метками раздела «Изменения с прошлого раза», сравнение с предыдущим
                 прохождением того же инструмента: у чисел — «было → стало (±разница)», у слов — «было → стало»,
                 без изменений — «без изменений». Первое прохождение — «первое прохождение».
  • инструменты — оглавление «NN Инструменты» (лежит в папке сферы, не здесь) — не проверяется.
Код выхода 1 — ошибка формы.
"""
import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shkala import FM, read_fm, write_fm, num  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPHERES = ROOT / "10 Сферы"
VIDY = ("тест", "опросник", "вдвоём", "список для разговора", "взгляд со стороны")
NAUCH = ("проверено", "частично", "популярное")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINK = re.compile(r"^\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]$")
START = "<!-- изменения: считает instrumenty.py -->"
END = "<!-- изменения: конец -->"
RESULT_NAME = re.compile(r"^\d{2} \d{4}-\d{2}-\d{2} Тест — .+$")
CARD_NAME = re.compile(r"^\d{2} Инструмент — .+$")


def text_val(v):
    return "" if isinstance(v, list) else (v or "").strip()


def to_num(s):
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def parse_results(path, fm, errors):
    out = {}
    items = fm.get("результаты") or []
    if not isinstance(items, list):
        errors.append(f"{path.name}: `результаты` — список строк «Шкала: значение»")
        return out
    for it in items:
        if ":" not in it:
            errors.append(f"{path.name}: строка результата «{it}» — нужно «Шкала: значение»")
            continue
        k, v = (x.strip() for x in it.rsplit(":", 1))
        if not k or not v:
            errors.append(f"{path.name}: строка результата «{it}» — пустое название или значение")
            continue
        if k in out:
            errors.append(f"{path.name}: шкала «{k}» указана дважды")
        out[k] = v
    if not out:
        errors.append(f"{path.name}: нет ни одной строки в `результаты`")
    return out


def compare(prev, cur):
    if prev is None:
        return ["- первое прохождение"]
    lines = []
    for k, v in cur.items():
        if k not in prev:
            lines.append(f"- {k}: новая шкала — {v}")
            continue
        a, b = to_num(prev[k]), to_num(v)
        if a is not None and b is not None:
            d = b - a
            lines.append(f"- {k}: без изменений ({v})" if d == 0 else
                         f"- {k}: {prev[k]} → {v} ({'+' if d > 0 else '−'}{num(round(abs(d), 2))})")
        else:
            lines.append(f"- {k}: без изменений ({v})" if prev[k] == v else f"- {k}: {prev[k]} → {v}")
    for k in prev:
        if k not in cur:
            lines.append(f"- {k}: в этот раз не считалась (было {prev[k]})")
    return lines


def check_table(path, text, errors, warnings):
    body = text[FM.match(text).end():] if FM.match(text) else text
    m = re.search(r"^## Вопросы\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    rows = []
    if m:
        head = False
        for line in m.group(1).splitlines():
            if not line.startswith("|"):
                continue
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if c[:2] == ["№", "Вопрос"]:
                head = True
                continue
            if head and set("".join(c)) <= set("-: "):
                continue
            if head:
                rows.append(c)
    if not rows:
        warnings.append(f"{path.name}: нет таблицы вопросов «| № | Вопрос | Оригинал | Шкала | Наоборот |»")
        return
    scales = {}
    for i, c in enumerate(rows, 1):
        if len(c) != 5:
            errors.append(f"{path.name}: вопрос {c[0] if c else '?'} — нужно 5 столбцов")
            continue
        n, q, _, sc, rev = c
        if n != str(i):
            errors.append(f"{path.name}: номер «{n}» вместо {i} — номера подряд с 1")
        if not q or not sc:
            errors.append(f"{path.name}: вопрос {n} — пустой текст или шкала")
        if rev not in ("", "да"):
            errors.append(f"{path.name}: вопрос {n} — «Наоборот» пусто или «да», а не «{rev}»")
        s = scales.setdefault(sc, [0, 0])
        s[0] += 1
        s[1] += rev == "да"
    print(f"• {path.stem}: вопросов {len(rows)} — " +
          "; ".join(f"{k}: {v[0]} (наоборот {v[1]})" for k, v in scales.items()))


def add_months(day, months):
    y, m = int(day[:4]), int(day[5:7]) - 1 + months
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    errors, warnings = [], []
    month_now = datetime.date.today().strftime("%Y-%m")
    files = sorted(SPHERES.glob("*/Инструменты/*.md"))
    cards, results = {}, []
    for p in files:
        fm = read_fm(p.read_text(encoding="utf-8"))
        kind = fm.get("тип")
        sphere = p.parent.parent.name
        own = f"[[{sphere}]]"
        if kind == "инструмент":
            if not CARD_NAME.match(p.stem):
                warnings.append(f"{p.name}: имя карточки — «NN Инструмент — Название»")
            if text_val(fm.get("сфера")) != own:
                errors.append(f"{p.name}: `сфера` — нужно \"{own}\" (сфера папки)")
            vid = text_val(fm.get("вид"))
            if vid not in VIDY:
                errors.append(f"{p.name}: вид «{vid}», нужно одно из: {', '.join(VIDY)}")
            nauch = text_val(fm.get("научность"))
            if not nauch:
                warnings.append(f"{p.name}: `научность` не указана")
            elif nauch not in NAUCH:
                errors.append(f"{p.name}: научность «{nauch}», нужно одно из: {', '.join(NAUCH)}")
            per = text_val(fm.get("перепройти"))
            months = None
            if per:
                if per.isdigit() and int(per) > 0:
                    months = int(per)
                else:
                    errors.append(f"{p.name}: `перепройти` «{per}» — целое число месяцев или пусто")
            check_table(p, p.read_text(encoding="utf-8"), errors, warnings)
            if p.stem in cards:
                errors.append(f"{p.name}: карточка с таким именем уже есть в {cards[p.stem]['path'].parent.parent.name}")
            cards[p.stem] = {"path": p, "months": months, "runs": []}
        elif kind == "результат":
            if not RESULT_NAME.match(p.stem):
                warnings.append(f"{p.name}: имя прохождения — «NN ГГГГ-ММ-ДД Тест — Название»")
            if text_val(fm.get("сфера")) != own:
                errors.append(f"{p.name}: `сфера` — нужно \"{own}\" (сфера папки)")
            day = text_val(fm.get("когда"))
            if not DATE.match(day):
                errors.append(f"{p.name}: `когда` «{day}» — нужно ГГГГ-ММ-ДД")
                day = None
            m = LINK.match(text_val(fm.get("инструмент")))
            if not m:
                errors.append(f"{p.name}: `инструмент` — ссылка на карточку: \"[[NN Инструмент — Название]]\"")
            res = parse_results(p, fm, errors)
            results.append({"path": p, "card": m.group(1).strip() if m else None, "day": day, "res": res})
        elif kind is None:
            errors.append(f"{p.name}: нет свойства `тип` (инструмент или результат)")
        else:
            errors.append(f"{p.name}: тип «{kind}» — в папке «Инструменты» только инструмент и результат")

    for r in results:
        if r["card"] is None:
            continue
        if r["card"] not in cards:
            errors.append(f"{r['path'].name}: карточка «{r['card']}» не найдена в папках «Инструменты»")
            continue
        if r["day"]:
            cards[r["card"]]["runs"].append(r)

    for name, c in sorted(cards.items()):
        runs = sorted(c["runs"], key=lambda r: (r["day"], r["path"].name))
        last = runs[-1]["day"] if runs else ""
        nxt = add_months(last, c["months"]) if last and c["months"] else ""
        if nxt and nxt < month_now:
            warnings.append(f"{name}: пора перепройти (срок {nxt})")
        print(f"• {name}: прохождений {len(runs)}, последнее {last or '—'}, следующее {nxt or '—'}")
        if a.write and write_fm(c["path"], {"последнее": f'"{last}"', "следующее": f'"{nxt}"'}, after="перепройти"):
            print("   записано:", name)
        prev = None
        for r in runs:
            lines = compare(prev, r["res"])
            prev = r["res"]
            if a.write:
                write_changes(r["path"], lines, errors)

    for w in warnings:
        print("⚠", w)
    for e in errors:
        print("✖", e)
    sys.exit(1 if errors else 0)


def write_changes(path, lines, errors):
    text = path.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        errors.append(f"{path.name}: нет меток раздела «Изменения с прошлого раза» (см. «Шаблон — Результат инструмента»)")
        return
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = head + START + "\n" + "\n".join(lines) + "\n" + END + tail
    if new != text:
        path.write_text(new, encoding="utf-8")
        print("   записано:", path.stem)


if __name__ == "__main__":
    main()
