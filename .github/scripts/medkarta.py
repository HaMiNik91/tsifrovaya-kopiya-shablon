#!/usr/bin/env python3
"""Медкарта: проверка формы и подсчёты. Правила — CLAUDE.md, пп. 5.2 («Медкарта»), 5.4.

Запуск из корня хранилища:
    python3 .github/scripts/medkarta.py           — проверить и показать посчитанное (ничего не пишет)
    python3 .github/scripts/medkarta.py --write   — записать посчитанное в шапки

Ищет папки «Медкарта» во всех сферах (10 Сферы/*/Медкарта/**.md) и смотрит на свойство `тип`:
  • проблема     — `статус` одно из: открыто, лечится, наблюдение, закрыто; у «закрыто» желательно `до`.
  • обследование — `периодичность` (месяцев, целое) и `последнее` ("ГГГГ-ММ" или "ГГГГ-ММ-ДД", пусто — ещё не было).
                   Пишет `следующее` = последнее + периодичность ("ГГГГ-ММ"); если не было — "сейчас".
                   Просроченное показывает предупреждением.
  • карта тела   — таблицы `| Пункт | Состояние | Проверка | Пояснение |`. Состояние: не беспокоит, беспокоит,
                   наблюдение, не знаю. Пишет `пунктов`, `здоров` (% «не беспокоит» + «наблюдение» среди отмеченных),
                   `отмечено` (% пунктов с известным состоянием), `проверено` (% с непустой проверкой),
                   `беспокоит` (число). У «беспокоит» и «наблюдение» в пояснении нужна ссылка [[…]] — иначе предупреждение.
  • замеры       — список `замеры`: "Что, единица: число" или "нет". Пишет `расчёт`: индекс массы тела,
                   талия к росту, доля жира по способу ВМС США (US Navy, мужчины: 86,010·lg(талия − шея)
                   − 70,041·lg(рост) + 36,76, всё в дюймах). Нет нужных замеров — «нет».
Округление процентов и расчётов — как у Шкалы: ,5 вниз (shkala.rnd).
Код выхода 1 — ошибка формы.
"""
import argparse
import datetime
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shkala import FM, read_fm, write_fm, rnd, num  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPHERES = ROOT / "10 Сферы"
PROBLEM = ("открыто", "лечится", "наблюдение", "закрыто")
STATE = ("не беспокоит", "беспокоит", "наблюдение", "не знаю")
MONTH = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def pct(a, b):
    return rnd(100 * a / b) if b else None


def body_map(path, text, errors, warnings):
    body = text[FM.match(text).end():] if FM.match(text) else text
    rows, in_table, section = [], False, ""
    for line in body.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        if line.startswith("|"):
            c = cells(line)
            if c[:2] == ["Пункт", "Состояние"]:
                in_table = True
                continue
            if in_table and set("".join(c)) <= set("-: "):
                continue
            if in_table:
                if len(c) < 4:
                    errors.append(f"{path.name}: «{section}» — строка без 4 столбцов: {line.strip()}")
                    continue
                item, state, check, note = c[:4]
                if state not in STATE:
                    errors.append(f"{path.name}: «{item}» — состояние «{state}», нужно одно из: {', '.join(STATE)}")
                    continue
                if state in ("беспокоит", "наблюдение") and "[[" not in note:
                    warnings.append(f"{path.name}: «{item}» — {state}, но в пояснении нет ссылки на проблему или шаг")
                rows.append((item, state, check))
        else:
            in_table = False
    if not rows:
        errors.append(f"{path.name}: нет ни одной таблицы «| Пункт | Состояние | Проверка | Пояснение |»")
        return None
    n = len(rows)
    known = [r for r in rows if r[1] != "не знаю"]
    ok = sum(1 for r in known if r[1] in ("не беспокоит", "наблюдение"))
    return {"пунктов": n,
            "здоров": pct(ok, len(known)),
            "отмечено": pct(len(known), n),
            "проверено": pct(sum(1 for r in rows if r[2]), n),
            "беспокоит": sum(1 for r in rows if r[1] == "беспокоит")}


def next_check(path, fm, errors, warnings, today):
    try:
        months = int(str(fm.get("периодичность") or "").strip())
    except ValueError:
        errors.append(f"{path.name}: `периодичность` — целое число месяцев")
        return None
    last = fm.get("последнее") or ""
    if isinstance(last, list):
        last = ""
    if not last:
        warnings.append(f"{path.name}: ещё не было — пора")
        return "сейчас"
    m = MONTH.match(last)
    if not m:
        errors.append(f"{path.name}: `последнее` «{last}» — нужно ГГГГ-ММ или ГГГГ-ММ-ДД")
        return None
    y, mo = int(m.group(1)), int(m.group(2)) - 1 + months
    nxt = f"{y + mo // 12}-{mo % 12 + 1:02d}"
    if nxt < today.strftime("%Y-%m"):
        warnings.append(f"{path.name}: срок прошёл ({nxt})")
    return nxt


def measures(path, fm, errors):
    vals = {}
    items = fm.get("замеры") or []
    if not isinstance(items, list):
        items = []
    for it in items:
        if ":" not in it:
            errors.append(f"{path.name}: строка замера «{it}» — нужно «Что, единица: число»")
            continue
        k, v = (x.strip() for x in it.rsplit(":", 1))
        if v == "нет":
            vals[k] = None
            continue
        try:
            vals[k] = float(v.replace(",", "."))
        except ValueError:
            errors.append(f"{path.name}: замер «{k}» — «{v}» не число и не «нет»")
    h, w = vals.get("Рост, см"), vals.get("Вес, кг")
    waist, neck = vals.get("Талия, см"), vals.get("Шея, см")
    bmi = w / (h / 100) ** 2 if h and w else None
    ratio = waist / h if h and waist else None
    fat = None
    if h and waist and neck and waist > neck:
        inch = 2.54
        fat = 86.010 * math.log10((waist - neck) / inch) - 70.041 * math.log10(h / inch) + 36.76

    def show(x, digits):
        return "нет" if x is None else num(round(x, digits))
    return [f"Индекс массы тела: {show(bmi, 1)}",
            f"Талия к росту: {show(ratio, 2)}",
            f"Доля жира, %: {'нет' if fat is None else rnd(fat)}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    errors, warnings, today = [], [], datetime.date.today()
    files = sorted(p for p in SPHERES.glob("*/Медкарта/**/*.md"))
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm = read_fm(text)
        kind = fm.get("тип")
        values, after = None, None
        if kind == "проблема":
            st = fm.get("статус")
            if st not in PROBLEM:
                errors.append(f"{p.name}: статус «{st}», нужно одно из: {', '.join(PROBLEM)}")
            print(f"• {p.stem}: {st}")
        elif kind == "обследование":
            nxt = next_check(p, fm, errors, warnings, today)
            print(f"• {p.stem}: следующее {nxt}")
            values, after = {"следующее": f'"{nxt}"'} if nxt else None, "последнее"
        elif kind == "карта тела":
            res = body_map(p, text, errors, warnings)
            if res:
                print(f"• {p.stem}: пунктов {res['пунктов']}, здоров {res['здоров']} %, отмечено {res['отмечено']} %, "
                      f"проверено {res['проверено']} %, беспокоит {res['беспокоит']}")
                values, after = res, "луч"
        elif kind == "замеры":
            calc = measures(p, fm, errors)
            print(f"• {p.stem}: " + "; ".join(calc))
            values, after = {"расчёт": calc}, "измерено"
        if a.write and values:
            if write_fm(p, values, after=after):
                print("   записано:", p.stem)
    for w in warnings:
        print("⚠", w)
    for e in errors:
        print("✖", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
