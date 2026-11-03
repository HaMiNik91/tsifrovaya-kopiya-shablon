#!/usr/bin/env python3
"""План недели — часы по сферам: план против сделанного (апгрейд 3.5, 03.11.2026; CLAUDE.md, п. 9.6–9.7).

Как устроено:
- Файл недели — `20 Журнал/ГГГГ-ММ-ДД План недели.md` (шаблон «Шаблон — План недели»; `тип: план недели`),
  дата — понедельник; в `когда` — та же дата.
- `сделано` в шапке — часы блоков внимания за неделю, строка на сферу: "10 Финансы: 1,5"
  (по номеру впереди программа узнаёт сферу; название после номера — для человека). Оплачиваемая работа не входит.
- План — свойство `часы` в «NN Шкала» каждой сферы. Пока неделя идёт, берётся нынешнее `часы`;
  у закончившейся недели план берётся из её же раздела «Итоги» (снимок), чтобы смена `часы` потом
  не переписала историю. Нет снимка — берётся нынешнее `часы` с пометкой.
- Раздел «Итоги» (между строками-метками) — таблица «сфера — план — сделано — как», всего часов,
  сферы-приоритеты без времени. Это же основа будущего экрана «Эта неделя» на сайте.

Запуск:
  python3 .github/scripts/nedelya.py            — проверка и отчёт, ничего не пишет
  python3 .github/scripts/nedelya.py --write    — записать раздел «Итоги» во все планы недели
  python3 .github/scripts/nedelya.py --dobavit 10=1,5 06=0,5 [--data ГГГГ-ММ-ДД]
      — прибавить часы к `сделано` недели, в которую попадает дата (по умолчанию сегодня);
        файла недели нет — создать из шаблона; затем записать «Итоги». Минус — убавить: 10=-0,5
  python3 .github/scripts/nedelya.py --nedelya ГГГГ-ММ-ДД
      — создать файл недели, в которую попадает дата (если его ещё нет), и записать «Итоги»
Ошибки — ✖ (исправить), предупреждения — ⚠ (назвать пользователю).
"""
import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from shkala import read_fm, write_fm, flag  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SFERY = ROOT / "10 Сферы"
ZHURNAL = ROOT / "20 Журнал"
SHABLON = ROOT / "80 Шаблоны" / "Шаблон — План недели.md"
TIP = "план недели"
START, END = "<!-- nedelya: начало -->", "<!-- nedelya: конец -->"
LINE = re.compile(r"^(\d{2})\b[^:]*:\s*(-?[\d.,]+)\s*$")
ROW = re.compile(r"^\|\s*\[\[(\d{2})[^\]]*\]\]\s*\|\s*([\d.,]+)\s*\|")
MES = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
       "августа", "сентября", "октября", "ноября", "декабря"]


def num(s):
    return float(str(s).replace(" ", "").replace(",", "."))


def fmt(x):
    """1.5 → «1,5»; 3.0 → «3»."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def monday(d):
    return d - datetime.timedelta(days=d.weekday())


def week_label(mon):
    sun = mon + datetime.timedelta(days=6)
    if mon.month == sun.month:
        return f"{mon.day}–{sun.day} {MES[sun.month - 1]} {sun.year}"
    return f"{mon.day} {MES[mon.month - 1]} – {sun.day} {MES[sun.month - 1]} {sun.year}"


def load_spheres():
    """Видимые сферы: код → {name, plan, prio, vazh}."""
    res = {}
    for d in sorted(SFERY.iterdir()):
        idx = d / f"{d.name}.md"
        if not d.is_dir() or not idx.exists():
            continue
        ifm = read_fm(idx.read_text(encoding="utf-8"))
        kod = ifm.get("код", "")
        if not kod or flag(ifm.get("скрыта")):
            continue
        shk = d / f"{kod} Шкала.md"
        sfm = read_fm(shk.read_text(encoding="utf-8")) if shk.exists() else {}

        def n(key, conv=num):
            try:
                return conv(sfm.get(key))
            except (TypeError, ValueError):
                return None
        res[kod] = {"name": d.name, "plan": n("часы") or 0.0, "prio": n("приоритет", int),
                    "vazh": n("важность", int) or 0}
    return res


def load_weeks():
    res = []
    if not ZHURNAL.exists():
        return res
    for p in sorted(ZHURNAL.glob("*.md")):
        t = p.read_text(encoding="utf-8")
        fm = read_fm(t)
        if fm.get("тип") == TIP:
            res.append((p, fm, t))
    return res


def parse_done(fm, spheres, where, errors):
    done = {}
    vals = fm.get("сделано") or []
    if isinstance(vals, str):
        vals = [vals]
    for v in vals:
        m = LINE.match(v.strip())
        if not m:
            errors.append(f"✖ {where}: строка `сделано` не по форме «NN Сфера: часы» — «{v}»")
            continue
        kod, h = m.group(1), num(m.group(2))
        if kod not in spheres:
            errors.append(f"✖ {where}: в `сделано` нет такой видимой сферы — «{v}»")
        elif kod in done:
            errors.append(f"✖ {where}: сфера {kod} в `сделано` дважды — одна строка на сферу")
        elif h < 0:
            errors.append(f"✖ {where}: отрицательные часы — «{v}»")
        else:
            done[kod] = h
    return done


def snapshot(text):
    """План из прошлого раздела «Итоги»: {код: часы} или None."""
    if START not in text or END not in text:
        return None
    blk = text[text.index(START):text.index(END)]
    res = {}
    for line in blk.splitlines():
        m = ROW.match(line)
        if m:
            res[m.group(1)] = num(m.group(2))
    return res or None


def block(mon, today, plan, done, spheres, from_snapshot):
    sun = mon + datetime.timedelta(days=6)
    state = "идёт" if mon <= today <= sun else ("закончилась" if today > sun else "ещё не началась")
    lines = [START, "*Посчитано программой `nedelya.py` — руками не править.*", ""]
    tp, td = sum(plan.values()), sum(done.values())
    pct = f" ({round(td / tp * 100)} %)" if tp else ""
    lines.append(f"**Неделя {week_label(mon)}** — {state}. **Блоков внимания:** {fmt(td)} ч из {fmt(tp)} ч плана{pct}.")
    if state == "закончилась" and not from_snapshot:
        lines.append("")
        lines.append("*План — по нынешним `часы` сфер: снимка плана этой недели не было.*")
    lines.append("")
    rows = [k for k in spheres if plan.get(k, 0) > 0 or done.get(k, 0) > 0]
    rows.sort(key=lambda k: (spheres[k]["prio"] or 99, -spheres[k]["vazh"], k))
    lines.append("| Сфера | План, ч | Сделано, ч | Как |")
    lines.append("|---|---|---|---|")
    for k in rows:
        p, d = plan.get(k, 0.0), done.get(k, 0.0)
        if p == 0:
            how = "сверх плана"
        elif d >= p:
            how = "✓"
        else:
            how = f"меньше на {fmt(p - d)}"
        if spheres[k]["prio"]:
            how += f" · место {spheres[k]['prio']}"
        lines.append(f"| [[{spheres[k]['name']}]] | {fmt(p)} | {fmt(d)} | {how} |")
    lines.append(f"| **Всего** | {fmt(tp)} | {fmt(td)} | |")
    empty = [spheres[k]["name"] for k in rows if spheres[k]["prio"] and done.get(k, 0) == 0]
    if empty:
        lines.append("")
        lines.append("**Сферы-приоритеты без времени:** " + ", ".join(f"[[{n}]]" for n in empty))
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def create_week(mon):
    p = ZHURNAL / f"{mon.isoformat()} План недели.md"
    if p.exists():
        return p, False
    t = SHABLON.read_text(encoding="utf-8").replace("{{date}}", mon.isoformat())
    t = t.replace("# План недели", f"# План недели {week_label(mon)}", 1)
    ZHURNAL.mkdir(exist_ok=True)
    p.write_text(t, encoding="utf-8")
    return p, True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dobavit", nargs="+", metavar="NN=часы")
    ap.add_argument("--data", help="дата внутри недели, ГГГГ-ММ-ДД (по умолчанию сегодня)")
    ap.add_argument("--nedelya", metavar="ГГГГ-ММ-ДД")
    args = ap.parse_args()
    today = datetime.date.today()
    spheres = load_spheres()
    errors, warns = [], []

    if args.nedelya or args.dobavit:
        try:
            d = datetime.date.fromisoformat(args.nedelya or args.data) if (args.nedelya or args.data) else today
        except ValueError:
            print("✖ дата — в виде ГГГГ-ММ-ДД")
            return 1
        p, new = create_week(monday(d))
        print(("создан: " if new else "неделя: ") + p.name)
        if args.dobavit:
            fm = read_fm(p.read_text(encoding="utf-8"))
            done = parse_done(fm, spheres, p.name, errors)
            for a in args.dobavit:
                m = re.match(r"^(\d{2})\s*[=:]\s*(-?[\d.,]+)$", a.strip())
                if not m or m.group(1) not in spheres:
                    errors.append(f"✖ --dobavit: «{a}» — нужно «NN=часы», NN — номер видимой сферы")
                    continue
                kod, h = m.group(1), num(m.group(2))
                if done.get(kod, 0) + h < 0:
                    errors.append(f"✖ --dobavit: у сферы {kod} часов станет меньше нуля")
                    continue
                done[kod] = done.get(kod, 0) + h
                print(f"  {spheres[kod]['name']}: +{fmt(h)} → {fmt(done[kod])} ч")
            if errors:
                for e in errors:
                    print(e)
                print("Ничего не записано.")
                return 1
            vals = [f"{k} {spheres[k]['name'][3:]}: {fmt(v)}" for k, v in sorted(done.items()) if v > 0]
            write_fm(p, {"сделано": vals, "обновлено": today.isoformat()}, "когда")
        args.write = True

    weeks = load_weeks()
    for p, fm, text in weeks:
        where = p.name
        try:
            mon = datetime.date.fromisoformat(str(fm.get("когда", "")).strip())
        except ValueError:
            errors.append(f"✖ {where}: `когда` — дата понедельника ГГГГ-ММ-ДД")
            continue
        if mon.weekday() != 0:
            errors.append(f"✖ {where}: `когда` {mon} — не понедельник")
        if not p.name.startswith(mon.isoformat()):
            errors.append(f"✖ {where}: дата в имени файла не совпадает с `когда` ({mon})")
        done = parse_done(fm, spheres, where, errors)
        sun = mon + datetime.timedelta(days=6)
        snap = snapshot(text) if today > sun else None
        plan = snap if snap is not None else {k: s["plan"] for k, s in spheres.items()}
        td, tp = sum(done.values()), sum(plan.values())
        print(f"{week_label(mon)}: сделано {fmt(td)} ч из {fmt(tp)} ч плана")
        if mon <= today <= sun:
            for k, s in spheres.items():
                if s["prio"] and done.get(k, 0) == 0 and today.weekday() >= 3:
                    warns.append(f"⚠ {where}: сфера-приоритет «{s['name']}» — пока 0 ч, а уже {['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][today.weekday()]}")
        if args.write:
            if START not in text or END not in text:
                errors.append(f"✖ {where}: нет строк-меток раздела «Итоги» ({START} … {END})")
                continue
            new = block(mon, today, plan, done, spheres, snap is not None)
            text2 = text[:text.index(START)] + new + text[text.index(END) + len(END):]
            if text2 != text:
                p.write_text(text2, encoding="utf-8")
                print(f"  записано: {p.name}")
    for e in errors:
        print(e)
    for w in warns:
        print(w)
    if not errors:
        print(f"План недели: ошибок нет, недель {len(weeks)}.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
