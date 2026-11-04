#!/usr/bin/env python3
"""Деньги — учёт «откуда → куда» (CLAUDE.md, п. 5.2, «10 Деньги»; апгрейд 3.3, 03.11.2026).

Как устроено:
- Файл настроек `тип: деньги` («10 Деньги»): счета, вид бюджета, своя доля в общем, регулярные операции.
- Файл месяца `тип: деньги-месяц` («10 ГГГГ-ММ Деньги»): таблица «Операции» (Дата | Сумма | Откуда | Куда | Что),
  по желанию «Начальные остатки» (с датой) и «Сверка» (Дата | Счёт | По факту).
- Каждая операция — откуда и куда ушли деньги. Концы бывают четырёх видов:
    счёт из настроек            — Кошелёк, Основной банк, Баланс у фирмы…
    «Доход: статья»             — откуда пришли заработанные деньги
    «Расход: статья»            — куда ушли потраченные
    «Возврат: статья»           — деньги, вернувшиеся за расход этой статьи (уменьшают расход)
  Разрешено: Доход → счёт, Возврат → счёт, счёт → Расход, счёт → счёт (перевод: не доход и не расход).
  Пометка «(общее)» или «(партнёра)» в конце статьи — для бюджета пары; без пометки — моё.
- Начальные остатки берутся из самого раннего месяца, где они есть, дальше переносятся из месяца в месяц.
  Операции раньше даты начальных остатков входят в итоги месяца, но не в остатки (они уже в них учтены).
- Сверка: остаток по факту против посчитанного на конец того дня; разница — «неучтено».
- Прогноз: регулярные операции из настроек, которых ещё нет в текущем месяце, и следующие 3 месяца;
  предупреждение, если счёт уходит в минус.
- Валюты (апгрейд 5.1, одобрено 04.11.2026): `валюта` — основная (все итоги в ней; пусто — EUR);
  у счёта в другой валюте — пометка в той же строке «Название: вид · USD»; `курсы` — строки «USD: 0,92 · ГГГГ-ММ-ДД»
  (сколько основной валюты за 1 единицу, с этой даты; новый курс — новая строка). Сумма операции — в валюте счёта;
  перевод между счетами в разных валютах — двумя суммами «100 USD → 92» (сколько ушло → сколько пришло),
  одной суммой — пересчёт по курсу на день операции. Остатки счетов — в их валюте, «Всего» — в основной.

Запуск:
  python3 .github/scripts/dengi.py           — проверка и отчёт, ничего не пишет
  python3 .github/scripts/dengi.py --write   — записать в шапки месяцев `доход`, `расход`, `остатки`, `неучтено`
                                               и раздел «Итоги» между строками-метками
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
KINDS = ("наличные", "банк", "баланс", "долг", "запас")
MARKS = ("общее", "партнёра")
START, END = "<!-- dengi: начало -->", "<!-- dengi: конец -->"
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
          "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
ROW = re.compile(r"^\|(.+)\|\s*$")


def money(x):
    """1234.5 → «1 234,50»; целое — без копеек."""
    s = f"{abs(x):,.2f}".replace(",", " ").replace(".", ",")
    if s.endswith(",00"):
        s = s[:-3]
    return ("−" if x < -0.004 else "") + s


SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "RUB": "₽", "UAH": "₴", "KZT": "₸", "TRY": "₺", "JPY": "¥", "CNY": "¥"}
CUR = re.compile(r"^[A-Z]{3}$")


def to_amount(s):
    s = re.sub(r"[A-Z]{3}", "", s)
    s = s.replace(" ", "").replace("\u00a0", "").replace("\u202f", "").replace("€", "").replace(",", ".")
    return float(s)


def sum_cell(s):
    """«12,50» → (12.5, None, None); «100 USD» → (100, "USD", None); «100 USD → 92» → (100, "USD", 92)."""
    left, _, right = s.partition("→")
    m = re.search(r"\b([A-Z]{3})\b", left)
    return to_amount(left), (m.group(1) if m else None), (to_amount(right) if right.strip() else None)


def to_date(s):
    return datetime.date.fromisoformat(s.strip())


def end_point(s, accounts):
    """Разобрать конец операции → (вид, имя, пометка). Вид: счёт / доход / расход / возврат."""
    s = s.strip()
    mark = ""
    m = re.match(r"^(.*?)\s*\((общее|партнёра)\)\s*$", s)
    if m:
        s, mark = m.group(1).strip(), m.group(2)
    for kind in ("Доход", "Расход", "Возврат"):
        if s.startswith(kind + ":"):
            name = s.split(":", 1)[1].strip()
            return (kind.lower(), name, mark) if name else (None, s, mark)
    if s in accounts and not mark:
        return ("счёт", s, "")
    return (None, s, mark)


def tables(text):
    """Таблицы по разделам «## …»: {заголовок: [строки-списки без шапки]}."""
    out, sec, rows, head = {}, None, [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if sec:
                out[sec] = rows
            sec, rows, head = line[3:].strip(), [], False
            continue
        m = ROW.match(line)
        if sec and m:
            cells = [c.strip() for c in m.group(1).split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                head = True
                continue
            if head:
                rows.append(cells)
    if sec:
        out[sec] = rows
    return out


def find(kind):
    res = []
    for p in sorted(SFERY.rglob("*.md")):
        fm = read_fm(p.read_text(encoding="utf-8"))
        if fm.get("тип") == kind:
            res.append((p, fm))
    return res


def month_add(ym, k):
    y, m = map(int, ym.split("-"))
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--today", help="дата «сегодня» для прогноза (для проверки), ГГГГ-ММ-ДД")
    args = ap.parse_args()
    today = to_date(args.today) if args.today else datetime.date.today()
    errors, warns = [], []

    sets = find("деньги")
    if not sets:
        print("Деньги: файла настроек (тип: деньги) нет — проверять нечего.")
        return 0
    if len(sets) > 1:
        errors.append("✖ файлов настроек (тип: деньги) больше одного: " + ", ".join(p.name for p, _ in sets))
    sp, sfm = sets[0]
    osn = (sfm.get("валюта") or "EUR").strip().upper()
    if not CUR.match(osn):
        errors.append(f"✖ {sp.name}: `валюта` — код из трёх латинских букв (EUR, USD, RUB…)")
        osn = "EUR"
    accounts, acur = {}, {}
    for line in sfm.get("счета") or []:
        if ":" not in line:
            errors.append(f"✖ {sp.name}: счёт «{line}» — нужно «Название: вид»")
            continue
        name, kind = (x.strip() for x in line.rsplit(":", 1))
        cur = osn
        if "·" in kind:
            kind, cur = (x.strip() for x in kind.split("·", 1))
            cur = cur.upper()
            if not CUR.match(cur):
                errors.append(f"✖ {sp.name}: счёт «{name}» — валюта «{cur}», нужен код из трёх латинских букв")
                cur = osn
        if kind not in KINDS:
            errors.append(f"✖ {sp.name}: счёт «{name}» — вид «{kind}», а можно: {', '.join(KINDS)}")
        accounts[name] = kind
        acur[name] = cur
    rates = {}   # валюта → [(дата, курс)] по возрастанию даты
    for line in sfm.get("курсы") or []:
        m = re.match(r"^([A-Za-z]{3})\s*:\s*([\d.,\s]+?)\s*(?:·\s*(\d{4}-\d{2}-\d{2}))?$", line.strip())
        if not m:
            errors.append(f"✖ {sp.name}: курс «{line}» — нужно «USD: 0,92 · ГГГГ-ММ-ДД»")
            continue
        try:
            v = to_amount(m.group(2))
        except ValueError:
            errors.append(f"✖ {sp.name}: курс «{line}» — не число")
            continue
        d = to_date(m.group(3)) if m.group(3) else datetime.date(1900, 1, 1)
        rates.setdefault(m.group(1).upper(), []).append((d, v))
    for v in rates.values():
        v.sort()
    for cur in sorted(set(acur.values()) - {osn}):
        if cur not in rates:
            errors.append(f"✖ {sp.name}: для валюты {cur} нет курса в `курсы` («{cur}: 0,92 · ГГГГ-ММ-ДД»)")
    single = set(acur.values()) <= {osn} and not rates
    sym = SYMBOLS.get(osn, osn)

    def rate(cur, d):
        """Сколько основной валюты за 1 единицу cur на день d (последний курс не позже d, иначе самый ранний)."""
        if cur == osn:
            return 1.0
        rs = rates.get(cur)
        if not rs:
            return 1.0
        ok = [v for dd, v in rs if dd <= d]
        return ok[-1] if ok else rs[0][1]

    def money_c(v, cur):
        return money(v) + ("" if cur == osn and single else f" {SYMBOLS.get(cur, cur)}")
    if sfm.get("бюджет") not in ("личный", "общий", "смешанный"):
        errors.append(f"✖ {sp.name}: `бюджет` — личный, общий или смешанный")
    try:
        share = float(str(sfm.get("доля") or "50").replace(",", ".")) / 100
    except ValueError:
        share = 0.5
        errors.append(f"✖ {sp.name}: `доля` — число процентов (моя доля в общих расходах)")
    regular = []
    for line in sfm.get("регулярно") or []:
        m = re.match(r"^(\d{1,2})\s*·\s*([\d.,\s]+)\s*·\s*(.+?)\s*→\s*(.+?)(?:\s*·\s*(.+))?$", line)
        if not m:
            errors.append(f"✖ {sp.name}: регулярно «{line}» — нужно «день · сумма · откуда → куда · что»")
            continue
        regular.append({"day": int(m.group(1)), "sum": to_amount(m.group(2)), "from": m.group(3),
                        "to": m.group(4), "what": m.group(5) or ""})

    months = []
    for p, fm in find("деньги-месяц"):
        ym = fm.get("месяц", "")
        if not re.fullmatch(r"\d{4}-\d{2}", ym):
            errors.append(f"✖ {p.name}: `месяц` — «ГГГГ-ММ»")
            continue
        months.append((ym, p, fm))
    months.sort()

    def check_op(where, d, s, f, t, what, ym):
        try:
            d = to_date(d)
        except ValueError:
            errors.append(f"✖ {where}: дата «{d}» — нужно ГГГГ-ММ-ДД")
            return None
        if ym and d.strftime("%Y-%m") != ym:
            errors.append(f"✖ {where}: дата {d} не из месяца {ym}")
        raw_s = s
        try:
            s, scur, s2 = sum_cell(str(s))
        except ValueError:
            errors.append(f"✖ {where}: сумма «{raw_s}» — не число")
            return None
        if s <= 0 or (s2 is not None and s2 <= 0):
            errors.append(f"✖ {where}: сумма должна быть больше нуля")
        fe, te = end_point(f, accounts), end_point(t, accounts)
        ok = {("доход", "счёт"), ("возврат", "счёт"), ("счёт", "расход"), ("счёт", "счёт")}
        for e, raw in ((fe, f), (te, t)):
            if e[0] is None:
                errors.append(f"✖ {where}: «{raw}» — нет такого счёта в настройках и не «Доход:/Расход:/Возврат: статья»")
                return None
        if (fe[0], te[0]) not in ok:
            errors.append(f"✖ {where}: {f} → {t} — так нельзя (можно: Доход → счёт, Возврат → счёт, счёт → Расход, счёт → счёт)")
            return None
        if fe == te:
            errors.append(f"✖ {where}: откуда и куда совпадают")
        fcur = acur[fe[1]] if fe[0] == "счёт" else None
        tcur = acur[te[1]] if te[0] == "счёт" else None
        cur = fcur or tcur
        if scur and scur != cur:
            errors.append(f"✖ {where}: сумма в {scur}, а счёт «{fe[1] if fcur else te[1]}» — в {cur} (сумма пишется в валюте счёта)")
            return None
        if s2 is not None and not (fcur and tcur):
            errors.append(f"✖ {where}: две суммы «→» — только для перевода между счетами в разных валютах")
            return None
        s_to = s
        if fcur and tcur and fcur != tcur:
            s_to = s2 if s2 is not None else s * rate(fcur, d) / rate(tcur, d)
        return {"date": d, "sum": s, "sum_to": s_to, "osn": s * rate(cur, d), "from": fe, "to": te, "what": what}

    for r in regular:
        r["op"] = check_op(f"{sp.name}, регулярно", today.isoformat(),
                           str(r["sum"]), r["from"], r["to"], r["what"], None)

    bal = None          # остатки на текущий момент
    opened = None       # дата начальных остатков
    report = {}
    for ym, p, fm in months:
        text = p.read_text(encoding="utf-8")
        tb = tables(text)
        start_rows = tb.get("Начальные остатки")
        if start_rows is not None and bal is None:
            m = re.search(r"^На:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
            if not m:
                errors.append(f"✖ {p.name}: в «Начальных остатках» нет строки «На: ГГГГ-ММ-ДД»")
                opened = datetime.date.fromisoformat(ym + "-01")
            else:
                opened = to_date(m.group(1))
            bal = {k: 0.0 for k in accounts}
            for row in start_rows:
                if len(row) < 2 or not row[0]:
                    continue
                if row[0] not in accounts:
                    errors.append(f"✖ {p.name}: начальный остаток — счёта «{row[0]}» нет в настройках")
                    continue
                try:
                    bal[row[0]] = to_amount(row[1])
                except ValueError:
                    errors.append(f"✖ {p.name}: начальный остаток «{row[0]}» — не число")
        if bal is None:
            errors.append(f"✖ {p.name}: нет начальных остатков ни в этом, ни в более раннем месяце")
            continue
        start = dict(bal)
        inc, exp, ret, shared = {}, {}, {}, {}
        ops = []
        for i, row in enumerate(tb.get("Операции", []), 1):
            row = (row + [""] * 5)[:5]
            if not any(row):
                continue
            op = check_op(f"{p.name}, операция {i}", *row, ym)
            if op:
                ops.append(op)
        ops.sort(key=lambda o: o["date"])
        checks = []
        for i, row in enumerate(tb.get("Сверка", []), 1):
            row = (row + [""] * 3)[:3]
            if not any(row):
                continue
            try:
                checks.append((to_date(row[0]), row[1], to_amount(row[2])))
            except ValueError:
                errors.append(f"✖ {p.name}, сверка {i}: нужна дата ГГГГ-ММ-ДД и сумма числом")
                continue
            if row[1] not in accounts:
                errors.append(f"✖ {p.name}, сверка {i}: счёта «{row[1]}» нет в настройках")
        checks.sort()
        diffs = []
        ci = 0

        def run_checks(upto):
            nonlocal ci
            while ci < len(checks) and (upto is None or checks[ci][0] < upto):
                d, acc, fact = checks[ci]
                if acc in bal:
                    diff = fact - bal[acc]
                    if abs(diff) > 0.004:
                        diffs.append((d, acc, diff))
                        bal[acc] = fact  # дальше считаем от фактического остатка
                ci += 1

        for op in ops:
            run_checks(op["date"])
            s, (fk, fn, fmk), (tk, tn, tmk) = op["osn"], op["from"], op["to"]
            if fk == "доход":
                key = fn + (f" ({fmk})" if fmk else "")
                inc[key] = inc.get(key, 0) + s
            if fk == "возврат":
                key = fn + (f" ({fmk})" if fmk else "")
                ret[key] = ret.get(key, 0) + s
            if tk == "расход":
                key = tn + (f" ({tmk})" if tmk else "")
                exp[key] = exp.get(key, 0) + s
                if tmk == "общее":
                    shared[tn] = shared.get(tn, 0) + s
            if op["date"] >= (opened or op["date"]):
                if fk == "счёт":
                    bal[fn] -= op["sum"]
                if tk == "счёт":
                    bal[tn] += op["sum_to"]
        run_checks(None)
        for k, v in ret.items():
            exp[k] = exp.get(k, 0) - v
        for d, acc, diff in diffs:
            b = diff * rate(acur[acc], d)
            if b < 0:
                exp[f"неучтённое ({acc})"] = exp.get(f"неучтённое ({acc})", 0) - b
            else:
                inc[f"неучтённое ({acc})"] = inc.get(f"неучтённое ({acc})", 0) + b
        report[ym] = {"p": p, "start": start, "end": dict(bal), "inc": inc, "exp": exp,
                      "shared": shared, "diffs": diffs, "ops": ops}

    # ---------- прогноз ----------
    forecast = []
    if report and regular:
        last = max(report)
        cur = today.strftime("%Y-%m")
        base = month_add(last, 1) if last < cur else last
        fb = dict(report[last]["end"])
        for k in range(0, 4):
            ym = month_add(base, k)
            for r in regular:
                if not r["op"]:
                    continue
                if ym == last and ym in report:
                    done = any(o["from"][1] == r["op"]["from"][1] and o["to"][1] == r["op"]["to"][1]
                               and abs(o["sum"] - r["sum"]) < 0.005 for o in report[ym]["ops"])
                    if done:
                        continue
                fk, fn, _ = r["op"]["from"]
                tk, tn, _ = r["op"]["to"]
                if fk == "счёт":
                    fb[fn] -= r["op"]["sum"]
                if tk == "счёт":
                    fb[tn] += r["op"]["sum_to"]
            neg = {a: v for a, v in fb.items() if v < -0.004}
            forecast.append((ym, dict(fb), neg))
            for a, v in neg.items():
                warns.append(f"⚠ прогноз: на конец {ym} «{a}» — {money(v)} (не хватает {money(-v)}), "
                             f"если не будет новых поступлений")

    # ---------- вывод ----------
    def block(ym):
        r = report[ym]
        y, m = ym.split("-")
        lines = [START, f"*Посчитано программой `dengi.py` — руками не править.*", ""]
        ti, te = sum(r["inc"].values()), sum(r["exp"].values())
        lines.append(f"**Доход:** {money(ti)} · **Расход:** {money(te)} · **Осталось от месяца:** {money(ti - te)}")
        if r["shared"]:
            sh = sum(r["shared"].values())
            lines.append(f"**Общие расходы:** {money(sh)}, моя доля {round(share * 100)} % — {money(sh * share)}")
        lines.append("")
        for title, d in (("Доходы", r["inc"]), ("Расходы", r["exp"])):
            if d:
                lines.append(f"| {title} | {sym} |")
                lines.append("|---|---|")
                for k, v in sorted(d.items(), key=lambda x: -x[1]):
                    lines.append(f"| {k} | {money(v)} |")
                lines.append("")
        lines.append("| Счёт | Начало | Конец |")
        lines.append("|---|---|---|")
        for acc in accounts:
            c = acur[acc]
            lines.append(f"| {acc} | {money_c(r['start'].get(acc, 0), c)} | {money_c(r['end'].get(acc, 0), c)} |")
        d0, d1 = datetime.date.fromisoformat(ym + "-01"), datetime.date.fromisoformat(month_add(ym, 1) + "-01") - datetime.timedelta(days=1)
        ts = sum(v * rate(acur[a], d0) for a, v in r["start"].items())
        tot = sum(v * rate(acur[a], d1) for a, v in r["end"].items())
        lines.append(f"| **Всего{'' if single else f', {sym}'}** | {money(ts)} | {money(tot)} |")
        if not single:
            used = sorted({acur[a] for a in accounts} - {osn})
            if used:
                lines.append("")
                lines.append("*Курсы на конец месяца: " + ", ".join(f"1 {c} = {money(rate(c, d1))} {sym}" for c in used) + ".*")
        lines.append("")
        if r["diffs"]:
            lines.append("**Сверка:** " + "; ".join(
                f"{d} {a}: {'не записано расходов на' if v < 0 else 'лишние'} {money(abs(v))}" for d, a, v in r["diffs"]))
            lines.append("")
        fc = [f for f in forecast if f[0] >= ym]
        if fc and ym == max(report):
            lines.append("**Прогноз по регулярным операциям** (без новых заработков):")
            lines.append("")
            shown = [a for a in accounts if any(abs(f[1][a]) > 0.004 for f in fc)]
            lines.append("| На конец | " + " | ".join(shown) + " |")
            lines.append("|---|" + "---|" * len(shown))
            for fym, fb, neg in fc:
                yy, mm = fym.split("-")
                lines.append(f"| {MONTHS[int(mm) - 1]} {yy} | " + " | ".join(
                    (f"**{money_c(fb[a], acur[a])}**" if a in neg else money_c(fb[a], acur[a])) for a in shown) + " |")
            lines.append("")
        lines.append(END)
        return lines

    for ym, r in report.items():
        y, m = ym.split("-")
        ti, te = sum(r["inc"].values()), sum(r["exp"].values())
        print(f"{MONTHS[int(m) - 1]} {y}: доход {money(ti)}, расход {money(te)}, "
              f"всего на счетах {money(sum(v * rate(acur[a], today) for a, v in r['end'].items()))}{'' if single else ' ' + osn}")
        if args.write:
            vals = {"доход": money(ti), "расход": money(te),
                    "остатки": [f"{acc}: {money_c(v, acur[acc])}" for acc, v in r["end"].items()],
                    "неучтено": [f"{d} {acc}: {money_c(v, acur[acc])}" for d, acc, v in r["diffs"]]}
            changed = write_fm(r["p"], vals, "месяц")
            text = r["p"].read_text(encoding="utf-8")
            new = "\n".join(block(ym))
            if START in text and END in text:
                text2 = text[:text.index(START)] + new + text[text.index(END) + len(END):]
            else:
                errors.append(f"✖ {r['p'].name}: нет строк-меток раздела «Итоги» ({START} … {END})")
                text2 = text
            if text2 != text:
                r["p"].write_text(text2, encoding="utf-8")
                changed = True
            if changed:
                print(f"  записано: {r['p'].name}")
    for e in errors:
        print(e)
    for w in warns:
        print(w)
    if not errors:
        print(f"Деньги: ошибок нет, месяцев {len(report)}, счетов {len(accounts)}.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
