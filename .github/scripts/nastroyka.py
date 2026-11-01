#!/usr/bin/env python3
"""Настройка копии по профилю: набор на старте и модули (CLAUDE.md, п. 5.2, «Профиль»).

Запуск из корня хранилища:
    python3 .github/scripts/nastroyka.py --proverit   — показать, что изменится (ничего не пишет)
    python3 .github/scripts/nastroyka.py              — применить; затем shkala.py --write

Откуда что берётся — «00 Старт/Профиль.md»:
  • `набор` — с чего начать («80 Шаблоны/Наборы/Набор — <имя>.md»: `скрытые сферы` — коды сфер,
    `скрытые лучи` — коды лучей). Набор применяется ОДИН раз: у сфер и лучей ставится `скрыта` / `скрыт`
    по набору, в профиль пишется `набор применён`. Дальше владелец сам открывает и скрывает что хочет;
    программа набор не повторяет, пока `набор` в профиле не сменится.
  • `модули` — какие модули включены («80 Шаблоны/Модули/<имя>/»: файлы модуля лежат в `файлы/` по тем же
    путям, что в копии). Включён новый модуль — его файлы раскладываются по местам (если файла ещё нет;
    если модуль раньше выключали — файлы возвращаются из архива вместе с оценками). Модуль убран из списка —
    его файлы переносятся в «90 Архив/Модули/<имя>/», ничего не удаляется. Основа не выключается.
    Что включено сейчас, программа помнит в `модули включены`.
Код выхода: 0 — всё хорошо (или нечего делать), 1 — ошибка (ничего не записано).
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFIL = ROOT / "00 Старт" / "Профиль.md"
NABORY = ROOT / "80 Шаблоны" / "Наборы"
MODULI = ROOT / "80 Шаблоны" / "Модули"
ARHIV = ROOT / "90 Архив" / "Модули"
SFERY = ROOT / "10 Сферы"
OSNOVA = "Основа"
FM = re.compile(r"\A---\n(.*?\n)---\n", re.S)


def read_fm(text):
    m = FM.match(text)
    out, key = {}, None
    if not m:
        return out
    for line in m.group(1).splitlines():
        if re.match(r"^\s+-\s", line) and key:
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(line.split("-", 1)[1].strip().strip('"'))
        elif ":" in line and not line.startswith(" "):
            key, val = (x.strip() for x in line.split(":", 1))
            out[key] = val.strip('"') if val else []
    return out


def set_fm(text, key, value, after=None):
    """Поставить свойство в шапке: заменить строку (со списком) или вставить после `after` (иначе в конец)."""
    m = FM.match(text)
    lines = m.group(1).splitlines()
    new = [f"{key}:"] + [f'  - "{x}"' for x in value] if isinstance(value, list) else [f"{key}: {value}"]
    out, i, done = [], 0, False
    while i < len(lines):
        if lines[i].split(":", 1)[0] == key and not lines[i].startswith(" "):
            i += 1
            while i < len(lines) and re.match(r"^\s+-\s", lines[i]):
                i += 1
            out += new
            done = True
            continue
        out.append(lines[i])
        i += 1
    if not done:
        pos = next((j + 1 for j, ln in enumerate(out) if after and ln.split(":", 1)[0] == after), len(out))
        out[pos:pos] = new
    return "---\n" + "\n".join(out) + "\n---\n" + text[m.end():]


def spisok(v):
    return [x for x in (v if isinstance(v, list) else [v] if v else []) if x]


def shapki():
    """(путь, тип, код) оглавлений сфер и лучей."""
    for p in sorted(SFERY.glob("*/*.md")) + sorted(SFERY.glob("*/Шкала/*.md")):
        fm = read_fm(p.read_text(encoding="utf-8"))
        if fm.get("тип") in ("оглавление", "луч") and fm.get("код"):
            yield p, fm["тип"], fm["код"]


def fayly_modulya(name):
    base = MODULI / name / "файлы"
    return [p.relative_to(base) for p in sorted(base.rglob("*")) if p.is_file()] if base.exists() else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proverit", action="store_true")
    a = ap.parse_args()
    if not PROFIL.exists():
        sys.exit("✖ нет «00 Старт/Профиль.md»")
    prof_text = PROFIL.read_text(encoding="utf-8")
    prof = read_fm(prof_text)
    zapis, perenos, report, errs = {}, [], [], []

    # 1. Набор — один раз
    nabor = prof.get("набор") or ""
    if isinstance(nabor, list):
        nabor = nabor[0] if nabor else ""
    if nabor and nabor != (prof.get("набор применён") or ""):
        f = NABORY / f"Набор — {nabor}.md"
        if not f.exists():
            errs.append(f"набора «{nabor}» нет: есть {', '.join(p.stem[8:] for p in NABORY.glob('Набор — *.md'))}")
        else:
            nf = read_fm(f.read_text(encoding="utf-8"))
            sk_sf, sk_l = set(spisok(nf.get("скрытые сферы"))), set(spisok(nf.get("скрытые лучи")))
            for p, tip, kod in shapki():
                key, nado = ("скрыта", kod in sk_sf) if tip == "оглавление" else ("скрыт", kod in sk_l)
                t = zapis.get(p) or p.read_text(encoding="utf-8")
                if (read_fm(t).get(key) == "true") != nado:
                    zapis[p] = set_fm(t, key, "true" if nado else "false", after="код")
                    report.append(f"{'скрыто' if nado else 'открыто'}: {p.relative_to(ROOT)}")
            prof_text = set_fm(prof_text, "набор применён", nabor, after="набор")
            report.append(f"набор «{nabor}» применён")

    # 2. Модули
    nado = spisok(prof.get("модули"))
    if OSNOVA not in nado:
        report.append("⚠ «Основа» не выключается — оставлена в модулях")
        nado = [OSNOVA] + nado
    est = spisok(prof.get("модули включены")) or [OSNOVA]
    for m in nado:
        if m in est or m == OSNOVA:
            continue
        if not (MODULI / m).exists():
            errs.append(f"модуля «{m}» нет в «80 Шаблоны/Модули»")
            continue
        for rel in fayly_modulya(m):
            dst, arh = ROOT / rel, ARHIV / m / rel
            if dst.exists():
                report.append(f"⚠ {rel}: уже есть — оставлен как есть")
            elif arh.exists():
                perenos.append((arh, dst))
            else:
                perenos.append((MODULI / m / "файлы" / rel, dst, "копия"))
        report.append(f"модуль «{m}» включён")
    for m in est:
        if m in nado or m == OSNOVA:
            continue
        for rel in fayly_modulya(m):
            if (ROOT / rel).exists():
                perenos.append((ROOT / rel, ARHIV / m / rel))
        report.append(f"модуль «{m}» выключен — файлы в «90 Архив/Модули/{m}»")
    if nado != est:
        prof_text = set_fm(prof_text, "модули включены", nado, after="набор применён")

    if errs:
        for e in errs:
            print("✖", e)
        print("✖ ничего не записано")
        sys.exit(1)
    for r in report or ["нечего менять"]:
        print(r)
    for x in perenos:
        print(f"   {'копия' if len(x) == 3 else 'перенос'}: {x[0].relative_to(ROOT)} → {x[1].relative_to(ROOT)}")
    if a.proverit:
        print("(проверка — ничего не записано)")
        return
    for p, t in zapis.items():
        p.write_text(t, encoding="utf-8")
    for x in perenos:
        x[1].parent.mkdir(parents=True, exist_ok=True)
        (shutil.copy2 if len(x) == 3 else shutil.move)(x[0], x[1])
    if prof_text != PROFIL.read_text(encoding="utf-8"):
        PROFIL.write_text(prof_text, encoding="utf-8")
    if zapis or perenos:
        print("дальше: python3 .github/scripts/shkala.py --write")


if __name__ == "__main__":
    main()
