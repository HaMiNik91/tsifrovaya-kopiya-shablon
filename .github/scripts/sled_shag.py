#!/usr/bin/env python3
"""«Следующий шаг сам» (апгрейд 3.4, 03.11.2026; CLAUDE.md, п. 5.5).

Связывает три вещи, которые уже есть: где я (оценки лучей и зон), что дальше (строка
«**Шаг вверх (N → N+1):**» под линейкой) и чем помочь себе (помощники из «60 Помощники»,
подобранные под уровень правилом podhodit(): N ≤ уровень < M).

Что делает:
  python3 .github/scripts/sled_shag.py           — показать, ничего не пишет
  python3 .github/scripts/sled_shag.py --write   — собрать страницу «00 Старт/Следующий шаг»
      (между строками-метками): у сфер-приоритетов (`приоритет` в «NN Шкала») — самый слабый луч,
      его самая слабая зона, шаг вверх, подходящие помощники с первой практикой и шаги, уже взятые
      в «Путь»; ниже — таблица остальных сфер.
  python3 .github/scripts/sled_shag.py --probely — пробелы: лучи без помощника под нынешний
      уровень и без строки «Шаг вверх» (что дописать в библиотеку помощников)
  python3 .github/scripts/sled_shag.py --vzyat "Помощник — Название"
      — «Взять в Путь»: создать шаг `NN Шаг — Название.md` в папке «Путь» сферы помощника
      (луч, уровень, ссылка на помощника, первая практика; `статус: в работе`). Если шаг с этим
      помощником уже есть — ничего не создаёт и называет его. Задачу в Todoist ставит Claude.
Ошибки — ✖, предупреждения — ⚠.
"""
import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from shkala import read_fm, flag, rnd, ZONE_H  # noqa: E402
from pomoshniki import podhodit, uroven  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SFERY = ROOT / "10 Сферы"
POMOSH = ROOT / "60 Помощники"
PAGE = ROOT / "00 Старт" / "Следующий шаг.md"
START, END = "<!-- sled_shag: начало -->", "<!-- sled_shag: конец -->"
STEP = re.compile(r"^\*\*Шаг вверх \((\d+) → (\d+)\):\*\*\s*(.+)")
NUM = re.compile(r":\s*(\d+)\s*$")


def section(text, title):
    """Текст раздела «## title» до следующего «## »."""
    m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def first_practice(text):
    s = section(text, "Что делать")
    for line in s.splitlines():
        line = line.strip().lstrip("-• ").strip()
        if line:
            return line
    return ""


def load_helpers():
    res = []
    for p in sorted(POMOSH.glob("Помощник — *.md")):
        t = p.read_text(encoding="utf-8")
        fm = read_fm(t)
        if fm.get("тип") != "помощник" or flag(fm.get("скрыт")):
            continue
        res.append({"name": p.stem, "luch": fm.get("луч", ""), "urovni": fm.get("уровни", ""),
                    "pomosh": fm.get("помощь", ""), "nauch": fm.get("научность", ""),
                    "practice": first_practice(t)})
    return res


def load_luch(p):
    t = p.read_text(encoding="utf-8")
    fm = read_fm(t)
    name = fm.get("луч") or p.stem.split("—", 1)[-1].strip()
    # оценки нижнего уровня → зоны
    zones, order = {}, []
    for line in fm.get("оценки") or []:
        head = line.rsplit(":", 1)[0].strip()
        zone = head.split(" / ", 1)[0].strip()
        m = NUM.search(line)
        if zone not in zones:
            zones[zone] = []
            order.append(zone)
        if m:
            zones[zone].append(int(m.group(1)))
    zscore = {z: (rnd(sum(v) / len(v)) if v else None) for z, v in zones.items()}
    # шаги вверх по зонам (вне зоны — шаг луча)
    steps, cur = {}, None
    for line in t[t.find("\n---", 3) + 4:].splitlines():
        zm = ZONE_H.match(line)
        if zm:
            cur = zm.group(1)
            continue
        if line.startswith("## "):
            cur = None
            continue
        sm = STEP.match(line)
        if sm:
            key = cur or name
            steps.setdefault(key, (int(sm.group(1)), int(sm.group(2)), sm.group(3).strip()))
    try:
        score = int(fm.get("оценка"))
    except (TypeError, ValueError):
        score = None
    has_zones = not (len(order) == 1 and order[0] == name)
    return {"file": p.stem, "name": name, "kod": fm.get("код", ""), "score": score,
            "hidden": flag(fm.get("скрыт")), "zones": order if has_zones else [],
            "zscore": zscore, "zvals": zones, "steps": steps}


def load_spheres():
    res = []
    for d in sorted(SFERY.iterdir()):
        if not d.is_dir():
            continue
        idx = d / f"{d.name}.md"
        if not idx.exists():
            continue
        ifm = read_fm(idx.read_text(encoding="utf-8"))
        if flag(ifm.get("скрыта")):
            continue
        kod = ifm.get("код", "")
        shk = d / f"{kod} Шкала.md"
        sfm = read_fm(shk.read_text(encoding="utf-8")) if shk.exists() else {}
        try:
            prio = int(sfm.get("приоритет"))
        except (TypeError, ValueError):
            prio = None
        luchi = [load_luch(p) for p in sorted((d / "Шкала").glob(f"{kod} Луч — *.md"))]
        path = []
        for p in sorted((d / "Путь").glob("*.md")):
            pfm = read_fm(p.read_text(encoding="utf-8"))
            if pfm.get("тип") == "шаг" and pfm.get("статус") != "готово":
                path.append({"file": p.stem, "luch": pfm.get("луч", ""), "status": pfm.get("статус") or "не начат",
                             "text": p.read_text(encoding="utf-8")})
        res.append({"dir": d, "name": d.name, "kod": kod, "prio": prio, "luchi": luchi, "path": path,
                    "title": (idx.read_text(encoding="utf-8").split("\n# ", 1)[-1].splitlines() or [d.name])[0]})
    return res


def targets(luch, helpers):
    """Элементы луча (зоны или сам луч) от слабого к сильному: уровень, шаг, помощники."""
    out = []
    elems = luch["zones"] or [luch["name"]]
    for z in elems:
        lvl = luch["zscore"].get(z) if luch["zones"] else luch["score"]
        if lvl is None:
            continue
        keys = {f'{luch["kod"]} / {z}'} if luch["zones"] else set()
        keys.add(luch["kod"])
        # помощник всего луча подбирается по оценке луча, помощник зоны — по оценке зоны
        hs = [h for h in helpers if h["luch"] in keys
              and podhodit(h["urovni"], luch["score"] if h["luch"] == luch["kod"] else lvl)]
        out.append({"zone": z if luch["zones"] else None, "lvl": lvl,
                    "step": luch["steps"].get(z) or luch["steps"].get(luch["name"]), "helpers": hs})
    out.sort(key=lambda e: e["lvl"])
    return out


def build(spheres, helpers):
    today = datetime.date.today().isoformat()
    L = [START, f"*Собрано программой `sled_shag.py` {today} — руками не править. Взять шаг в «Путь» — сказать Claude «беру помощника …».*", ""]
    prio = sorted([s for s in spheres if s["prio"]], key=lambda s: s["prio"])
    if not prio:
        L += ["Сферы-приоритеты не выбраны — их ставят в [[Время и внимание]] (важность, место, часы).", ""]
    for s in prio:
        vis = [l for l in s["luchi"] if not l["hidden"] and l["score"] is not None]
        if not vis:
            continue
        low = min(l["score"] for l in vis)
        for luch in [l for l in vis if l["score"] == low]:
            L.append(f"## {s['prio']}. {s['title']} — луч «{luch['name']}» ({luch['score']} из 10)")
            L.append("")
            L.append(f"Луч: [[{luch['file']}]]")
            L.append("")
            tg = targets(luch, helpers)
            shown = 0
            for e in tg:
                if shown >= 2 or (shown and not e["helpers"]):
                    break
                where = f"зона «{e['zone']}» — {e['lvl']}" if e["zone"] else f"уровень {e['lvl']}"
                L.append(f"**{where.capitalize()}.**")
                if e["step"]:
                    L.append(f"- Шаг вверх ({e['step'][0]} → {e['step'][1]}): {e['step'][2]}")
                if e["helpers"]:
                    for h in e["helpers"]:
                        L.append(f"- [[{h['name']}]] — {h['pomosh']}, {h['urovni']}, {h['nauch']}. {h['practice']}")
                else:
                    L.append("- Помощника под этот уровень пока нет.")
                L.append("")
                shown += 1
            if not any(e["helpers"] for e in tg):
                alt = []
                for other in sorted(vis, key=lambda l: l["score"]):
                    if other is luch:
                        continue
                    for e in targets(other, helpers):
                        if e["helpers"]:
                            alt.append((other, e))
                            break
                    if alt:
                        break
                if alt:
                    other, e = alt[0]
                    where = f", зона «{e['zone']}»" if e["zone"] else ""
                    L.append(f"**Ближайший луч с помощником:** [[{other['file']}]]{where} — {e['lvl']} из 10")
                    for h in e["helpers"]:
                        L.append(f"- [[{h['name']}]] — {h['pomosh']}, {h['urovni']}, {h['nauch']}. {h['practice']}")
                    L.append("")
            mine = [p for p in s["path"] if p["luch"] == luch["name"]]
            if mine:
                L.append("**Уже в «Путь»:** " + "; ".join(f"[[{p['file']}]] ({p['status']})" for p in mine))
                L.append("")
    rest = []
    for s in sorted((s for s in spheres if not s["prio"]), key=lambda s: s["kod"]):
        vis = [l for l in s["luchi"] if not l["hidden"] and l["score"] is not None]
        if vis:
            luch = min(vis, key=lambda l: l["score"])
            n = sum(len(e["helpers"]) for e in targets(luch, helpers))
            rest.append(f"| {s['kod']} | [[{luch['file']}\\|{luch['name']}]] | {luch['score']} | {n} |")
    if rest:
        L += ["## Остальные сферы", "", "| Сфера | Самый слабый луч | Уровень | Помощников |", "|---|---|---|---|", *rest, ""]
    elif not any(s["prio"] for s in spheres):
        L += ["Оценок ещё нет — начните с оценки сфер (опросник или Шкала), тогда здесь появится самый слабый луч каждой сферы.", ""]
    L.append(END)
    return "\n".join(L)


PAGE_HEAD = """---
тип: следующий шаг
статус: в работе
обновлено: {d}
---
# Следующий шаг

← [[Начни здесь]] · [[Время и внимание]] · [[Колесо баланса]] · [[60 Помощники]]

*Что делать дальше: у сфер-приоритетов — самый слабый луч, его шаг вверх и помощники ровно под ваш уровень (новичку не показываются советы для верхних уровней). Страницу пересобирает программа после каждого изменения оценок и помощников.*

"""


def vzyat(name, spheres, helpers):
    h = next((x for x in helpers if x["name"] == name), None)
    if not h:
        print(f"✖ помощника «{name}» нет (или он скрыт)")
        return 1
    kod = h["luch"].split(" / ")[0]
    zone = h["luch"].split(" / ", 1)[1] if " / " in h["luch"] else None
    s = next((x for x in spheres if x["kod"] == kod.split(".")[0]), None)
    luch = s and next((l for l in s["luchi"] if l["kod"] == kod), None)
    if not luch:
        print(f"✖ луча {kod} нет")
        return 1
    for p in s["path"]:
        if f"[[{name}]]" in p["text"]:
            print(f"⚠ уже взят: {p['file']} ({p['status']})")
            return 0
    same = [p for p in s["path"] if p["luch"] == luch["name"]]
    if same:
        print("⚠ по этому лучу уже есть шаги: " + "; ".join(f"{p['file']} ({p['status']})" for p in same))
    title = name.split("—", 1)[1].strip()
    path = s["dir"] / "Путь" / f"{s['kod']} Шаг — {title}.md"
    if path.exists():
        print(f"⚠ файл уже есть: {path.name}")
        return 0
    lvl = luch["zscore"].get(zone) if zone else luch["score"]
    step = luch["steps"].get(zone or luch["name"])
    today = datetime.date.today().isoformat()
    body = [f"# {title}", "",
            f"Помощник: [[{name}]] · Луч: [[{luch['file']}]]" + (f", зона «{zone}»" if zone else ""), ""]
    if lvl is not None:
        body.append(f"Сейчас — {lvl} из 10; помощник для отрезка {h['urovni']}.")
    if step:
        body.append(f"Шаг вверх ({step[0]} → {step[1]}): {step[2]}")
    body += ["", "## Первая практика", "", h["practice"] or "— (см. карточку помощника)", "",
             f"*Взято в «Путь» {today} через «Следующий шаг».*", ""]
    fm = ["---", "тип: шаг", f'сфера: "[[{s["name"]}]]"', f"луч: {luch['name']}", "важность:",
          "простота: 4", "статус: в работе", f"обновлено: {today}", "---"]
    path.write_text("\n".join(fm + body), encoding="utf-8")
    print(f"создан: {path.relative_to(ROOT)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--vzyat")
    ap.add_argument("--probely", action="store_true", help="лучи без помощника под нынешний уровень, без «Шага вверх» или с «Шагом вверх» не с того уровня")
    a = ap.parse_args()
    helpers = load_helpers()
    spheres = load_spheres()
    for h in helpers:
        if not uroven(h["urovni"]):
            print(f"⚠ {h['name']}: `уровни` не по форме «N → M»")
    if a.vzyat:
        return vzyat(a.vzyat, spheres, helpers)
    if a.probely:
        # строка «Шаг вверх» без закрывающих ** программа не видит — назвать её
        for f in sorted(SFERY.glob("*/Шкала/*.md")):
            for i, x in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if x.startswith("**Шаг вверх") and not STEP.match(x):
                    print(f"⚠ {f.stem}, строка {i}: «Шаг вверх» не по форме (программа её не видит) «**Шаг вверх (N → M):** …»")
        for s in spheres:
            for l in s["luchi"]:
                if l["hidden"] or l["score"] is None:
                    continue
                tg = targets(l, helpers)
                gaps = []
                if not any(e["helpers"] for e in tg):
                    gaps.append("нет помощника: " + ", ".join(
                        (f"{e['zone']} {e['lvl']}" if e["zone"] else str(e["lvl"])) for e in tg))
                if not l["steps"]:
                    gaps.append("нет «Шага вверх»")
                for e in tg:
                    # у зоны с признаками «Шаг вверх» может стоять под признаком — сверяем и с ним
                    svoi = {e["lvl"]} | set(l["zvals"].get(e["zone"] or "", []))
                    if e["step"] and int(e["step"][0]) not in svoi:
                        gaps.append(f"«Шаг вверх» не с нынешнего уровня: {e['zone'] or 'луч'} "
                                    f"(сейчас {e['lvl']}, шаг {e['step'][0]} → {e['step'][1]})")
                if gaps:
                    print(f"{l['kod']} {l['name']}{' (приоритет)' if s['prio'] else ''}: " + "; ".join(gaps))
        return 0
    text = build(spheres, helpers)
    if a.write:
        if PAGE.exists():
            old = PAGE.read_text(encoding="utf-8")
            new = old[:old.index(START)] + text + old[old.index(END) + len(END):] if START in old else old + "\n" + text
            def bez_daty(s):
                return [x for x in s.splitlines() if "Собрано программой" not in x and not x.startswith("обновлено:")]
            if bez_daty(new) != bez_daty(old):
                new = re.sub(r"^обновлено: .*$", f"обновлено: {datetime.date.today().isoformat()}", new, count=1, flags=re.M)
                PAGE.write_text(new, encoding="utf-8")
                print(f"записано: {PAGE.relative_to(ROOT)}")
        else:
            PAGE.write_text(PAGE_HEAD.format(d=datetime.date.today().isoformat()) + text + "\n", encoding="utf-8")
            print(f"создано: {PAGE.relative_to(ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
