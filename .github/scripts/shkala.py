#!/usr/bin/env python3
"""Шкала сфер: проверка формы, подсчёт оценок, сборка интерактивной карточки.
Правила — CLAUDE.md, пп. 5.1, 5.3 («Шкала»), 5.4.

Запуск из корня хранилища:
    python3 .github/scripts/shkala.py              — проверить форму и показать посчитанное (ничего не пишет)
    python3 .github/scripts/shkala.py --write      — записать посчитанное в шапки (оценка луча; оценка, слабый, сильный в «NN Шкала»;
                                                     оценка, слабый, сильный сфер — в «00 Старт/Колесо баланса»)
    python3 .github/scripts/shkala.py --card OUT.html [--sphere 01]
                                                   — собрать страницу-карточку из шаблона .github/scripts/shkala_card.html

Что откуда берётся:
  • Оценки ставятся только на нижнем уровне — в шапке файла луча, свойство `оценки`:
        оценки:
          - "Шпагат / Продольный: 2"     ← зона / признак
          - "Присед: 9"                  ← зона без признаков
          - "Сердце и сосуды: нет"       ← не оценено
    У луча без зон одна строка с названием самого луча: "Суставы: 7".
  • Выше считает эта программа: признаки → зона → луч → сфера. Среднее берётся из уже округлённых
    оценок уровня ниже; «нет» не учитывается; если оценок нет совсем — нет и оценки.
    Округление: дробная часть до ,5 включительно — вниз, больше ,5 — вверх (6,5 → 6; 6,51 → 7).
  • Линейки уровней — из текста луча:
        ## [номер] Зона «Название» [— пояснение]
        ### [номер] Признак «Название» [— пояснение]
    Таблица `| Уровень | … |` с уровнями 1–10 сверху вниз (вертикальная) или `| Уровень | 1 | 2 | … | 10 |`
    (горизонтальная: каждая строка — свой признак или зона). Поиск линейки идёт снизу вверх:
      признак — своя таблица в разделе «Признак», иначе строка горизонтальной таблицы зоны,
                чьё название начинается с имени признака, иначе линейка зоны;
      зона    — своя таблица в разделе «Зона» (вертикальная или горизонтальная из одной строки),
                иначе строка горизонтальной таблицы луча вне зон, чьё название начинается с имени зоны;
      луч без зон — вертикальная таблица луча вне зон.
    Любой другой заголовок `## …` закрывает раздел зоны.

Код выхода 1 — ошибка формы (оценку нельзя прочитать). Предупреждения (нет линейки, не 10 уровней) код не меняют.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
from decimal import Decimal, ROUND_HALF_DOWN

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPHERES = ROOT / "10 Сферы"
TEMPLATE = pathlib.Path(__file__).with_name("shkala_card.html")
WHEEL = ROOT / "00 Старт" / "Колесо баланса.md"
FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
ZONE_H = re.compile(r"^##\s+(?:[\d.]+\s+)?Зона\s+«([^»]+)»")
SIGN_H = re.compile(r"^###\s+(?:[\d.]+\s+)?Признак\s+«([^»]+)»")
COMPUTED = ("оценка", "слабый", "сильный")


# ---------- шапка ----------
def read_fm(text):
    """Простой разбор шапки: «ключ: значение» и списки «  - элемент»."""
    m = FM.match(text)
    out, key = {}, None
    if not m:
        return out
    for line in m.group(1).splitlines():
        if re.match(r"^\s+-\s", line) and key:
            out.setdefault(key, [])
            if not isinstance(out[key], list):
                out[key] = []
            out[key].append(line.split("-", 1)[1].strip().strip('"'))
        elif ":" in line and not line.startswith(" "):
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            out[key] = val.strip('"') if val else []
    return out


def write_fm(path, values, after):
    """Записать посчитанные свойства в шапку: заменить старые или вставить после строки `after`."""
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    lines = m.group(1).splitlines()
    keep, i = [], 0
    while i < len(lines):  # убрать прежние посчитанные свойства вместе с их списками
        k = lines[i].split(":", 1)[0].strip()
        if not lines[i].startswith(" ") and k in values:
            i += 1
            while i < len(lines) and re.match(r"^\s+-\s", lines[i]):
                i += 1
            continue
        keep.append(lines[i])
        i += 1
    new = []
    for k, v in values.items():
        if v is None or v == []:
            continue
        if isinstance(v, list):
            new.append(f"{k}:")
            new += [f'  - "{x}"' for x in v]
        else:
            new.append(f"{k}: {v}")
    pos = next((j + 1 for j, ln in enumerate(keep) if ln.split(":", 1)[0].strip() == after), len(keep))
    result = keep[:pos] + new + keep[pos:]
    out = "---\n" + "\n".join(result) + "\n---\n" + text[m.end():]
    if out != text:
        path.write_text(out, encoding="utf-8")
        return True
    return False


# ---------- счёт ----------
def rnd(x):
    return int(Decimal(str(round(x, 6))).quantize(Decimal("1"), rounding=ROUND_HALF_DOWN))


def num(x):
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def average(kids):
    """Среднее округлённых оценок уровня ниже; «нет» пропускается. Возвращает (оценка, строка расчёта)."""
    vals = [k["score"] for k in kids if k["score"] is not None]
    if not vals:
        return None, None
    avg = sum(vals) / len(vals)
    calc = f"({' + '.join(map(str, vals))}) / {len(vals)} = {num(avg)} → {rnd(avg)}"
    if len(vals) < len(kids):
        calc += f"; без оценки, не учтено: {len(kids) - len(vals)}"
    return rnd(avg), calc


# ---------- текст луча: линейки уровней ----------
def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_body(text):
    """Таблицы уровней по разделам: (зона, признак) → {'v': [вертикальные], 'h': [(строка, уровни)]}."""
    scopes = {}
    zone = sign = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("## ") or ln.startswith("# "):
            m = ZONE_H.match(ln)
            zone, sign = (m.group(1).strip(), None) if m else (None, None)
        elif ln.startswith("### "):
            m = SIGN_H.match(ln)
            if zone:
                sign = m.group(1).strip() if m else None
        sc = scopes.setdefault((zone, sign), {"v": [], "h": []})
        if re.match(r"^\|\s*Уровень\s*\|\s*1\s*\|", ln):
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                c = cells(lines[j])
                sc["h"].append((c[0], {k + 1: v for k, v in enumerate(c[1:11]) if v}))
                j += 1
            i = j
            continue
        if re.match(r"^\|\s*Уровень\s*\|", ln):
            lv, j = {}, i + 2
            while j < len(lines) and lines[j].startswith("|"):
                c = cells(lines[j])
                if c[0].isdigit() and 1 <= int(c[0]) <= 10:
                    lv[int(c[0])] = c[1] if len(c) > 1 else ""
                j += 1
            sc["v"].append(lv)
            i = j
            continue
        i += 1
    return scopes


def starts(rows, name):
    n = name.casefold()
    return next((lv for r, lv in rows if r.casefold().startswith(n)), None)


def zone_ladder(scopes, z):
    sc = scopes.get((z, None))
    if sc:
        if sc["v"]:
            return sc["v"][0]
        if len(sc["h"]) == 1:
            return sc["h"][0][1]
    return starts(scopes.get((None, None), {"h": []})["h"], z)


def sign_ladder(scopes, z, s):
    sc = scopes.get((z, s))
    if sc:
        if sc["v"]:
            return sc["v"][0]
        if len(sc["h"]) == 1:
            return sc["h"][0][1]
    own = scopes.get((z, None))
    if own:
        hit = starts(own["h"], s)
        if hit:
            return hit
    return zone_ladder(scopes, z)


# ---------- луч и сфера ----------
def load_ray(path, errors, warnings):
    text = path.read_text(encoding="utf-8")
    fm = read_fm(text)
    name = fm.get("луч") or path.stem.split("— ", 1)[-1]
    items = fm.get("оценки") or []
    if isinstance(items, str):
        items = [items]
    scopes = parse_body(text)
    ray = {"name": name, "file": path.stem, "rated_on": fm.get("оценено") or None, "zones": [], "levels": {}}
    zones = {}
    for it in items:
        m = re.match(r"^(.+?):\s*(нет|\d+)\s*$", it)
        if not m:
            errors.append(f"{path.stem}: не читается строка оценки «{it}»")
            continue
        parts = [p.strip() for p in m.group(1).split(" / ")]
        val = None if m.group(2) == "нет" else int(m.group(2))
        if val is not None and not 1 <= val <= 10:
            errors.append(f"{path.stem}: оценка вне 1–10 в «{it}»")
            continue
        if len(parts) == 1 and parts[0] == name:  # луч без зон
            ray["own"] = val
            continue
        if len(parts) > 2:
            errors.append(f"{path.stem}: больше двух уровней в «{it}» (нужно «Зона / Признак: N»)")
            continue
        z = zones.get(parts[0])
        if not z:
            z = zones[parts[0]] = {"name": parts[0], "score": None, "signs": [], "levels": {}}
            ray["zones"].append(z)
        if len(parts) == 1:
            if z.get("own_set"):
                errors.append(f"{path.stem}: зона «{parts[0]}» оценена дважды")
            z["score"], z["own_set"] = val, True
        else:
            z["signs"].append({"name": parts[1], "score": val, "levels": {}})
    if "own" in ray and ray["zones"]:
        errors.append(f"{path.stem}: у луча есть и своя оценка, и зоны")
    # линейки и счёт
    if ray["zones"]:
        for z in ray["zones"]:
            if z["signs"]:
                if z.get("own_set"):
                    errors.append(f"{path.stem}: у зоны «{z['name']}» есть и своя оценка, и признаки")
                for s in z["signs"]:
                    s["levels"] = sign_ladder(scopes, z["name"], s["name"]) or {}
                z["levels"] = zone_ladder(scopes, z["name"]) or {}
                z["score"], z["calc"] = average(z["signs"])
            else:
                z["levels"] = zone_ladder(scopes, z["name"]) or {}
            z.pop("own_set", None)
        ray["score"], ray["calc"] = average(ray["zones"])
    else:
        ray["score"] = ray.pop("own", None)
        ray["levels"] = (scopes.get((None, None), {"v": []})["v"] or [{}])[0]
    ray.pop("own", None)
    if not items:
        warnings.append(f"{path.stem}: в шапке нет свойства `оценки`")
    # предупреждения о линейках
    def chk(label, lv):
        if not lv:
            warnings.append(f"{path.stem}: {label} — линейка уровней не найдена")
        elif len(lv) != 10:
            warnings.append(f"{path.stem}: {label} — в линейке {len(lv)} уровней, не 10")
    if ray["zones"]:
        for z in ray["zones"]:
            if z["signs"]:
                for s in z["signs"]:
                    chk(f"«{z['name']} / {s['name']}»", s["levels"])
            else:
                chk(f"зона «{z['name']}»", z["levels"])
    else:
        chk("луч", ray["levels"])
    # сколько оценено на нижнем уровне (для карточки)
    leaves = [s for z in ray["zones"] for s in (z["signs"] or [z])] or [ray]
    ray["leaves_total"] = len(leaves)
    ray["leaves_rated"] = sum(1 for x in leaves if x["score"] is not None)
    if ray["zones"]:
        ray["zones_rated"] = sum(1 for z in ray["zones"] if z["score"] is not None)
    for z in ray["zones"]:
        z["levels"] = {str(k): v for k, v in z["levels"].items()}
        for s in z["signs"]:
            s["levels"] = {str(k): v for k, v in s["levels"].items()}
    ray["levels"] = {str(k): v for k, v in ray["levels"].items()}
    return ray


def load_sphere(folder, errors, warnings):
    nn = folder.name[:2]
    scale = folder / f"{nn} Шкала.md"
    ray_dir = folder / "Шкала"
    paths = [p for p in sorted(ray_dir.glob("*.md")) if read_fm(p.read_text(encoding="utf-8")).get("тип") == "луч"]
    if not paths or not scale.exists():
        return None
    order = re.findall(r"\[\[([^\]|#]+)", scale.read_text(encoding="utf-8"))
    paths.sort(key=lambda p: order.index(p.stem) if p.stem in order else 999)
    rays = [load_ray(p, errors, warnings) for p in paths]
    score, calc = average(rays)
    rated = [r for r in rays if r["score"] is not None]
    lo = hi = []
    if len(rated) >= 2 and min(r["score"] for r in rated) != max(r["score"] for r in rated):
        lo = [r for r in rated if r["score"] == min(x["score"] for x in rated)]
        hi = [r for r in rated if r["score"] == max(x["score"] for x in rated)]
    exact = round(sum(r["score"] for r in rated) / len(rated), 2) if rated else None
    return {"nn": nn, "sphere": folder.name[3:], "scale": scale, "paths": paths, "score": score, "calc": calc,
            "exact": exact, "weak": lo, "strong": hi, "rays": rays}


def wheel_write(spheres):
    """Колесо баланса (00 Старт): оценка — среднее оценок сфер (то же округление), слабая и сильная сфера."""
    rated = [s for s in spheres if s["score"] is not None]
    score, calc = average(rated)
    lo = hi = []
    if len(rated) >= 2 and min(s["score"] for s in rated) != max(s["score"] for s in rated):
        lo = [s for s in rated if s["score"] == min(x["score"] for x in rated)]
        hi = [s for s in rated if s["score"] == max(x["score"] for x in rated)]
    link = lambda s: f"[[{s['nn']} {s['sphere']}]]"
    vals = {"оценка": score, "слабый": [link(s) for s in lo], "сильный": [link(s) for s in hi]}
    print(f"■ Колесо баланса: {score} {('· ' + calc) if calc else ''}")
    if WHEEL.exists():
        print("   записано:", "Колесо баланса" if write_fm(WHEEL, vals, after="тип") else "ничего не изменилось")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--card")
    ap.add_argument("--sphere")
    a = ap.parse_args()
    errors, warnings, spheres = [], [], []
    for folder in sorted(p for p in SPHERES.iterdir() if p.is_dir()):
        if a.sphere and not folder.name.startswith(a.sphere):
            continue
        s = load_sphere(folder, errors, warnings)
        if s:
            spheres.append(s)
    for s in spheres:
        print(f"■ {s['nn']} {s['sphere']}: сфера {s['score']} {('· ' + s['calc']) if s['calc'] else ''}")
        for r in s["rays"]:
            print(f"   {r['name']}: {r['score']}  {r.get('calc') or ''}")
        if a.write:
            changed = []
            for p, r in zip(s["paths"], s["rays"]):
                if write_fm(p, {"оценка": r["score"]}, after="луч"):
                    changed.append(p.stem)
            vals = {"оценка": s["score"],
                    "слабый": [f"[[{r['file']}]]" for r in s["weak"]],
                    "сильный": [f"[[{r['file']}]]" for r in s["strong"]]}
            if write_fm(s["scale"], vals, after="сфера"):
                changed.append(s["scale"].stem)
            print("   записано:", ", ".join(changed) if changed else "ничего не изменилось")
    if a.write and not a.sphere:
        wheel_write(spheres)
    for w in warnings:
        print("⚠", w)
    for e in errors:
        print("✖", e)
    if a.card:
        if errors:
            print("✖ карточка не собрана: сначала исправить ошибки формы")
            sys.exit(1)
        data = [{"nn": s["nn"], "sphere": s["sphere"], "score": s["score"], "calc": s["calc"], "exact": s["exact"],
                 "rated": sum(1 for r in s["rays"] if r["score"] is not None), "rays": s["rays"]} for s in spheres]
        payload = {"built": datetime.date.today().isoformat(), "spheres": data}
        page = TEMPLATE.read_text(encoding="utf-8").replace(
            "__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
        pathlib.Path(a.card).write_text(page, encoding="utf-8")
        print("карточка:", a.card)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
