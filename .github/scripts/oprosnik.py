#!/usr/bin/env python3
"""Опросник: проверка файлов «80 Шаблоны/Опросник/NN Опросник.md» и сборка набора данных.
Правила — «80 Шаблоны/Опросник/Опросник.md» и CLAUDE.md, п. 5.4 (`ступени`, `уточнить`).

Запуск из корня хранилища:
    python3 .github/scripts/oprosnik.py               — проверить (ничего не пишет)
    python3 .github/scripts/oprosnik.py --json OUT    — проверить и записать набор данных для страницы

Что проверяется:
  • шапка: `тип: опросник`, `код` — есть сфера с таким кодом, `вопрос` не пустой;
  • `ступени` — ровно 5 строк «N — текст», уровни 1–10 по возрастанию;
  • `уточнить` — 1–3 строки «КОД — вопрос» или «КОД / Зона — вопрос»: луч с кодом есть в этой сфере;
    зона есть в `оценки` луча; у луча с зонами зона указана; у луча без зон — не указана.
Код выхода 1 — ошибка.
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from shkala import read_fm, SPHERES, ROOT  # noqa: E402

PAPKA = ROOT / "80 Шаблоны" / "Опросник"
STUPEN = re.compile(r"^(\d+) — (.+)$")
UTOCH = re.compile(r"^(\d{2}\.\d{2})(?: / (.+?))? — (.+)$")


def spisok(v):
    return v if isinstance(v, list) else ([v] if v else [])


def sfery():
    """код сферы → {папка, лучи: код → {файл, зоны}}."""
    out = {}
    for folder in sorted(p for p in SPHERES.iterdir() if p.is_dir()):
        nn = folder.name[:2]
        ogl = folder / f"{folder.name}.md"
        kod = (read_fm(ogl.read_text(encoding="utf-8")).get("код") if ogl.exists() else None) or nn
        luchi = {}
        for p in sorted((folder / "Шкала").glob("*.md")):
            fm = read_fm(p.read_text(encoding="utf-8"))
            if fm.get("тип") != "луч" or not fm.get("код"):
                continue
            imya = fm.get("луч") or p.stem.split("— ", 1)[-1]
            zony = []
            for it in spisok(fm.get("оценки")):
                chast = it.rsplit(":", 1)[0].strip().split(" / ")[0].strip()
                if chast != imya and chast not in zony:
                    zony.append(chast)
            luchi[fm["код"]] = {"file": p.stem, "name": imya, "zones": zony}
        out[kod] = {"folder": folder.name, "rays": luchi}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json")
    a = ap.parse_args()
    errors, data = [], []
    S = sfery()
    files = sorted(PAPKA.glob("[0-9][0-9] Опросник.md"))
    if not files:
        errors.append(f"нет файлов опросника в {PAPKA.relative_to(ROOT)}")
    for f in files:
        fm = read_fm(f.read_text(encoding="utf-8"))
        who = f.stem
        if fm.get("тип") != "опросник":
            errors.append(f"{who}: `тип` должен быть «опросник»")
        kod = fm.get("код")
        sf = S.get(kod)
        if not sf:
            errors.append(f"{who}: нет сферы с кодом «{kod}»")
            continue
        if not isinstance(fm.get("вопрос"), str) or not fm.get("вопрос"):
            errors.append(f"{who}: пустой `вопрос`")
        st = []
        for s in spisok(fm.get("ступени")):
            m = STUPEN.match(s)
            if not m:
                errors.append(f"{who}: ступень не читается «{s}» (нужно «N — текст»)")
                continue
            st.append({"level": int(m.group(1)), "text": m.group(2)})
        lv = [x["level"] for x in st]
        if len(st) != 5:
            errors.append(f"{who}: ступеней {len(st)}, нужно 5")
        if lv != sorted(set(lv)) or any(not 1 <= x <= 10 for x in lv):
            errors.append(f"{who}: уровни ступеней должны быть 1–10 по возрастанию: {lv}")
        ut = []
        items = spisok(fm.get("уточнить"))
        if not 1 <= len(items) <= 3:
            errors.append(f"{who}: уточнений {len(items)}, нужно 1–3")
        for s in items:
            m = UTOCH.match(s)
            if not m:
                errors.append(f"{who}: уточнение не читается «{s}»")
                continue
            k, z, q = m.groups()
            r = sf["rays"].get(k)
            if not r:
                errors.append(f"{who}: в сфере нет луча с кодом «{k}»")
                continue
            if z and z not in r["zones"]:
                errors.append(f"{who}: у луча «{r['name']}» нет зоны «{z}» (есть: {', '.join(r['zones']) or 'зон нет'})")
            if not z and r["zones"]:
                errors.append(f"{who}: у луча «{r['name']}» есть зоны — укажите зону («{k} / Зона — вопрос»)")
            ut.append({"kod": k, "luch": r["file"], "zona": z, "vopros": q})
        data.append({"kod": kod, "sfera": sf["folder"], "vopros": fm.get("вопрос"), "stupeni": st, "utochnit": ut})
        print(f"■ {who}: ступени {lv}; уточнения: " + "; ".join(f"{u['luch']}{' / ' + u['zona'] if u['zona'] else ''}" for u in ut))
    for e in errors:
        print("✖", e)
    if a.json and not errors:
        payload = {"oblasti": {"плохо": [1, 4], "средне": [4, 7], "хорошо": [7, 10]}, "sfery": data}
        pathlib.Path(a.json).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print("набор данных:", a.json)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
