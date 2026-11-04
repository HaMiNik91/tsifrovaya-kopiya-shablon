#!/usr/bin/env python3
"""Цикл — модуль «Цикл» (апгрейд 4.3, 04.11.2026; CLAUDE.md, п. 5.2).

Как устроено:
- Отметки — файлы на месяц `01 ГГГГ-ММ Цикл.md` в «10 Сферы/01 …/Медкарта/Цикл/» (шаблон «Шаблон — Цикл месяц»;
  `тип: цикл-месяц`), таблица `| Дата | Кровь | Боль | Заметка |`: кровь — пусто, мажет, слабо, средне, обильно;
  боль 0–3. Настроение и энергия берутся из журнала дня (`20 Журнал/ГГГГ-ММ-ДД.md`, `настроение`, `энергия`).
- Начало цикла — первый день с кровью «слабо» и сильнее после хотя бы 7 дней без такой крови («мажет» — не начало).
- Итог — в «01 Цикл» (`тип: цикл`): `средний цикл`, `разброс`, `ожидается` и раздел «Итоги» (между строками-метками):
  циклы, длина месячных, выход за нормы (⚠ «стоит показаться врачу», не диагноз), свои закономерности —
  после 2 полных циклов: боль, настроение и энергия в дни перед месячными, во время и в остальные дни.
- Нормы (взрослые, FIGO 2018 / NHS): цикл 24–38 дней; разброс (самый длинный − самый короткий) до 9 дней;
  месячные до 8 дней; 90 дней без месячных. Подростки (младше 18 по `год рождения` или набор «Подросток»):
  цикл 21–45 дней. Источники — «80 Шаблоны/Модули/Цикл/Исследование — Женский цикл».
- Модуль не включён (нет «01 Цикл») — программа молча выходит.

Запуск:
  python3 .github/scripts/tsikl.py           — проверка и отчёт, ничего не пишет
  python3 .github/scripts/tsikl.py --write   — записать свойства и «Итоги» в «01 Цикл»
  … [--data ГГГГ-ММ-ДД]                      — считать «сегодня» этой датой (для проверок)
Ошибки — ✖ (исправить), предупреждения — ⚠ (назвать владельцу).
"""
import argparse
import datetime
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from shkala import read_fm, write_fm  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SFERY = ROOT / "10 Сферы"
ZHURNAL = ROOT / "20 Журнал"
PROFIL = ROOT / "00 Старт" / "Профиль.md"
START, END = "<!-- tsikl: начало -->", "<!-- tsikl: конец -->"
KROV = {"": 0, "нет": 0, "мажет": 1, "слабо": 2, "средне": 3, "обильно": 4}
ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
PAUZA = 7  # дней без крови «слабо»+ — чтобы новая кровь считалась новым циклом


def papka():
    for d in sorted(SFERY.glob("*/Медкарта/Цикл")):
        idx = d / f"{d.parent.parent.name[:2]} Цикл.md"
        if idx.exists():
            return d, idx
    return None, None


def podrostok(today):
    if not PROFIL.exists():
        return False
    fm = read_fm(PROFIL.read_text(encoding="utf-8"))
    god = str(fm.get("год рождения", "") or "")
    if re.fullmatch(r"\d{4}", god) and today.year - int(god) < 18:
        return True
    return str(fm.get("набор", "")).strip().lower() == "подросток"


def load_marks(d, errors):
    marks = {}
    for f in sorted(d.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        fm = read_fm(text)
        if fm.get("тип") != "цикл-месяц":
            continue
        mes = fm.get("месяц", "")
        if not re.fullmatch(r"\d{4}-\d{2}", mes or ""):
            errors.append(f"{f.stem}: `месяц` нужно ГГГГ-ММ")
        for i, line in enumerate(text.splitlines(), 1):
            m = ROW.match(line)
            if not m:
                continue
            day, krov, bol, zam = (x.strip() for x in m.groups())
            where = f"{f.stem}, строка {i}"
            try:
                dt = datetime.date.fromisoformat(day)
            except ValueError:
                errors.append(f"{where}: дата «{day}»")
                continue
            if mes and not day.startswith(mes):
                errors.append(f"{where}: дата {day} не из месяца {mes}")
            if krov.lower() not in KROV:
                errors.append(f"{where}: кровь «{krov}» — пусто, мажет, слабо, средне, обильно")
                continue
            b = None
            if bol:
                if bol in ("0", "1", "2", "3"):
                    b = int(bol)
                else:
                    errors.append(f"{where}: боль «{bol}» — 0, 1, 2 или 3")
            if dt in marks:
                errors.append(f"{where}: дата {day} уже отмечена")
            marks[dt] = {"krov": KROV[krov.lower()], "bol": b, "zam": zam}
    return marks


def load_journal():
    """Дата → (настроение, энергия) из шапок журнала дня."""
    res = {}
    if not ZHURNAL.exists():
        return res
    for f in ZHURNAL.glob("????-??-??.md"):
        fm = read_fm(f.read_text(encoding="utf-8"))
        vals = []
        for k in ("настроение", "энергия"):
            v = str(fm.get(k, "") or "").strip()
            vals.append(int(v) if v.isdigit() else None)
        if any(v is not None for v in vals):
            res[datetime.date.fromisoformat(f.stem)] = tuple(vals)
    return res


def starts_and_periods(marks):
    """Начала циклов и длина месячных у каждого (дни подряд с кровью ≥ «мажет» от начала, пропуск ≤ 1 дня)."""
    starts, last = [], None
    for dt in sorted(marks):
        if marks[dt]["krov"] >= 2:
            if last is None or (dt - last).days > PAUZA:
                starts.append(dt)
            last = dt
    periods = []
    for s in starts:
        end, dt = s, s
        while True:
            nxt = [d for d in (dt + datetime.timedelta(1), dt + datetime.timedelta(2))
                   if d in marks and marks[d]["krov"] >= 1]
            if not nxt:
                break
            dt = nxt[0]
            end = dt
        periods.append((end - s).days + 1)
    return starts, periods


def fmt(d):
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def chislo(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def zakonomernosti(marks, journal, starts):
    """Средние боль, настроение, энергия: 1–5 дней до месячных, дни месячных (первые 5), остальные дни."""
    if len(starts) < 3:
        return None
    groups = {"за 5 дней до месячных": [], "первые 5 дней месячных": [], "остальные дни": []}
    first, last = starts[0], starts[-1]
    day = first
    while day < last:
        nxt = min(s for s in starts if s > day) if any(s > day for s in starts) else None
        cur = max(s for s in starts if s <= day)
        if nxt and 1 <= (nxt - day).days <= 5:
            g = "за 5 дней до месячных"
        elif (day - cur).days < 5:
            g = "первые 5 дней месячных"
        else:
            g = "остальные дни"
        m = marks.get(day, {})
        j = journal.get(day, (None, None))
        groups[g].append((m.get("bol") if m else None, j[0], j[1]))
        day += datetime.timedelta(1)
    rows = []
    for g, vals in groups.items():
        cols = []
        for k in range(3):
            xs = [v[k] for v in vals if v[k] is not None]
            cols.append(chislo(statistics.mean(xs)) + f" ({len(xs)})" if xs else "—")
        rows.append((g, *cols))
    return rows


def raschet(marks, journal, today, teen):
    starts, periods = starts_and_periods(marks)
    lens = [(b - a).days for a, b in zip(starts, starts[1:])]
    lo, hi = (21, 45) if teen else (24, 38)
    warn = []
    for (a, b), n in zip(zip(starts, starts[1:]), lens):
        if n < lo or n > hi:
            warn.append(f"цикл с {fmt(a)} — {n} дн. (обычно {lo}–{hi})")
    for s, p in zip(starts, periods):
        if p > 8:
            warn.append(f"месячные с {fmt(s)} — {p} дн. (обычно до 8)")
    if not teen and len(lens) >= 3 and max(lens) - min(lens) > 9:  # у подростков цикл в первые годы неровный
        warn.append(f"разброс циклов {max(lens) - min(lens)} дн. (обычно до 9)")
    if starts and (today - starts[-1]).days >= 90:
        warn.append(f"нет месячных {(today - starts[-1]).days} дн. (с {fmt(starts[-1])})")
    if starts and any(m["bol"] == 3 for d, m in marks.items() if d >= starts[0]):
        n = sum(1 for s in starts if any(marks.get(s + datetime.timedelta(k), {}).get("bol") == 3 for k in range(-5, 5)))
        if n >= 2:
            warn.append(f"боль «3 — мешает делам» в {n} циклах")
    sred = round(statistics.mean(lens[-6:])) if lens else None
    razbros = (max(lens[-6:]) - min(lens[-6:])) if len(lens) >= 2 else None
    ozhid = starts[-1] + datetime.timedelta(sred) if sred and starts else None
    return {"starts": starts, "periods": periods, "lens": lens, "warn": warn, "sred": sred,
            "razbros": razbros, "ozhid": ozhid, "teen": teen,
            "zak": zakonomernosti(marks, journal, starts)}


def itogi(r, today):
    out = [START, f"*Пишет программа `tsikl.py` ({today.isoformat()}); руками не править.*", ""]
    if not r["starts"]:
        out += ["Отметок с началом цикла ещё нет: отметьте дни месячных в файле месяца.", END]
        return out
    out.append(f"**Отмечено циклов:** {len(r['starts'])} (с {fmt(r['starts'][0])}); полных: {len(r['lens'])}.")
    if r["sred"]:
        rz = f", разброс {r['razbros']} дн" if r["razbros"] is not None else ""
        out.append(f"**Средний цикл:** {r['sred']} дн (по последним {min(len(r['lens']), 6)}){rz}. "
                   f"**Месячные:** обычно {round(statistics.mean(r['periods']))} дн.")
        if r["ozhid"]:
            pm = f" ± {max(1, (r['razbros'] or 0) // 2)} дн" if r["razbros"] else ""
            out.append(f"**Следующие ожидаются:** около {fmt(r['ozhid'])}{pm}.")
    out.append("")
    out.append("| Начало | Цикл, дн. | Месячные, дн. |")
    out.append("|---|---|---|")
    for i, s in enumerate(r["starts"][-12:]):
        k = len(r["starts"]) - len(r["starts"][-12:]) + i
        n = r["lens"][k] if k < len(r["lens"]) else "идёт"
        out.append(f"| {fmt(s)} | {n} | {r['periods'][k]} |")
    out.append("")
    norma = "21–45 (подростки)" if r["teen"] else "24–38"
    if r["warn"]:
        out.append(f"**⚠ Стоит показаться врачу с этими отметками** (нормы: цикл {norma} дн., месячные до 8 дн., "
                   "разброс до 9 дн.; это не диагноз): " + "; ".join(r["warn"]) + ".")
    else:
        out.append(f"**Нормы:** всё в пределах (цикл {norma} дн., месячные до 8 дн., разброс до 9 дн.).")
    out.append("")
    if r["zak"]:
        out += ["**Мои закономерности** (средние по отметкам; в скобках — сколько дней с отметкой; "
                "настроение и энергия — из журнала дня):", "",
                "| Дни | Боль 0–3 | Настроение | Энергия |", "|---|---|---|---|"]
        out += [f"| {g} | {a} | {b} | {c} |" for g, a, b, c in r["zak"]]
        out += ["", "*Разница меньше 1 балла — скорее случайность. Закономерность, которая повторяется "
                "от цикла к циклу, можно учитывать в планах ([[Время и внимание]]).*"]
    else:
        out.append("**Мои закономерности** появятся после двух полных циклов отметок.")
    out.append(END)
    return out


def write(idx, r, today):
    text = idx.read_text(encoding="utf-8")
    block = "\n".join(itogi(r, today))
    if START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        new = text[:a] + block + text[b:]
    else:
        new = text.rstrip("\n") + "\n\n## Итоги\n\n" + block + "\n"
    ch = new != text
    if ch:
        idx.write_text(new, encoding="utf-8")
    vals = {"средний цикл": r["sred"] if r["sred"] is not None else "",
            "разброс": r["razbros"] if r["razbros"] is not None else "",
            "ожидается": f'"{r["ozhid"].isoformat()}"' if r["ozhid"] else ""}
    return write_fm(idx, vals, "сфера") or ch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--data")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.data) if a.data else datetime.date.today()
    d, idx = papka()
    if not idx:
        print("Цикл: модуль не включён.")
        return 0
    errors = []
    marks = load_marks(d, errors)
    for e in errors:
        print("✖ " + e)
    if errors:
        return 1
    r = raschet(marks, load_journal(), today, podrostok(today))
    for w in r["warn"]:
        print("⚠ " + w)
    if a.write and write(idx, r, today):
        print(f"записано: {idx.name}")
    print(f"Цикл: отметок {len(marks)}, циклов {len(r['starts'])}, средний {r['sred'] or '—'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
