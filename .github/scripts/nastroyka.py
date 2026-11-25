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
  • анкета знакомства (страница, экран «Анкета» / «Обо мне») пишет `анкета пройдена` — дату и время. Если она
    не совпадает с `анкета применена`, программа ОДИН раз применяет ответы: `пара: нет` — скрыть луч
    «Совместная жизнь» (06.04), `пара: да` — открыть; `приоритеты` (коды сфер по порядку) — `приоритет` 1–3
    в «NN Шкала» (у остальных сфер снимается; пустой список — ничего не трогать); `страна` — `валюта`
    в «10 Деньги», если она ещё пустая и страна известна. Затем пишет `анкета применена`. Дальше владелец
    меняет всё сам («Время и внимание», «Скрыть луч»), программа не повторяет, пока анкету не пройдут снова.
  • «Мои сферы» (страница, экран «Мои сферы» — «00 Старт/Мои сферы.md»): `заявка` — список поручений строкой
    «ГГГГ-ММ-ДД ЧЧ:ММ:СС · действие · …». Программа выполняет строки новее `заявка выполнена`, по порядку:
      переименовать · NN · Короткое · Полное — папка, оглавление, заголовок, `aliases` и все ссылки на сферу
        (кроме «80 Шаблоны» и «90 Архив»); `код` и номер остаются;
      добавить · Короткое · Полное · Луч; Луч — своя сфера со следующим свободным кодом (13, 14…), общие файлы
        из «80 Шаблоны» (как `new_sphere.py --nova`), лучи с пустыми линейками, место на колесе — последнее;
      луч · NN · Название — новый луч с пустой линейкой; код — следующий свободный (в сферах шаблона 01–12 свои
        лучи — с 51, чтобы не столкнуться с лучами шаблона и модулей);
      порядок · NN, NN, … — `порядок` 1, 2, 3… в оглавлениях по этому списку.
    Что сделано и что нет (с причиной) — строками в раздел «Что сделано» того же файла; `заявка` очищается,
    в `заявка выполнена` — время последней строки. Скрыть и вернуть сферу страница пишет сама (`скрыта`).
  • Ссылки на сферу по коду — при каждом запуске: ссылка или путь со старым названием сферы (из шаблона
    или из «Что сделано») заменяется на нынешнее — так файлы, сделанные из заготовок шаблона («Деньги месяц»,
    ветки, модули), сразу смотрят в переименованную сферу. Модуль раскладывается в папку сферы по коду.
Код выхода: 0 — всё хорошо (или нечего делать), 1 — ошибка (ничего не записано).
"""
import argparse
import datetime
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
MOI = ROOT / "00 Старт" / "Мои сферы.md"
TEMPLATES = ROOT / "80 Шаблоны"
PARA = "06.04"
# Страна → основная валюта (код из трёх букв, как `валюта` в «10 Деньги»). Нет в списке — валюта не ставится.
EVRO = ("испания", "германия", "франция", "италия", "португалия", "нидерланды", "бельгия", "австрия", "ирландия",
        "финляндия", "греция", "словакия", "словения", "эстония", "латвия", "литва", "люксембург", "мальта",
        "кипр", "хорватия", "черногория", "болгария")
VALYUTY = {**{s: "EUR" for s in EVRO}, "россия": "RUB", "беларусь": "BYN", "белоруссия": "BYN", "украина": "UAH",
           "казахстан": "KZT", "узбекистан": "UZS", "кыргызстан": "KGS", "киргизия": "KGS", "таджикистан": "TJS",
           "армения": "AMD", "грузия": "GEL", "азербайджан": "AZN", "молдова": "MDL", "молдавия": "MDL",
           "сша": "USD", "америка": "USD", "великобритания": "GBP", "англия": "GBP", "швейцария": "CHF",
           "польша": "PLN", "чехия": "CZK", "сербия": "RSD", "турция": "TRY", "израиль": "ILS", "оаэ": "AED",
           "таиланд": "THB", "тайланд": "THB", "индонезия": "IDR", "вьетнам": "VND", "китай": "CNY", "япония": "JPY",
           "канада": "CAD", "австралия": "AUD", "мексика": "MXN", "аргентина": "ARS", "бразилия": "BRL",
           "швеция": "SEK", "норвегия": "NOK", "дания": "DKK", "венгрия": "HUF", "румыния": "RON"}
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
    new = [f"{key}:"] + [f'  - "{x}"' for x in value] if isinstance(value, list) else [f"{key}: {value}" if value != "" else f"{key}:"]
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


# ---------- сферы по коду («Мои сферы») ----------

PLOHIE = re.compile(r'[\\/:*?"<>|#^\[\]·;]')
METKA_N, METKA_K = "<!-- sfery: начало -->", "<!-- sfery: конец -->"


def papki_sfer():
    """код сферы → имя папки «NN Название» (код — из оглавления, иначе номер папки)."""
    out = {}
    for d in sorted(x for x in SFERY.iterdir() if x.is_dir() and re.match(r"^\d{2} ", x.name)) if SFERY.exists() else []:
        idx = d / f"{d.name}.md"
        kod = read_fm(idx.read_text(encoding="utf-8")).get("код") if idx.exists() else None
        out[(kod if isinstance(kod, str) and kod else d.name[:2])] = d.name
    return out


def dengi_fayl():
    d = papki_sfer().get("10")
    return SFERY / d / "Деньги" / "10 Деньги.md" if d else None


def v_papku_sfery(rel):
    """Путь из шаблона («10 Сферы/NN Название шаблона/…») — в папку этой сферы в копии (по коду)."""
    parts = Path(rel).parts
    if len(parts) >= 2 and parts[0] == "10 Сферы" and re.match(r"^\d{2} ", parts[1]):
        d = papki_sfer().get(parts[1][:2])
        if d and d != parts[1]:
            rest = list(parts[2:])
            if rest and rest[-1] == f"{parts[1]}.md":
                rest[-1] = f"{d}.md"
            return Path("10 Сферы", d, *rest)
    return Path(rel)


def zamenit_sferu(text, old, new):
    """Ссылки [[NN Старое]], имя в кавычках ("NN Старое" — в таблицах Bases) и пути «10 Сферы/NN Старое» → новое (только точное имя)."""
    text = re.sub(r"\[\[" + re.escape(old) + r"(?=[\]|#])", lambda m: "[[" + new, text)
    text = re.sub(r'(?<=")' + re.escape(old) + r'(?=")', lambda m: new, text)  # file.hasLink("NN Старое") в таблицах
    for o, n in ((f"10 Сферы/{old}", f"10 Сферы/{new}"),
                 (f"10 Сферы/{old}".replace(" ", "%20"), f"10 Сферы/{new}".replace(" ", "%20"))):
        text = re.sub(re.escape(o) + r"""(?=[/"')\]]|$)""", lambda m: n, text, flags=re.M)
    return text


def md_fayly():
    for p in sorted(ROOT.rglob("*.md")):
        rel = p.relative_to(ROOT).parts
        if rel[0] in (".git", "80 Шаблоны", "90 Архив", "node_modules"):
            continue
        yield p


def perepisat(mapping):
    """Заменить старые названия сфер во всех файлах; число изменённых файлов."""
    n = 0
    for p in md_fayly():
        t = p.read_text(encoding="utf-8")
        new = t
        for old, cur in mapping.items():
            if old in new:
                new = zamenit_sferu(new, old, cur)
        if new != t:
            p.write_text(new, encoding="utf-8")
            n += 1
    return n


def istoriya():
    """Строки раздела «Что сделано» файла «Мои сферы»."""
    if not MOI.exists():
        return []
    t = MOI.read_text(encoding="utf-8")
    if METKA_N not in t:
        return []
    return [x for x in t.split(METKA_N, 1)[1].split(METKA_K, 1)[0].splitlines() if x.strip()]


def starye_imena():
    """Старое имя папки сферы → нынешнее: названия шаблона и переименования из «Что сделано»."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from new_sphere import OSNOVA
    except Exception:
        OSNOVA = []
    est = papki_sfer()
    out = {}
    imena = [(k, f"{k} {s}") for k, s, _ in OSNOVA]
    for line in istoriya():
        m = re.search(r"переименовано: (\d{2} [^→]+?) → (\d{2} .+?)(?: \(|$)", line)
        if m:
            imena.append((m.group(1)[:2], m.group(1).strip()))
    for kod, old in imena:
        cur = est.get(kod)
        if cur and old != cur and not (SFERY / old).exists():
            out[old] = cur
    return out


def chistoe_imya(s, chto, dlina=40):
    s = (s or "").strip()
    if not s:
        return None, f"пустое {chto}"
    if len(s) > dlina:
        return None, f"{chto} длиннее {dlina} знаков"
    if PLOHIE.search(s) or s.startswith(".") or s.endswith("."):
        return None, f"{chto} «{s}»: нельзя знаки \\ / : * ? \" < > | # ^ [ ] · ; и точку в начале или конце"
    return s, None


def svobodnyy_kod_lucha(nn, papka):
    zanyato = set()
    for p in list((SFERY / papka / "Шкала").glob("*.md")) + list(MODULI.glob(f"*/файлы/10 Сферы/{nn} */Шкала/*.md")):
        k = read_fm(p.read_text(encoding="utf-8")).get("код")
        if isinstance(k, str) and re.match(rf"^{nn}\.\d\d$", k):
            zanyato.add(int(k[3:]))
    start = 51 if int(nn) <= 12 else 1
    n = max([x for x in zanyato if x >= start] + [start - 1]) + 1
    return f"{nn}.{n:02d}" if n <= 99 else None


def novyy_luch(nn, papka, name, today):
    """Файл луча с пустой линейкой из «Шаблон — Луч» и строка в «NN Шкала». Возвращает (путь, ошибка)."""
    name, err = chistoe_imya(name, "название луча", 60)
    if err:
        return None, err
    f = SFERY / papka / "Шкала" / f"{nn} Луч — {name}.md"
    if f.exists():
        return None, f"луч «{name}» в сфере {papka} уже есть"
    kod = svobodnyy_kod_lucha(nn, papka)
    if not kod:
        return None, f"в сфере {papka} нет свободного кода луча"
    full = (re.search(r"^# (.+)$", (SFERY / papka / f"{papka}.md").read_text(encoding="utf-8"), re.M) or [None, papka[3:]])[1]
    t = (TEMPLATES / "Шаблон — Луч.md").read_text(encoding="utf-8")
    t = t.replace("{{NN}}", nn).replace("{{Сфера}}", papka[3:]).replace("{{Полное}}", full).replace("{{date}}", today)
    t = t.replace(f'код: "{nn}.__"', f'код: "{kod}"').replace("Название луча", name)
    f.parent.mkdir(parents=True, exist_ok=True)
    (f.parent / ".gitkeep").unlink(missing_ok=True)
    f.write_text(t, encoding="utf-8")
    sc = SFERY / papka / f"{nn} Шкала.md"
    if sc.exists():
        st = sc.read_text(encoding="utf-8")
        link = f"[[{nn} Луч — {name}]]"
        if "## Лучи" in st and link not in st:
            head, tail = st.split("## Лучи", 1)
            lines = tail.split("\n")
            nums = [i for i, ln in enumerate(lines) if re.match(r"^\d+\.\s*", ln)]
            if nums and re.match(r"^\d+\.\s*$", lines[nums[-1]]):  # пустая заготовка «1. »
                lines[nums[-1]] = f"{len(nums)}. {link}"
            elif nums:
                lines.insert(nums[-1] + 1, f"{len(nums) + 1}. {link}")
            else:
                lines.insert(1, f"\n1. {link}")
            sc.write_text(head + "## Лучи" + "\n".join(lines), encoding="utf-8")
    return f, None


def moi_sfery(proverit):
    """Выполнить новые строки `заявка` файла «Мои сферы». Возвращает строки отчёта."""
    if not MOI.exists():
        return []
    text = MOI.read_text(encoding="utf-8")
    fm = read_fm(text)
    zayavka = spisok(fm.get("заявка"))
    sdelano = fm.get("заявка выполнена") or ""
    sdelano = sdelano if isinstance(sdelano, str) else ""
    novye = [z for z in zayavka if z.split(" · ", 1)[0].strip() > sdelano]
    if not zayavka:
        return []
    report, hist = [], []
    today = datetime.date.today().isoformat()
    for z in novye:
        parts = [x.strip() for x in z.split(" · ")]
        kogda, deystvie, polya = parts[0], (parts[1] if len(parts) > 1 else ""), parts[2:]
        if proverit:
            report.append(f"«Мои сферы»: будет выполнено — {' · '.join(parts[1:])}")
            continue
        est = papki_sfer()
        res = None
        try:
            if deystvie == "переименовать" and len(polya) >= 2:
                kod, short, full = polya[0], polya[1], (polya[2] if len(polya) > 2 else "") or polya[1]
                short, e1 = chistoe_imya(short, "короткое название")
                full, e2 = chistoe_imya(full, "полное название", 80)
                old = est.get(kod)
                if e1 or e2:
                    res = f"не сделано: {e1 or e2}"
                elif not old:
                    res = f"не сделано: сферы с кодом {kod} нет"
                else:
                    new = f"{old[:2]} {short}"
                    if new != old and (SFERY / new).exists():
                        res = f"не сделано: папка «{new}» уже есть"
                    else:
                        if new != old:
                            shutil.move(SFERY / old, SFERY / new)
                            (SFERY / new / f"{old}.md").rename(SFERY / new / f"{new}.md")
                        idx = SFERY / new / f"{new}.md"
                        t = idx.read_text(encoding="utf-8")
                        t = set_fm(t, "aliases", [full], after="скрыта")
                        t = re.sub(r"^# .+$", f"# {full}", t, count=1, flags=re.M)
                        t = set_fm(t, "обновлено", today)
                        idx.write_text(t, encoding="utf-8")
                        n = perepisat({old: new}) if new != old else 0
                        res = (f"переименовано: {old} → {new} (полное: {full}; ссылки поправлены в {n} файлах)"
                               if new != old else f"полное название сферы {old}: {full}")
            elif deystvie == "добавить" and polya:
                short, e1 = chistoe_imya(polya[0], "короткое название")
                full, e2 = chistoe_imya((polya[1] if len(polya) > 1 else "") or polya[0], "полное название", 80)
                luchi = [x.strip() for x in (polya[2] if len(polya) > 2 else "").split(";") if x.strip()]
                kody = [int(k) for k in est if k.isdigit()]
                nn = f"{max(kody + [12]) + 1:02d}"
                if e1 or e2:
                    res = f"не сделано: {e1 or e2}"
                elif not luchi:
                    res = "не сделано: нужен хотя бы один луч"
                elif len(luchi) > 12:
                    res = "не сделано: больше 12 лучей — начните с главных, остальные добавьте потом"
                elif int(nn) > 99:
                    res = "не сделано: свободных кодов сфер нет"
                elif any(v[3:].lower() == short.lower() for v in est.values()):
                    res = f"не сделано: сфера «{short}» уже есть"
                else:
                    bad = [e for e in (chistoe_imya(x, "название луча", 60)[1] for x in luchi) if e]
                    if bad:
                        res = f"не сделано: {bad[0]}"
                    else:
                        sys.path.insert(0, str(Path(__file__).resolve().parent))
                        import new_sphere
                        new_sphere.build_sphere(nn, short, full, today, [])
                        papka = f"{nn} {short}"
                        idx = SFERY / papka / f"{papka}.md"
                        pory = []
                        for d in est.values():
                            o = read_fm((SFERY / d / f"{d}.md").read_text(encoding="utf-8")).get("порядок") if (SFERY / d / f"{d}.md").exists() else None
                            if isinstance(o, str) and o.isdigit():
                                pory.append(int(o))
                        idx.write_text(set_fm(idx.read_text(encoding="utf-8"), "порядок", str(max(pory + [0]) + 1)), encoding="utf-8")
                        sdel = [novyy_luch(nn, papka, x, today) for x in luchi]
                        oshibki = [e for _, e in sdel if e]
                        res = f"добавлена сфера {papka} (полное: {full}), лучей: {len(luchi) - len(oshibki)}" + (
                            f"; не добавлены: {'; '.join(oshibki)}" if oshibki else "")
            elif deystvie == "луч" and len(polya) >= 2:
                papka = est.get(polya[0])
                if not papka:
                    res = f"не сделано: сферы с кодом {polya[0]} нет"
                else:
                    f, e = novyy_luch(papka[:2], papka, polya[1], today)
                    res = f"не сделано: {e}" if e else f"добавлен луч {f.stem} в сфере {papka}"
            elif deystvie == "порядок" and polya:
                kody = [k.strip() for k in polya[0].split(",") if k.strip()]
                ostalnye = [k for k in sorted(est) if k not in kody]
                izm = 0
                for i, k in enumerate([k for k in kody if k in est] + ostalnye, 1):
                    idx = SFERY / est[k] / f"{est[k]}.md"
                    if not idx.exists():
                        continue
                    t = idx.read_text(encoding="utf-8")
                    if read_fm(t).get("порядок") != str(i):
                        idx.write_text(set_fm(set_fm(t, "порядок", str(i), after="код"), "обновлено", today), encoding="utf-8")
                        izm += 1
                res = f"порядок на колесе: {', '.join(kody)} (изменено оглавлений: {izm})"
            else:
                res = f"не сделано: непонятное поручение «{' · '.join(parts[1:])}»"
        except OSError as e:
            res = f"не сделано: ошибка файла — {e}"
        hist.append(f"- {kogda} · {res}")
        report.append(f"«Мои сферы»: {res}")
    if proverit:
        return report
    text = MOI.read_text(encoding="utf-8")
    text = set_fm(text, "заявка", [])
    last = max([z.split(" · ", 1)[0].strip() for z in zayavka] + [sdelano])
    text = set_fm(text, "заявка выполнена", f'"{last}"', after="заявка")
    text = set_fm(text, "обновлено", today)
    if METKA_N in text:
        a, b = text.split(METKA_N, 1)
        mid, c = b.split(METKA_K, 1)
        old_lines = [x for x in mid.splitlines() if x.strip()]
        text = a + METKA_N + "\n" + "\n".join(hist[::-1] + old_lines) + "\n" + METKA_K + c
    else:
        text = text.rstrip("\n") + f"\n\n## Что сделано\n\n{METKA_N}\n" + "\n".join(hist[::-1]) + f"\n{METKA_K}\n"
    MOI.write_text(text, encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proverit", action="store_true")
    a = ap.parse_args()
    if not PROFIL.exists():
        sys.exit("✖ нет «00 Старт/Профиль.md»")
    prof_text = PROFIL.read_text(encoding="utf-8")
    prof = read_fm(prof_text)
    zapis, perenos, report, errs = {}, [], [], []

    # 0. «Мои сферы» — переименовать, добавить, луч, порядок (пишется сразу: дальше пути — уже новые)
    report += moi_sfery(a.proverit)

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
            dst, arh = ROOT / v_papku_sfery(rel), ARHIV / m / rel
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
            if (ROOT / v_papku_sfery(rel)).exists():
                perenos.append((ROOT / v_papku_sfery(rel), ARHIV / m / rel))
        report.append(f"модуль «{m}» выключен — файлы в «90 Архив/Модули/{m}»")
    if nado != est:
        prof_text = set_fm(prof_text, "модули включены", nado, after="набор применён")

    # 3. Анкета знакомства — один раз на каждое прохождение
    proyd = prof.get("анкета пройдена") or ""
    if isinstance(proyd, list):
        proyd = proyd[0] if proyd else ""
    if proyd and proyd != (prof.get("анкета применена") or ""):
        para = (prof.get("пара") or "") if not isinstance(prof.get("пара"), list) else ""
        if para in ("да", "нет"):
            for p, tip, kod in shapki():
                if tip == "луч" and kod == PARA:
                    t = zapis.get(p) or p.read_text(encoding="utf-8")
                    nado = "true" if para == "нет" else "false"
                    if (read_fm(t).get("скрыт") or "false") != nado:
                        zapis[p] = set_fm(t, "скрыт", nado, after="код")
                        report.append(f"{'скрыт' if para == 'нет' else 'открыт'} луч «Совместная жизнь» (пара: {para})")
        prio = spisok(prof.get("приоритеты"))[:3]
        if prio:
            for sc in sorted(SFERY.glob("*/[0-9][0-9] Шкала.md")):
                t = zapis.get(sc) or sc.read_text(encoding="utf-8")
                fm = read_fm(t)
                if fm.get("тип") != "шкала":
                    continue
                kod = sc.parent.name[:2]
                idx = sc.parent / f"{sc.parent.name}.md"
                if idx.exists():
                    kod = read_fm(idx.read_text(encoding="utf-8")).get("код") or kod
                nado = str(prio.index(kod) + 1) if kod in prio else ""
                cur = fm.get("приоритет") or ""
                if (cur if not isinstance(cur, list) else "") != nado:
                    zapis[sc] = set_fm(t, "приоритет", nado, after="важность")
                    report.append(f"приоритет {nado or 'снят'}: {sc.relative_to(ROOT)}")
        strana = (prof.get("страна") or "") if not isinstance(prof.get("страна"), list) else ""
        val = VALYUTY.get(strana.strip().lower().replace("ё", "е"))
        DENGI = dengi_fayl()
        if val and DENGI and DENGI.exists():
            t = zapis.get(DENGI) or DENGI.read_text(encoding="utf-8")
            cur = read_fm(t).get("валюта")
            if not cur:
                zapis[DENGI] = set_fm(t, "валюта", val, after="тип")
                report.append(f"валюта {val} ({strana}): {DENGI.relative_to(ROOT)}")
        prof_text = set_fm(prof_text, "анкета применена", f'"{proyd}"', after="анкета пройдена")
        report.append("анкета применена")

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
    # 4. Ссылки на сферы по коду: старые названия (шаблона и прежние свои) → нынешние
    stare = starye_imena()
    if stare:
        n = perepisat(stare)
        if n:
            print(f"ссылки на переименованные сферы поправлены в {n} файлах ({', '.join(f'{o} → {c}' for o, c in stare.items())})")
            zapis = zapis or {"ссылки": 1}
    if zapis or perenos:
        print("дальше: python3 .github/scripts/shkala.py --write")


if __name__ == "__main__":
    main()
