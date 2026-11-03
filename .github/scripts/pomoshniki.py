#!/usr/bin/env python3
"""Помощники по лучам: проверка карточек «60 Помощники/Помощник — Название.md».
Правила — CLAUDE.md, п. 5.5 и 5.4 (`луч`, `уровни`, `помощь`, `научность`).

Запуск из корня хранилища:
    python3 .github/scripts/pomoshniki.py            — проверить (ничего не пишет)
    python3 .github/scripts/pomoshniki.py --svodka   — ещё сводка: помощники по лучам
                                                       и показательные лучи опросника без помощника

Что проверяется:
  • шапка: `тип: помощник`; `луч` — код существующего луча («01.03»), у луча с зонами — «КОД / Зона»
    (зона есть в `оценки` луча и обязательна, у луча без зон — не указывается);
    `сфера` — ссылка на оглавление сферы этого луча;
  • `уровни` — «N → M», 1 ≤ N < M ≤ 10;
  • `помощь` — совет · практика · инструмент; `научность` — проверено · частично · популярное
    (пусто — предупреждение);
  • в тексте — ссылка «Луч: [[…]]» на файл луча с этим кодом (иначе предупреждение: луч переименован?);
  • у луча есть раздел «## Помощники» (иначе предупреждение);
  • разделы карточки по шаблону; у `научность: популярное` в тексте пометка «слабо проверено».

Подбор (для «Следующего шага», этап 3.4): помощник подходит лучу на уровне L, если N ≤ L < M —
функция podhodit().
Код выхода 1 — ошибка (✖); предупреждения (⚠) код выхода не меняют.
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shkala import read_fm, ROOT  # noqa: E402
from oprosnik import sfery, spisok  # noqa: E402

PAPKA = ROOT / "60 Помощники"
OPROSNIK = ROOT / "80 Шаблоны" / "Опросник"
UROVNI = re.compile(r"^(\d+) → (\d+)$")
POMOSH = ("совет", "практика", "инструмент")
NAUCH = ("проверено", "частично", "популярное")
RAZDELY = ("Что даёт", "Насколько научный", "Что знать", "Что делать", "Инструмент",
           "Осторожно", "Как понять, что помогло", "Помогает и другим лучам", "Источник")
SSYLKA_LUCH = re.compile(r"Луч: \[\[([^\]|#]+)")


def uroven(s):
    """«3 → 5» → (3, 5) или None."""
    m = UROVNI.match(str(s or "").strip())
    if not m:
        return None
    n, k = int(m.group(1)), int(m.group(2))
    return (n, k) if 1 <= n < k <= 10 else None


def podhodit(urovni, l):
    """Подходит ли помощник с отрезком «N → M» лучу на уровне l: N ≤ l < M."""
    u = uroven(urovni)
    return bool(u) and u[0] <= l < u[1]


def pokazatelnye():
    """Коды показательных лучей из `уточнить` опросника (порядок файлов)."""
    out = []
    for f in sorted(OPROSNIK.glob("[0-9][0-9] Опросник.md")):
        for s in spisok(read_fm(f.read_text(encoding="utf-8")).get("уточнить")):
            k = s.split(" ", 1)[0]
            if k not in out:
                out.append(k)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--svodka", action="store_true")
    a = ap.parse_args()
    errors, warnings = [], []
    S = sfery()
    luchi = {}  # код → (сфера-папка, файл луча)
    for sf in S.values():
        for k, r in sf["rays"].items():
            luchi[k] = (sf["folder"], r["file"], r["zones"])
    po_luchu = {}
    files = sorted(PAPKA.glob("Помощник — *.md")) if PAPKA.exists() else []
    for f in files:
        who = f.stem
        text = f.read_text(encoding="utf-8")
        fm = read_fm(text)
        if fm.get("тип") != "помощник":
            errors.append(f"{who}: `тип` должен быть «помощник»")
        luch_v = str(fm.get("луч") or "")
        kod, _, zona = (x.strip() for x in luch_v.partition(" / "))
        if kod not in luchi:
            errors.append(f"{who}: нет луча с кодом «{kod}» (`луч` — код луча, п. 5.4)")
        else:
            folder, lfile, zony = luchi[kod]
            if zona and zona not in zony:
                errors.append(f"{who}: у луча {kod} нет зоны «{zona}» (есть: {', '.join(zony) or 'зон нет'})")
            if not zona and zony:
                errors.append(f"{who}: у луча {kod} есть зоны — укажите зону: «{kod} / Зона»")
            if fm.get("сфера") != f"[[{folder}]]":
                errors.append(f"{who}: `сфера` должна быть \"[[{folder}]]\" (луч {kod})")
            m = SSYLKA_LUCH.search(text)
            if not m or m.group(1).strip() != lfile:
                warnings.append(f"{who}: в тексте нет строки «Луч: [[{lfile}]]» (код {kod}) — луч переименован?")
            lp = ROOT / "10 Сферы" / folder / "Шкала" / f"{lfile}.md"
            if lp.exists() and "\n## Помощники" not in lp.read_text(encoding="utf-8"):
                warnings.append(f"{lfile}: нет раздела «## Помощники» (шаблон луча)")
        u = uroven(fm.get("уровни"))
        if not u:
            errors.append(f"{who}: `уровни` «{fm.get('уровни')}» — нужно «N → M», 1 ≤ N < M ≤ 10")
        if fm.get("помощь") not in POMOSH:
            errors.append(f"{who}: `помощь` «{fm.get('помощь')}» — нужно: {', '.join(POMOSH)}")
        n = fm.get("научность")
        if not n:
            warnings.append(f"{who}: пустая `научность`")
        elif n not in NAUCH:
            errors.append(f"{who}: `научность` «{n}» — нужно: {', '.join(NAUCH)}")
        elif n == "популярное" and "слабо проверено" not in text:
            warnings.append(f"{who}: у популярного нет пометки «слабо проверено»")
        net = [r for r in RAZDELY if f"\n## {r}" not in text]
        if net:
            warnings.append(f"{who}: нет разделов: {', '.join(net)}")
        if kod in luchi:
            po_luchu.setdefault(kod, []).append((u, fm.get("помощь"), who + (f" [зона «{zona}»]" if zona else ""), fm.get("скрыт") is True))
    print(f"помощников: {len(files)}, лучей с помощниками: {len(po_luchu)}")
    if a.svodka:
        for k in sorted(po_luchu):
            print(f"■ {k} {luchi[k][1]}")
            for u, p, who, skr in sorted(po_luchu[k], key=lambda x: x[0] or (0, 0)):
                print(f"   {u[0] if u else '?'} → {u[1] if u else '?'}  {p:<10} {who}{'  (скрыт)' if skr else ''}")
        bez = [k for k in pokazatelnye() if k not in po_luchu]
        print(f"показательные лучи опросника без помощника: {len(bez)}")
        for k in bez:
            print("   ", k, luchi.get(k, ("", "— нет луча"))[1])
    for w in warnings:
        print("⚠", w)
    for e in errors:
        print("✖", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
