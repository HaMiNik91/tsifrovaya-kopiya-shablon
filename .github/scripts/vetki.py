#!/usr/bin/env python3
"""Ветки событий (апгрейд 4.2, 03.11.2026; CLAUDE.md, п. 5.6).

Ветка — план события с началом и концом (переезд, новый питомец, беременность…) в три фазы:
подготовка → процесс → привыкание.

Как устроено:
- Заготовки — `80 Шаблоны/Ветки/Ветка — Вид.md` (`статус: заготовка`); пустой образец — «Шаблон — Ветка».
- Живая ветка — `70 Ветки/ГГГГ-ММ-ДД Ветка — Тема.md` (дата — день запуска; `тип: ветка`).
- Разделы `## Подготовка`, `## Процесс`, `## Привыкание` — шаги-галочки одной строкой:
      - [ ] Что сделать · 12 · −8 нед · Todoist · Путь
  через « · »: сферы («12» или «07, 01»), срок относительно `день события`
  («−3 дн», «−8 нед», «+2 мес», «день события», «по ходу» — без даты), пометки «Todoist» (задача
  со сроком), «Путь» (шаг в «Путь» сферы при запуске). Дату срока « · до ГГГГ-ММ-ДД» дописывает программа.
- Раздел «Сейчас» (между строками-метками) и свойство `фаза` пишет программа: сделано по фазам,
  просроченное, ближайшие шаги. Фаза — по календарю: до дня события — подготовка; до последнего
  срока «Процесса» — процесс; дальше — привыкание.

Запуск:
  python3 .github/scripts/vetki.py           — проверка, ничего не пишет
  python3 .github/scripts/vetki.py --write   — даты сроков, `фаза`, раздел «Сейчас» во всех идущих ветках
  python3 .github/scripts/vetki.py --zapusk Вид --tema "Тема" [--den ГГГГ-ММ-ДД] [--data ГГГГ-ММ-ДД]
      — завести ветку из заготовки «Ветка — Вид»: файл в «70 Ветки», шаги «Путь» в сферах,
        список задач для Todoist (их ставит Claude). Без --den даты не считаются (дописать позже).
  python3 .github/scripts/vetki.py --zavershit "ГГГГ-ММ-ДД Ветка — Тема" [--data ГГГГ-ММ-ДД] [--otmena]
      — закончить ветку: `статус: закончена` (или `отменена`), `до`, период в «Опыт» главной сферы
        (первая в `сферы`), чтобы событие попало в «Летопись жизни».
Ошибки — ✖ (исправить), предупреждения — ⚠ (назвать пользователю).
"""
import argparse
import datetime
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from shkala import read_fm, write_fm  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SFERY = ROOT / "10 Сферы"
VETKI = ROOT / "70 Ветки"
ZAGOTOVKI = ROOT / "80 Шаблоны" / "Ветки"
TIP = "ветка"
FAZY = ("Подготовка", "Процесс", "Привыкание")
STATUSY = ("заготовка", "идёт", "закончена", "отменена")
START, END = "<!-- vetki: начало -->", "<!-- vetki: конец -->"
STEP = re.compile(r"^- \[([ xX])\] (.+)$")
SROK = re.compile(r"^([−+-])(\d+) (дн|нед|мес)$")
SFERA = re.compile(r"^\d{2}(, \d{2})*$")
DO = re.compile(r"^до (\d{4}-\d{2}-\d{2})$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
H2 = re.compile(r"^## (.+?)\s*$")
FM = re.compile(r"\A---\n.*?\n---\n", re.S)


def spheres():
    """Код сферы → имя папки (оно же имя оглавления)."""
    res = {}
    for d in sorted(SFERY.iterdir()):
        idx = d / f"{d.name}.md"
        if d.is_dir() and idx.exists():
            kod = read_fm(idx.read_text(encoding="utf-8")).get("код", "")
            if kod:
                res[kod] = d.name
    return res


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    days = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return datetime.date(y, m, min(d.day, days[m - 1]))


def srok_date(srok, den, start=None):
    """Дата срока шага от дня события; None — без даты. Срок раньше запуска ветки (`когда`)
    сдвигается на день запуска: раньше начала шаг сделать нельзя."""
    if den is None or srok in (None, "по ходу"):
        return None
    if srok == "день события":
        d = den
    else:
        m = SROK.match(srok)
        k = -int(m.group(2)) if m.group(1) in "−-" else int(m.group(2))
        if m.group(3) == "дн":
            d = den + datetime.timedelta(days=k)
        elif m.group(3) == "нед":
            d = den + datetime.timedelta(weeks=k)
        else:
            d = add_months(den, k)
    return max(d, start) if start and d < start else d


def short(text):
    """Имя шага «Путь»: до двоеточия или скобки, не длиннее 60 знаков, без запрещённых в Windows знаков."""
    t = re.split(r"[:(;]", text)[0].strip()
    if len(t) > 60:
        t = t[:60].rsplit(" ", 1)[0]
    return re.sub(r'[\\/*?"<>|]', "_", t).rstrip(" ,.")


def parse_step(text, kody, where, errors):
    """Строка шага → словарь; ошибки формы — в errors."""
    parts = [p.strip() for p in text.split(" · ")]
    st = {"text": parts[0], "sfery": [], "srok": None, "todoist": False, "put": False}
    for p in parts[1:]:
        if SFERA.match(p):
            st["sfery"] = p.split(", ")
            for k in st["sfery"]:
                if k not in kody:
                    errors.append(f"{where}: сферы {k} нет")
        elif p in ("день события", "по ходу") or SROK.match(p):
            st["srok"] = p
        elif p == "Todoist":
            st["todoist"] = True
        elif p == "Путь":
            st["put"] = True
        elif DO.match(p):
            pass  # дату пишет программа, пересчитывается
        else:
            errors.append(f"{where}: непонятная часть «{p}» (сферы «12», срок «−8 нед», «Todoist», «Путь»)")
    if st["srok"] is None:
        errors.append(f"{where}: нет срока («−8 нед», «день события», «по ходу»)")
    if st["put"] and not st["sfery"]:
        errors.append(f"{where}: для «Путь» нужна сфера")
    return st


def load(path, kody, errors, warnings):
    text = path.read_text(encoding="utf-8")
    fm = read_fm(text)
    name = path.stem
    v = {"path": path, "name": name, "fm": fm, "text": text, "steps": []}
    status = fm.get("статус", "")
    if status not in STATUSY:
        errors.append(f"{name}: `статус` «{status}» — нужно одно из: {', '.join(STATUSY)}")
    v["status"] = status
    den = fm.get("день события", "")
    v["den"] = None
    st = fm.get("когда", "")
    v["start"] = datetime.date.fromisoformat(st) if DATE.match(st or "") else None
    if den:
        if DATE.match(den):
            v["den"] = datetime.date.fromisoformat(den)
        else:
            errors.append(f"{name}: `день события` «{den}» — нужно ГГГГ-ММ-ДД")
    for k in fm.get("сферы", []) or []:
        kod = k.strip("[]")[:2]
        if kod not in kody:
            errors.append(f"{name}: в `сферы` нет сферы «{k}»")
    faza, seen, i = None, [], 0
    for i, line in enumerate(text.splitlines(), 1):
        h = H2.match(line)
        if h:
            faza = h.group(1) if h.group(1) in FAZY else None
            if faza:
                seen.append(faza)
            continue
        m = STEP.match(line)
        if m and faza:
            st = parse_step(m.group(2), kody, f"{name}, строка {i}", errors)
            st.update(done=m.group(1) != " ", faza=faza, line=i)
            v["steps"].append(st)
    if tuple(seen) != FAZY:
        errors.append(f"{name}: нужны разделы «## Подготовка», «## Процесс», «## Привыкание» по порядку (есть: {', '.join(seen) or 'нет'})")
    if status == "идёт" and not v["den"]:
        warnings.append(f"{name}: нет `день события` — сроки не посчитаны")
    return v


def faza_now(v, today):
    if not v["den"]:
        return None
    if today < v["den"]:
        return "подготовка"
    proc = [srok_date(s["srok"], v["den"], v["start"]) for s in v["steps"] if s["faza"] == "Процесс"]
    end = max([d for d in proc if d] + [v["den"]])
    return "процесс" if today <= end else "привыкание"


def fmt(d):
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def svodka(v, today):
    out = [START, f"*Пишет программа `vetki.py` ({today.isoformat()}); руками не править.*", ""]
    if v["den"]:
        delta = (v["den"] - today).days
        when = (f"через {delta} дн." if delta > 0 else "сегодня" if delta == 0 else f"{-delta} дн. назад")
        out.append(f"**День события:** {fmt(v['den'])} ({when}) · **Фаза:** {faza_now(v, today)}")
    else:
        out.append("**День события** не задан — сроки не посчитаны.")
    out.append("")
    out.append("| Фаза | Сделано |")
    out.append("|---|---|")
    for f in FAZY:
        ss = [s for s in v["steps"] if s["faza"] == f]
        out.append(f"| {f} | {sum(s['done'] for s in ss)} из {len(ss)} |")
    late, soon = [], []
    for s in v["steps"]:
        d = srok_date(s["srok"], v["den"], v["start"])
        if s["done"] or not d:
            continue
        (late if d < today else soon).append((d, s["text"]))
    if late:
        late = sorted(late)
        more = f"; и ещё {len(late) - 5}" if len(late) > 5 else ""
        out += ["", "**Просрочено:** " + "; ".join(f"{t} (до {fmt(d)})" for d, t in late[:5]) + more]
    if soon:
        out += ["", "**Ближайшее:** " + "; ".join(f"{t} (до {fmt(d)})" for d, t in sorted(soon)[:3])]
    out.append(END)
    return out


def render(v, today):
    """Текст ветки: даты сроков в строках шагов и раздел «Сейчас»."""
    lines = v["text"].splitlines()
    for s in v["steps"]:
        line = lines[s["line"] - 1]
        parts = [p for p in line.split(" · ") if not DO.match(p.strip())]
        d = srok_date(s["srok"], v["den"], v["start"])
        if d:
            parts.append(f"до {d.isoformat()}")
        lines[s["line"] - 1] = " · ".join(parts)
    text = "\n".join(lines) + "\n"
    block = "\n".join(svodka(v, today))
    if START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a] + block + text[b:]
    else:
        text = text.replace("\n## Подготовка", f"\n## Сейчас\n\n{block}\n\n## Подготовка", 1)
    return text


def write(v, today):
    new = render(v, today)
    changed = new != v["text"]
    if changed:
        v["path"].write_text(new, encoding="utf-8")
    f = faza_now(v, today)
    if f and write_fm(v["path"], {"фаза": f}, "статус"):
        changed = True
    return changed


def zapusk(a, kody, today):
    src = ZAGOTOVKI / f"Ветка — {a.zapusk}.md"
    if not src.exists():
        print(f"✖ заготовки «{src.name}» нет; есть: " + ", ".join(p.stem for p in sorted(ZAGOTOVKI.glob('*.md'))))
        return 1
    if a.den and not DATE.match(a.den):
        print("✖ --den нужно ГГГГ-ММ-ДД")
        return 1
    dst = VETKI / f"{today.isoformat()} Ветка — {a.tema}.md"
    if dst.exists():
        print(f"⚠ ветка уже есть: {dst.name}")
        return 0
    text = src.read_text(encoding="utf-8")
    fm = read_fm(text)
    body = text[FM.match(text).end():]
    body = re.sub(r"^# .+$", f"# {a.tema}", body, count=1, flags=re.M)
    body = body.replace("Заготовка ветки", f"Заготовка: [[{src.stem}]]. Ветка", 1)
    head = ["---", "тип: ветка", f"вид: {fm.get('вид', '')}", "статус: идёт", "фаза: подготовка",
            f'когда: "{today.isoformat()}"', 'до: "сейчас"', f'день события: "{a.den or ""}"',
            f"линия: {fm.get('линия', '')}", "сферы:"]
    head += [f'  - "{k}"' for k in fm.get("сферы", []) or []]
    head += ["люди: []", f"обновлено: {today.isoformat()}", "---"]
    VETKI.mkdir(exist_ok=True)
    dst.write_text("\n".join(head) + "\n" + body, encoding="utf-8")
    errors, warnings = [], []
    v = load(dst, kody, errors, warnings)
    if errors:
        dst.unlink()
        print("\n".join("✖ " + e for e in errors))
        return 1
    write(v, today)
    v = load(dst, kody, [], [])
    print(f"создана: {dst.relative_to(ROOT)}")
    for s in v["steps"]:
        if s["put"]:
            kod = s["sfery"][0]
            step = SFERY / kody[kod] / "Путь" / f"{kod} Шаг — {short(s['text'])}.md"
            if step.exists():
                print(f"⚠ шаг уже есть: {step.name}")
                continue
            d = srok_date(s["srok"], v["den"], v["start"])
            step.write_text("\n".join([
                "---", "тип: шаг", f'сфера: "[[{kody[kod]}]]"', "луч:", "важность:", "простота:",
                "статус:", f"обновлено: {today.isoformat()}", "---", f"# {short(s['text'])}", "", s["text"], "",
                f"Ветка: [[{dst.stem}]], фаза «{s['faza']}»" + (f", срок — до {d.isoformat()}." if d else "."), ""]),
                encoding="utf-8")
            print(f"шаг в «Путь»: {step.relative_to(ROOT)}")
    todo = [s for s in v["steps"] if s["todoist"]]
    if todo:
        print("\nЗадачи для Todoist (проект с именем ветки):")
        for s in todo:
            d = srok_date(s["srok"], v["den"], v["start"])
            print(f"  - {s['text']} — {d.isoformat() if d else 'без срока'}")
    return 0


def zavershit(a, kody, today):
    path = VETKI / f"{a.zavershit}.md"
    if not path.exists():
        print(f"✖ ветки «{a.zavershit}» нет")
        return 1
    errors = []
    v = load(path, kody, errors, [])
    if errors:
        print("\n".join("✖ " + e for e in errors))
        return 1
    end = a.data or today.isoformat()
    status = "отменена" if a.otmena else "закончена"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^статус: .*$", f"статус: {status}", text, count=1, flags=re.M)
    text = re.sub(r"^до: .*$", f'до: "{end}"', text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
    sf = v["fm"].get("сферы", []) or []
    if not sf:
        print(f"⚠ у ветки нет `сферы` — период в «Опыт» не создан; ветка {status}")
        return 0
    main_name = sf[0].strip("[]")
    kod = main_name[:2]
    tema = path.stem.split(" Ветка — ", 1)[1]
    start = v["fm"].get("когда", "")
    opyt = SFERY / kody[kod] / "Опыт" / f"{kod} {start[:7]} {tema}.md"
    if opyt.exists():
        print(f"⚠ период уже есть: {opyt.name}")
    else:
        done = sum(s["done"] for s in v["steps"])
        vliyaet = "".join(f'\n  - "{x}"' for x in sf[1:])
        opyt.write_text("\n".join([
            "---", "тип: опыт", f'сфера: "[[{main_name}]]"', "вид: период", f'когда: "{start}"', f'до: "{end}"',
            f"линия: {v['fm'].get('линия', '')}", "период:", "влияет:" + (vliyaet if vliyaet else " []"),
            "темы: []", "люди: []", "значимость:", "влияние:", "проработка:", "статус: черновик",
            f"обновлено: {today.isoformat()}", "---",
            f"Источник: [[{path.stem}]]", "", "## Что было", "",
            f"Ветка «{tema}» ({status}): с {start}" + (f", день события — {v['den'].isoformat()}" if v["den"] else "")
            + f", до {end}. Шагов сделано: {done} из {len(v['steps'])}.", "",
            "## Как это повлияло", "", "## Связь с убеждениями", ""]), encoding="utf-8")
        print(f"период в «Опыт»: {opyt.relative_to(ROOT)}")
    print(f"ветка {status}: {path.name}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--zapusk")
    ap.add_argument("--tema")
    ap.add_argument("--den")
    ap.add_argument("--zavershit")
    ap.add_argument("--otmena", action="store_true")
    ap.add_argument("--data")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.data) if a.data and not a.zavershit else datetime.date.today()
    kody = spheres()
    if a.zapusk:
        if not a.tema:
            print("✖ нужна --tema")
            return 1
        return zapusk(a, kody, today)
    if a.zavershit:
        return zavershit(a, kody, today)
    errors, warnings, items = [], [], []
    for p in sorted(ZAGOTOVKI.glob("*.md")):
        v = load(p, kody, errors, warnings)
        if v["status"] != "заготовка":
            errors.append(f"{p.stem}: у заготовки `статус: заготовка`")
        if not v["steps"]:
            errors.append(f"{p.stem}: нет ни одного шага")
    for p in sorted(VETKI.glob("*.md")) if VETKI.exists() else []:
        if read_fm(p.read_text(encoding="utf-8")).get("тип") != TIP:
            continue
        v = load(p, kody, errors, warnings)
        items.append(v)
        if v["status"] == "заготовка":
            errors.append(f"{p.stem}: `заготовка` — только в «80 Шаблоны/Ветки»")
    for e in errors:
        print("✖ " + e)
    for w in warnings:
        print("⚠ " + w)
    if errors:
        return 1
    going = [v for v in items if v["status"] == "идёт"]
    if a.write:
        for v in going:
            if write(v, today):
                print(f"записано: {v['name']}")
    print(f"заготовок: {len(list(ZAGOTOVKI.glob('*.md')))}, веток: {len(items)} (идут: {len(going)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
