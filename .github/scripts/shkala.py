#!/usr/bin/env python3
"""Шкала сфер: проверка формы, подсчёт оценок, сборка интерактивной карточки.
Правила — CLAUDE.md, пп. 5.1, 5.3 («Шкала»), 5.4.

Запуск из корня хранилища:
    python3 .github/scripts/shkala.py              — проверить форму и показать посчитанное (ничего не пишет)
    python3 .github/scripts/shkala.py --write      — записать посчитанное в шапки (оценка луча; оценка, слабый, сильный в «NN Шкала»;
                                                     оценка, слабый, сильный сфер — в «00 Старт/Колесо баланса»)
    python3 .github/scripts/shkala.py --card OUT.html [--sphere 01] [--edit 01,02]
                                                   — собрать страницу-карточку из шаблона .github/scripts/shkala_card.html;
                                                     --edit — в каких сферах на карточке можно нажимать уровни (без него — во всех)
    python3 .github/scripts/shkala.py --perenos VYBOR.json
                                                   — перенести оценки, выбранные нажатием на карточке, в шапки лучей (`оценки`, `оценено`).
                                                     VYBOR.json — список документов коллекции «vybor» карточки (ArtifactData list):
                                                     {"luch": "01 Луч — Гибкость", "stroka": "Шпагат / Продольный", "bylo": 2, "novoe": 3}
                                                     (novoe null — «нет»). Всё или ничего: если строка не найдена или в файле уже
                                                     не «bylo», ни один файл не пишется. После переноса — запустить с --write.

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

  • Коды, порядок и скрытие (CLAUDE.md, п. 5.4): сфера берётся из оглавления «NN Сфера.md» — `код`, `порядок`
    (место на колесе и на карточке), `скрыта`; луч — `код` («01.03»), `скрыт`. Скрытый луч не входит в оценку сферы,
    слабый и сильный луч и карточку (свою оценку получает). Скрытая сфера не входит в колесо и карточку; в её
    «NN Шкала» программа пишет `скрыта: true` (по нему таблица Колеса её не показывает).
    Ошибка: два луча или две сферы с одним кодом, код луча не начинается с кода сферы.

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
KOD_SFERA = re.compile(r"^\d{2}$")
KOD_LUCH = re.compile(r"^(\d{2})\.(\d{2})$")
ZONE_H = re.compile(r"^##\s+(?:[\d.]+\s+)?Зона\s+«([^»]+)»(?:\s+—\s+(.+))?")
SIGN_H = re.compile(r"^###\s+(?:[\d.]+\s+)?Признак\s+«([^»]+)»(?:\s+—\s+(.+))?")
# Строки-пояснения, которые карточка показывает под линейкой: «**Сейчас …:**», «**Шаг вверх …:**» и т. п., «Мерить …»
NOTE_L = re.compile(r"^(\*\*[^*]+\*\*|Мерить|Как мерить|Условия)")
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


def flag(v):
    """Флажок из шапки: true / да → True; false, пусто, нет свойства → False."""
    return isinstance(v, str) and v.strip().lower() in ("true", "да", "yes")


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
    lines = FM.sub("", text, count=1).splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        desc = None
        if ln.startswith("## ") or ln.startswith("# "):
            m = ZONE_H.match(ln)
            zone, sign = (m.group(1).strip(), None) if m else (None, None)
            desc = m.group(2) if m else None
        elif ln.startswith("### "):
            m = SIGN_H.match(ln)
            if zone:
                sign = m.group(1).strip() if m else None
                desc = m.group(2) if m else None
        sc = scopes.setdefault((zone, sign), {"v": [], "h": [], "text": [], "desc": None})
        if desc and zone:
            sc["desc"] = desc.strip()
        if NOTE_L.match(ln.strip()):
            sc["text"].append(ln.strip())
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


def ladder_unit(scopes, z, s=None):
    """Название строки горизонтальной таблицы, по которой взята линейка («Задержка дыхания, с»), иначе None."""
    def row(rows, name):
        n = name.casefold()
        return next((r for r, lv in rows if r.casefold().startswith(n)), None)
    if s:
        sc = scopes.get((z, s))
        if sc and not sc["v"] and len(sc["h"]) == 1:
            return sc["h"][0][0]
        if sc and sc["v"]:
            return None
        own = scopes.get((z, None))
        if own and row(own["h"], s):
            return row(own["h"], s)
    sc = scopes.get((z, None))
    if sc:
        if sc["v"]:
            return None
        if len(sc["h"]) == 1:
            return sc["h"][0][0]
    return row(scopes.get((None, None), {"h": []})["h"], z)


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
def info(item, sc, unit):
    """Для карточки: пояснение из заголовка, подпись числовой линейки и строки-пояснения (Сейчас, Шаг вверх…)."""
    if sc and sc.get("desc"):
        item["desc"] = sc["desc"]
    if unit:
        item["unit"] = unit
    if sc and sc.get("text"):
        item["text"] = sc["text"]


# ---------- луч и сфера (сборка) ----------
def load_ray(path, errors, warnings):
    text = path.read_text(encoding="utf-8")
    fm = read_fm(text)
    name = fm.get("луч") or path.stem.split("— ", 1)[-1]
    items = fm.get("оценки") or []
    if isinstance(items, str):
        items = [items]
    scopes = parse_body(text)
    ray = {"name": name, "file": path.stem, "kod": fm.get("код") or None, "hidden": flag(fm.get("скрыт")),
           "rated_on": fm.get("оценено") or None, "zones": [], "levels": {}}
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
                    info(s, scopes.get((z["name"], s["name"])), ladder_unit(scopes, z["name"], s["name"]))
                z["levels"] = zone_ladder(scopes, z["name"]) or {}
                z["score"], z["calc"] = average(z["signs"])
            else:
                z["levels"] = zone_ladder(scopes, z["name"]) or {}
            info(z, scopes.get((z["name"], None)), None if z["signs"] else ladder_unit(scopes, z["name"]))
            z.pop("own_set", None)
        ray["score"], ray["calc"] = average(ray["zones"])
    else:
        ray["score"] = ray.pop("own", None)
        ray["levels"] = (scopes.get((None, None), {"v": []})["v"] or [{}])[0]
    ray.pop("own", None)
    info(ray, scopes.get((None, None)), None)
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


def sphere_meta(folder, errors, warnings):
    """Код, порядок и скрытие сферы — из шапки её оглавления «NN Сфера.md»."""
    index = folder / f"{folder.name}.md"
    fm = read_fm(index.read_text(encoding="utf-8")) if index.exists() else {}
    kod = fm.get("код") or None
    if not kod:
        warnings.append(f"{folder.name}: в оглавлении нет `код` — взят номер папки")
        kod = folder.name[:2]
    elif not KOD_SFERA.match(kod):
        errors.append(f"{folder.name}: `код` «{kod}» — нужно две цифры («01»)")
    elif kod != folder.name[:2]:
        warnings.append(f"{folder.name}: `код` «{kod}» не совпадает с номером папки")
    try:
        order = int(fm.get("порядок"))
    except (TypeError, ValueError):
        order = None
        if fm:
            warnings.append(f"{folder.name}: в оглавлении нет числа `порядок` — сфера идёт после остальных")
    return {"kod": kod, "order": order, "hidden": flag(fm.get("скрыта"))}


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
    meta = sphere_meta(folder, errors, warnings)
    for r in rays:
        m = KOD_LUCH.match(r["kod"] or "")
        if not r["kod"]:
            warnings.append(f"{r['file']}: нет `код`")
        elif not m:
            errors.append(f"{r['file']}: `код` «{r['kod']}» — нужно «{meta['kod']}.NN»")
        elif m.group(1) != meta["kod"]:
            errors.append(f"{r['file']}: `код` «{r['kod']}» не начинается с кода сферы «{meta['kod']}»")
    shown = [r for r in rays if not r["hidden"]]
    score, calc = average(shown)
    rated = [r for r in shown if r["score"] is not None]
    lo = hi = []
    if len(rated) >= 2 and min(r["score"] for r in rated) != max(r["score"] for r in rated):
        lo = [r for r in rated if r["score"] == min(x["score"] for x in rated)]
        hi = [r for r in rated if r["score"] == max(x["score"] for x in rated)]
    exact = round(sum(r["score"] for r in rated) / len(rated), 2) if rated else None
    return {"nn": nn, "sphere": folder.name[3:], "scale": scale, "paths": paths, "score": score, "calc": calc,
            "exact": exact, "weak": lo, "strong": hi, "rays": rays, "shown": shown, **meta}


def wheel_write(spheres):
    """Колесо баланса (00 Старт): оценка — среднее оценок сфер (то же округление), слабая и сильная сфера."""
    rated = [s for s in spheres if s["score"] is not None and not s["hidden"]]
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


def perenos(src):
    """Оценки, выбранные на карточке, — в шапки лучей. Всё или ничего."""
    items = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("docs") or items.get("documents") or list(items.values())
    items = [x.get("data", x) if isinstance(x, dict) else x for x in items]
    files, texts, problems, done = {}, {}, [], []
    for p in SPHERES.glob("*/Шкала/*.md"):
        files[p.stem] = p
    today = datetime.date.today().isoformat()
    for it in items:
        luch, stroka, bylo, novoe = it.get("luch"), it.get("stroka"), it.get("bylo"), it.get("novoe")
        p = files.get(luch)
        if not p:
            problems.append(f"луч «{luch}» не найден")
            continue
        if novoe is not None and not (isinstance(novoe, int) and 1 <= novoe <= 10):
            problems.append(f"{luch}: «{stroka}» — оценка вне 1–10: {novoe}")
            continue
        text = texts.get(p) or p.read_text(encoding="utf-8")
        m = FM.match(text)
        old = f'  - "{stroka}: {"нет" if bylo is None else bylo}"'
        lines = m.group(1).split("\n")
        hits = [i for i, ln in enumerate(lines) if ln.rstrip() == old]
        if len(hits) != 1:
            now = [ln.strip() for ln in lines if ln.strip().startswith(f'- "{stroka}:')]
            problems.append(f"{luch}: строка «{stroka}: {bylo}» не найдена (в файле сейчас: {', '.join(now) or 'нет такой строки'})")
            continue
        lines[hits[0]] = f'  - "{stroka}: {"нет" if novoe is None else novoe}"'
        if any(ln.startswith("оценено:") for ln in lines):
            lines = [f"оценено: {today}" if ln.startswith("оценено:") else ln for ln in lines]
        else:
            lines.insert(next(i for i, ln in enumerate(lines) if ln.startswith("оценки:")), f"оценено: {today}")
        texts[p] = "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]
        done.append(f"{luch}: {stroka}: {'нет' if bylo is None else bylo} → {'нет' if novoe is None else novoe}")
    if problems:
        for x in problems:
            print("✖", x)
        print("✖ ничего не записано")
        return 1
    for p, t in texts.items():
        p.write_text(t, encoding="utf-8")
    for x in done:
        print("✔", x)
    print(f"перенесено: {len(done)}, файлов: {len(texts)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--card")
    ap.add_argument("--sphere")
    ap.add_argument("--edit")
    ap.add_argument("--perenos")
    a = ap.parse_args()
    if a.perenos:
        sys.exit(perenos(a.perenos))
    errors, warnings, spheres = [], [], []
    for folder in sorted(p for p in SPHERES.iterdir() if p.is_dir()):
        s = load_sphere(folder, errors, warnings)
        if s:
            spheres.append(s)
    seen = {}
    for s in spheres:  # коды уникальны во всём хранилище
        for kod, who in [(s["kod"], s["nn"] + " " + s["sphere"])] + [(r["kod"], r["file"]) for r in s["rays"] if r["kod"]]:
            if kod in seen:
                errors.append(f"код «{kod}» повторяется: {seen[kod]} и {who}")
            seen[kod] = who
    spheres.sort(key=lambda s: (s["order"] is None, s["order"] or 0, s["kod"]))
    if a.sphere:
        spheres = [s for s in spheres if s["kod"] == a.sphere or s["nn"] == a.sphere]
    for s in spheres:
        mark = "  (скрыта — не в колесе и не на карточке)" if s["hidden"] else ""
        print(f"■ {s['nn']} {s['sphere']}: сфера {s['score']} {('· ' + s['calc']) if s['calc'] else ''}{mark}")
        for r in s["rays"]:
            print(f"   {r['name']}: {r['score']}  {r.get('calc') or ''}{'  (скрыт — не в оценке сферы)' if r['hidden'] else ''}")
        if a.write:
            changed = []
            for p, r in zip(s["paths"], s["rays"]):
                if write_fm(p, {"оценка": r["score"]}, after="луч"):
                    changed.append(p.stem)
            vals = {"оценка": s["score"],
                    "слабый": [f"[[{r['file']}]]" for r in s["weak"]],
                    "сильный": [f"[[{r['file']}]]" for r in s["strong"]],
                    "скрыта": "true" if s["hidden"] else None}
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
                 "rated": sum(1 for r in s["shown"] if r["score"] is not None), "rays": s["shown"]}
                for s in spheres if not s["hidden"]]
        payload = {"built": datetime.date.today().isoformat(), "spheres": data,
                   "edit": [x.strip() for x in a.edit.split(",")] if a.edit else None}
        page = TEMPLATE.read_text(encoding="utf-8").replace(
            "__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
        pathlib.Path(a.card).write_text(page, encoding="utf-8")
        print("карточка:", a.card)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
