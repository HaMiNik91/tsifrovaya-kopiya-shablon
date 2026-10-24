#!/usr/bin/env python3
"""Обновление копии «Цифровой копии» из общего шаблона (CLAUDE.md, раздел 12).

Шаблон развивается (правила, программы, страница, линейки лучей), а у владельца копии
есть своё: оценки, свои правки уровней, записи, журнал, люди. Программа переносит в копию
только то, что изменилось в шаблоне, и ничего своего не теряет.

Как работает. Сравниваются три вида каждого файла: «было» — в шаблоне той версии, из которой
копия получила последнее обновление (или из которой создана), «шаблон» — в шаблоне сейчас,
«ваше» — в копии сейчас.
  - Владелец файл не менял → файл просто становится как в шаблоне.
  - Шаблон файл не менял → остаётся как у владельца.
  - Меняли оба → слияние по строкам: изменения шаблона вносятся вокруг правок владельца.
    Если оба изменили одну и ту же строку — остаётся строка владельца, вариант шаблона
    записывается в отчёт.
  - В шапке файла (свойства между ---) слияние идёт по свойствам. Личные свойства
    (оценки, даты, важность, приоритет, часы, замеры и др. — LICHNYE) всегда остаются свои.
    Список `оценки` луча: свои цифры остаются; новая зона из шаблона добавляется с `нет`;
    зона, которой в шаблоне больше нет, убирается, а её цифра попадает в отчёт.
  - Личные места (журнал, люди, Входящие, Записи, Опыт, Путь, Увлечения, Архив,
    «Как со мной работать») не меняются никогда: туда только добавляются новые файлы шаблона.
  - Переименованный в шаблоне файл переносится под новое имя вместе с правками владельца,
    ссылки [[старое имя]] во всех файлах копии исправляются.
  - Файл, удалённый в шаблоне, удаляется, только если владелец его не менял.

Версия шаблона, до которой обновлена копия, хранится в `.github/shablon.json` (`versiya`).
Если её ещё нет, программа находит версию сама: шаблон, из которого сделан первый коммит
копии (кнопка «Use this template» кладёт в него ровно файлы шаблона); не нашла — берёт
последнюю версию шаблона не позже первого коммита копии и пишет об этом в отчёте.

Запуск (из корня копии):
  python3 .github/scripts/obnovlenie.py --proverit          # только показать, что изменится
  python3 .github/scripts/obnovlenie.py                     # обновить файлы (коммит — сами)
Ключи:
  --shablon АДРЕС    откуда брать шаблон: адрес git или папка с клоном (по умолчанию —
                     https://github.com/<shablon из shablon.json>.git; ключ доступа к закрытому
                     шаблону — переменная окружения SHABLON_TOKEN)
  --do ВЕРСИЯ        до какой версии шаблона обновить (по умолчанию — последняя в ветке)
  --ot ВЕРСИЯ        с какой версии шаблона считать «было» (если versiya неверна)
  --bez-workflows    не трогать .github/workflows (встроенному ключу GitHub Actions это
                     запрещено) — такие файлы попадут в отчёт «нужен Claude»
  --otchet ФАЙЛ      записать отчёт ещё и в этот файл (GitHub Actions — в итог запуска)

Отчёт каждого обновления дописывается в «00 Старт/Обновления из шаблона.md».
Код выхода: 0 — всё хорошо, 1 — ошибка, 3 — уже последняя версия.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                           text=True).stdout.strip() or ".").resolve()
NASTROYKA = ".github/shablon.json"
ZHURNAL = "00 Старт/Обновления из шаблона.md"

# Личные места: файлы в них не меняются и не удаляются, только добавляются новые из шаблона.
LICHNYE_PAPKI = ("01 Входящие/", "20 Журнал/", "40 Люди/", "90 Архив/")
LICHNYE_PODPAPKI = ("Входящие", "Записи", "Опыт", "Путь", "Увлечения")  # внутри «10 Сферы/NN …/»
LICHNYE_FAYLY = {"00 Старт/Как со мной работать.md", "00 Старт/Промт для нового чата.md", ZHURNAL}
# Общие файлы: правила, программы, страница, заготовки. Если владелец и шаблон изменили одно
# и то же место, побеждает шаблон (вариант владельца — в отчёте); свои добавления в других
# местах сохраняются. Свои правила владелец держит в «Как со мной работать» (CLAUDE.md, раздел 12).
OBSHCHIE_FAYLY = {"CLAUDE.md", "README.md", "wrangler.jsonc", ".gitignore",
                  "00 Старт/Начни здесь.md", "00 Старт/Как работают связи.md"}
OBSHCHIE_PAPKI = (".github/", "docs/", "worker/", "80 Шаблоны/", ".obsidian/")
# Служебное шаблона, которое в копию не переносится совсем.
NE_PERENOSIT = ("_работа/",)

# Личные свойства шапки: всегда остаются как у владельца.
LICHNYE = {
    "оценки", "оценено", "оценка", "слабый", "сильный", "статус", "обновлено",
    "важность", "приоритет", "часы",
    "замеры", "измерено", "расчёт", "пунктов", "здоров", "отмечено", "проверено", "беспокоит",
    "последнее", "следующее",
    "ступень", "проб", "радость", "компания", "люди", "темы", "настроение", "энергия",
}


def git(*args, cwd=None, check=True, inp=None, binary=False):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd or ROOT,
                       capture_output=True, input=inp, text=not binary)
    if check and r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
        raise SystemExit(f"✖ git {' '.join(args[:3])}: {err.strip()}")
    return r


# ---------- где что лежит ----------

def lichnoe(path):
    if path in LICHNYE_FAYLY or path.startswith(LICHNYE_PAPKI):
        return True
    parts = path.split("/")
    return len(parts) >= 4 and parts[0] == "10 Сферы" and parts[2] in LICHNYE_PODPAPKI


def obshchee(path):
    return path in OBSHCHIE_FAYLY or path.startswith(OBSHCHIE_PAPKI)


def ne_perenosit(path):
    return path == NASTROYKA or path.startswith(NE_PERENOSIT)


def workflow(path):
    return path.startswith(".github/workflows/")


# ---------- шаблон ----------

class Shablon:
    def __init__(self, adres):
        self.dir = Path(tempfile.mkdtemp(prefix="shablon-"))
        token = os.environ.get("SHABLON_TOKEN")
        if token and adres.startswith("https://github.com/"):
            adres = adres.replace("https://", f"https://x-access-token:{token}@", 1)
        r = subprocess.run(["git", "clone", "--bare", "--quiet", "--no-tags", adres, str(self.dir)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            msg = r.stderr.replace(token, "***") if token else r.stderr
            raise SystemExit(f"✖ Не удалось получить шаблон ({msg.strip()}). Если шаблон закрыт — "
                             "нужен ключ SHABLON_TOKEN.")
        self.cache = {}

    def g(self, *args, **kw):
        return git(*args, cwd=self.dir, **kw)

    def rev(self, ref):
        r = self.g("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        return r.stdout.strip() if r.returncode == 0 else None

    def files(self, rev):
        out = self.g("ls-tree", "-r", "-z", rev).stdout
        res = {}
        for item in out.split("\0"):
            if item:
                meta, path = item.split("\t", 1)
                res[path] = meta.split()[2]
        return res

    def blob(self, sha):
        if sha not in self.cache:
            self.cache[sha] = self.g("cat-file", "blob", sha, binary=True).stdout
        return self.cache[sha]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def nayti_bazu(sh, theirs):
    """Версия шаблона, из которой сделана копия: по дереву первого коммита, иначе по дате."""
    roots = git("rev-list", "--max-parents=0", "HEAD").stdout.split()
    hist = sh.g("log", "--format=%H %T %ct", theirs).stdout.split("\n")
    hist = [h.split() for h in hist if h]
    trees = {t: c for c, t, _ in reversed(hist)}
    for root in roots:
        tree = git("rev-parse", f"{root}^{{tree}}").stdout.strip()
        if tree in trees:
            return trees[tree], "по первому коммиту копии"
    ct = int(git("log", "-1", "--format=%ct", roots[-1]).stdout.strip())
    for c, _, t in hist:
        if int(t) <= ct:
            return c, "по дате первого коммита копии (точного совпадения нет — проверьте отчёт)"
    return hist[-1][0], "самая первая версия шаблона (копия старше шаблона?)"


# ---------- слияние ----------

def text(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return None


def split_fm(t):
    if t.startswith("---\n"):
        end = t.find("\n---\n", 4)
        if end != -1:
            return t[4:end + 1], t[end + 5:]
        if t.endswith("\n---"):
            return t[4:len(t) - 3], ""
    return None, t


def parse_fm(fm):
    """Шапка → упорядоченный словарь «свойство → текст (строка свойства и её продолжение)»."""
    keys, cur = {}, None
    for line in fm.splitlines(keepends=True):
        m = re.match(r"^([^\s#\-][^:]*):", line)
        if m:
            cur = m.group(1).strip()
            keys[cur] = line
        elif cur is not None:
            keys[cur] += line
        else:
            keys.setdefault("\0начало", "")
            keys["\0начало"] += line
    return keys


def ocenki_items(block):
    items = []
    for line in block.splitlines()[1:]:
        m = re.match(r'^\s*-\s*"?(.*?)"?\s*$', line)
        if m and ":" in m.group(1):
            name, val = m.group(1).rsplit(":", 1)
            items.append((name.strip(), val.strip()))
    return items


def merge_ocenki(mine, base, theirs, notes, path):
    m, b, t = ocenki_items(mine), ocenki_items(base or "оценки:\n"), ocenki_items(theirs)
    mv, bn, tn = dict(m), {n for n, _ in b}, [n for n, _ in t]
    tv = dict(t)
    res = [(n, mv.get(n, tv[n] if n in tv else "нет")) for n in tn]
    added = [n for n in tn if n not in mv]
    dropped = []
    for n, v in m:
        if n in tv:
            continue
        if n in bn:  # было в шаблоне, теперь нет — зона убрана или переименована
            dropped.append((n, v))
        else:  # своя зона владельца
            res.append((n, v))
    if added:
        notes.append(("новые оценки", path, ", ".join(f"«{n}»" for n in added) + " — добавлены с «нет»"))
    for n, v in dropped:
        hint = ""
        if len(dropped) == 1 and len(added) == 1:
            hint = f"; возможно, теперь это «{added[0]}»"
        notes.append(("снятые оценки", path, f"«{n}: {v}» — такой зоны в шаблоне больше нет{hint}"))
    head = mine.splitlines()[0] if mine else "оценки:"
    return head + "\n" + "".join(f'  - "{n}: {v}"\n' for n, v in res)


def merge_fm(mine, base, theirs, notes, path):
    M, B, T = parse_fm(mine), parse_fm(base or ""), parse_fm(theirs)
    out = {}
    for k, tval in T.items():
        if k in M:
            mval, bval = M[k], B.get(k)
            if k == "оценки":
                out[k] = merge_ocenki(mval, bval, tval, notes, path)
            elif k in LICHNYE or mval == tval or tval == bval:
                out[k] = mval
            elif mval == bval:
                out[k] = tval
            else:
                out[k] = mval
                notes.append(("оставлено ваше", path, f"свойство «{k}»: в шаблоне — {tval.strip()}"))
        elif k not in B:
            out[k] = tval  # новое свойство шаблона
    for k, mval in M.items():
        if k in out:
            continue
        if k in B and k not in T:
            if mval == B[k]:
                continue  # шаблон убрал свойство, владелец его не менял
            notes.append(("оставлено ваше", path, f"свойство «{k}» убрано из шаблона, у вас оно изменено — оставлено"))
        out[k] = mval
    return "".join(out.values())


def merge_text(mine, base, theirs, notes, path):
    shablon_glavnee = obshchee(path)
    with tempfile.TemporaryDirectory() as d:
        f = {}
        for name, t in (("ваше", mine), ("было", base), ("шаблон", theirs)):
            f[name] = Path(d, name)
            f[name].write_text(t, encoding="utf-8")
        args = ["merge-file", "-p", "-L", "ваше", "-L", "было", "-L", "шаблон",
                str(f["ваше"]), str(f["было"]), str(f["шаблон"])]
        r = git(*args, check=False)
        if r.returncode == 0:
            return r.stdout
        if r.returncode < 0 or r.returncode > 127:
            raise SystemExit(f"✖ git merge-file: {r.stderr}")
        for blk in re.findall(r"^<<<<<<< ваше\n(.*?)^=======\n(.*?)^>>>>>>> шаблон\n",
                              r.stdout, re.S | re.M):
            yours, tmpl = (x.strip() or "(пусто)" for x in blk)
            if shablon_glavnee:
                notes.append(("взято из шаблона", path, f"было у вас: {kratko(yours)} · стало: {kratko(tmpl)}"))
            else:
                notes.append(("оставлено ваше", path, f"у вас: {kratko(yours)} · в шаблоне: {kratko(tmpl)}"))
        side = "--theirs" if shablon_glavnee else "--ours"
        return git(*args[:1], side, *args[1:], check=False).stdout


def kratko(s, n=300):
    s = " ⏎ ".join(x.strip() for x in s.splitlines() if x.strip())
    return s if len(s) <= n else s[:n] + "…"


def merge3(mine, base, theirs, path, notes):
    """Вернуть новое содержимое файла (bytes) или None, если слить нельзя (оставить ваше)."""
    if mine == base or base is None and mine == theirs:
        return theirs
    if theirs == base or mine == theirs:
        return mine
    tm, tb, tt = text(mine), text(base or b""), text(theirs)
    if None in (tm, tb, tt):
        notes.append(("оставлено ваше", path, "файл не текстовый, а изменён и у вас, и в шаблоне"))
        return None
    fm_m, body_m = split_fm(tm)
    fm_b, body_b = split_fm(tb)
    fm_t, body_t = split_fm(tt)
    if fm_m is not None and fm_t is not None and path.endswith(".md"):
        fm = merge_fm(fm_m, fm_b, fm_t, notes, path)
        body = merge_text(body_m, body_b if fm_b is not None else tb, body_t, notes, path)
        res = "---\n" + fm + "---\n" + body
        if res != tm:
            res = re.sub(r"^(обновлено:).*$", rf"\1 {dt.date.today().isoformat()}", res, count=1, flags=re.M)
        return res.encode("utf-8")
    return merge_text(tm, tb, tt, notes, path).encode("utf-8")


# ---------- главное ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--shablon")
    ap.add_argument("--do")
    ap.add_argument("--ot")
    ap.add_argument("--proverit", action="store_true")
    ap.add_argument("--bez-workflows", action="store_true")
    ap.add_argument("--otchet")
    a = ap.parse_args()

    cfg_path = ROOT / NASTROYKA
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    repo = cfg.get("shablon", "HaMiNik91/tsifrovaya-kopiya-shablon")
    vetka = cfg.get("vetka", "main")
    if os.environ.get("GITHUB_REPOSITORY", "").lower() == repo.lower():
        print("Это сам шаблон — обновлять нечего.")
        return 0
    if git("status", "--porcelain").stdout.strip() and not a.proverit:
        raise SystemExit("✖ В папке есть несохранённые изменения — сначала коммит или отмена.")

    sh = Shablon(a.shablon or f"https://github.com/{repo}.git")
    try:
        theirs = sh.rev(a.do or vetka) or sh.rev("HEAD")
        if not theirs:
            raise SystemExit(f"✖ В шаблоне нет версии «{a.do or vetka}».")
        # Всегда работает самая новая программа: если в шаблоне она новее — запустить её
        nov = sh.g("show", f"{theirs}:.github/scripts/obnovlenie.py", check=False, binary=True).stdout
        if nov and nov != Path(__file__).read_bytes() and not os.environ.get("OBNOVLENIE_NOVAYA"):
            f = Path(tempfile.mkdtemp(prefix="obnovlenie-"), "obnovlenie.py")
            f.write_bytes(nov)
            args = [x for x in sys.argv[1:]]
            if "--shablon" in args:
                j = args.index("--shablon")
                del args[j:j + 2]
            print("Программа обновления в шаблоне новее — работает новая версия.")
            r = subprocess.run([sys.executable, str(f), *args, "--shablon", str(sh.dir), "--do", theirs],
                               cwd=ROOT, env={**os.environ, "OBNOVLENIE_NOVAYA": "1"})
            shutil.rmtree(f.parent, ignore_errors=True)
            return r.returncode
        if a.ot:
            base, how = sh.rev(a.ot), "указана вручную"
            if not base:
                raise SystemExit(f"✖ В шаблоне нет версии «{a.ot}».")
        elif cfg.get("versiya") and sh.rev(cfg["versiya"]):
            base, how = sh.rev(cfg["versiya"]), "из .github/shablon.json"
        else:
            base, how = nayti_bazu(sh, theirs)
        if base == theirs and not (cfg.get("workflows_ot") and not a.bez_workflows):
            print(f"Копия уже обновлена до последней версии шаблона ({theirs[:7]}).")
            return 3
        return obnovit(a, sh, base, theirs, how, cfg, repo, vetka)
    finally:
        sh.close()


def izmeneniya(sh, ot, do):
    """Список изменений шаблона между двумя версиями: (вид, старый путь, новый путь)."""
    diff = sh.g("diff", "--name-status", "-z", "-M50%", ot, do).stdout.split("\0")
    res, i = [], 0
    while i < len(diff) and diff[i]:
        st = diff[i]
        if st[0] in "RC":
            res.append((st[0], diff[i + 1], diff[i + 2]))
            i += 3
        else:
            res.append((st[0], diff[i + 1], diff[i + 1]))
            i += 2
    return res


def obnovit(a, sh, base, theirs, how, cfg, repo, vetka):
    T = sh.files(theirs)
    # Программы-расписания, которые прошлый запуск в GitHub Actions обновить не смог, считаются
    # от своей версии (workflows_ot), остальное — от versiya.
    wf_ot = cfg.get("workflows_ot")
    if wf_ot and not sh.rev(wf_ot):
        wf_ot = None
    changes = []
    for st, old, new in izmeneniya(sh, base, theirs):
        if not (wf_ot and (workflow(old) or workflow(new))):
            changes.append((st, old, new, base))
    if wf_ot:
        changes += [(st, old, new, wf_ot) for st, old, new in izmeneniya(sh, wf_ot, theirs)
                    if workflow(old) or workflow(new)]
    bases = {b: sh.files(b) for b in {c[3] for c in changes}}

    def local(p):
        f = ROOT / p
        return f.read_bytes() if f.is_file() else None

    writes, deletes, renames = {}, [], []
    log = {k: [] for k in ("заменено", "слито", "добавлено", "удалено", "переименовано")}
    notes, claude = [], []

    def put(path, data, kind):
        if workflow(path) and a.bez_workflows and data != local(path):
            claude.append(path)
            return
        writes[path] = data
        log[kind].append(path)

    for st, old, new, ot in changes:
        if ne_perenosit(new) or ne_perenosit(old):
            continue
        B = bases[ot]
        if st == "C":  # копия файла шаблона под новым именем — для копии это новый файл
            st = "A"
        if st == "R" and local(old) is None and local(new) is not None:
            st = "M"  # уже переименован раньше — слить в новый
        tdata = sh.blob(T[new]) if new in T else None
        bdata = sh.blob(B[old]) if old in B else None
        if st == "A":
            mine = local(new)
            if mine is None:
                put(new, tdata, "добавлено")
            elif mine != tdata:
                notes.append(("оставлено ваше", new, "новый файл шаблона, у вас уже есть свой с таким именем"))
        elif st in ("M", "T"):
            mine = local(new)
            if lichnoe(new):
                continue
            if mine is None:
                notes.append(("пропущено", new, "вы удалили этот файл, а в шаблоне он изменился"))
                continue
            before = len(notes)
            res = merge3(mine, bdata, tdata, new, notes)
            if res is not None and res != mine:
                put(new, res, "заменено" if mine == bdata else "слито")
            elif res is None and len(notes) == before:
                notes.append(("оставлено ваше", new, "слить не удалось"))
        elif st == "D":
            mine = local(old)
            if lichnoe(old) or mine is None:
                continue
            if mine == bdata:
                if workflow(old) and a.bez_workflows:
                    claude.append(old)
                else:
                    deletes.append(old)
                    log["удалено"].append(old)
            else:
                notes.append(("оставлено ваше", old, "в шаблоне файл удалён, у вас он изменён — оставлен"))
        elif st == "R":
            mine = local(old)
            if lichnoe(old) or lichnoe(new):
                if mine is None and local(new) is None and lichnoe(new):
                    put(new, tdata, "добавлено")
                continue
            if local(new) is not None:
                notes.append(("оставлено ваше", new, f"шаблон переименовал «{old}» сюда, но у вас уже есть такой файл"))
                continue
            if mine is None:
                put(new, tdata, "добавлено")
                continue
            res = merge3(mine, bdata, tdata, new, notes)
            if res is None:
                res = mine
            if workflow(new) and a.bez_workflows:
                claude.append(f"{old} → {new}")
                continue
            writes[new] = res
            deletes.append(old)
            renames.append((old, new))
            log["переименовано"].append(f"{old} → {new}")

    # ссылки [[старое имя]] → [[новое имя]] во всех файлах копии
    links = {Path(o).stem: Path(n).stem for o, n in renames
             if o.endswith(".md") and Path(o).stem != Path(n).stem}
    if links:
        pat = re.compile(r"\[\[(" + "|".join(re.escape(k) for k in links) + r")(?=[\]|#])")
        for f in ROOT.rglob("*.md"):
            rel = f.relative_to(ROOT).as_posix()
            if rel.startswith((".git/", "90 Архив/")) or rel in deletes:
                continue
            data = writes.get(rel, f.read_bytes())
            t = text(data)
            if t and pat.search(t):
                writes[rel] = pat.sub(lambda m: "[[" + links[m.group(1)], t).encode("utf-8")
                if rel not in sum(log.values(), []):
                    log["слито"].append(rel + " (ссылки)")

    report = otchet(base, theirs, how, log, notes, claude, repo, sh)
    print(report)
    if a.otchet:
        with open(a.otchet, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    if a.proverit:
        print("\n(Режим проверки: файлы не изменены.)")
        return 0

    for p in deletes:
        (ROOT / p).unlink(missing_ok=True)
        d = (ROOT / p).parent
        while d != ROOT and d.exists() and not any(d.iterdir()):
            d.rmdir()
            d = d.parent
    for p, data in writes.items():
        f = ROOT / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        mode = sh.g("ls-tree", theirs, "--", p).stdout.split()
        if mode and mode[0] == "100755":
            f.chmod(0o755)
    cfg.update({"shablon": repo, "vetka": vetka, "versiya": theirs,
                "obnovleno": dt.date.today().isoformat()})
    if claude:
        # программы-расписания ждут Claude: следующий запуск возьмёт их изменения от этой версии
        cfg["workflows_ot"] = wf_ot or base
    else:
        cfg.pop("workflows_ot", None)
    (ROOT / NASTROYKA).write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    zapisat_zhurnal(report)
    return 0


def otchet(base, theirs, how, log, notes, claude, repo, sh):
    date = sh.g("log", "-1", "--format=%cs", theirs).stdout.strip()
    L = [f"## {dt.date.today().isoformat()} — обновление из шаблона",
         "",
         f"Шаблон {repo}: версия {base[:7]} ({how}) → {theirs[:7]} от {date}.",
         ""]
    counts = ", ".join(f"{k} — {len(v)}" for k, v in log.items() if v) or "изменений в общих файлах нет"
    L.append(f"**Итог:** {counts}.")
    groups = {}
    for kind, path, msg in notes:
        groups.setdefault(kind, []).append(f"- `{path}` — {msg}")
    titles = {
        "снятые оценки": "**Снятые оценки** — зона исчезла из шаблона; поставьте цифру заново, если зона переименована:",
        "оставлено ваше": "**Оставлено ваше** — вы и шаблон изменили одно и то же место; ваш вариант сохранён, вариант шаблона — здесь:",
        "новые оценки": "**Новые зоны** — оцените, когда будет удобно:",
        "взято из шаблона": "**Взято из шаблона** — общий файл, вы и шаблон изменили одно место; стоит версия шаблона, ваш прежний вариант — здесь (если это было ваше правило — его место в «Как со мной работать»):",
        "пропущено": "**Пропущено:**",
    }
    for kind in ("снятые оценки", "оставлено ваше", "взято из шаблона", "новые оценки", "пропущено"):
        if kind in groups:
            L += ["", titles[kind], *groups[kind]]
    if claude:
        L += ["", "**Нужен Claude** — эти программы-расписания встроенный ключ GitHub обновить не может. "
              "Попросите Claude: «обнови копию из шаблона» — программа запомнила, что их нужно обновить:",
              *[f"- `{p}`" for p in claude]]
    files = [f"> - {k}: `{p}`" for k, v in log.items() for p in v]
    if files:
        L += ["", "> [!note]- Список файлов", *files]
    return "\n".join(L) + "\n"


def zapisat_zhurnal(report):
    f = ROOT / ZHURNAL
    today = dt.date.today().isoformat()
    if f.exists():
        t = f.read_text(encoding="utf-8")
        t = re.sub(r"^(обновлено:).*$", rf"\1 {today}", t, count=1, flags=re.M)
    else:
        t = ("---\nтип: справка\nстатус: в работе\n"
             f"обновлено: {today}\n---\n# Обновления из шаблона\n\n"
             "← [[Начни здесь]]\n\n"
             "*Что приходило из общего шаблона и что осталось вашим. Пишет программа `obnovlenie.py` "
             "(CLAUDE.md, раздел 12); новые записи — сверху.*\n")
    head, sep, rest = t.partition("\n## ")
    t = head.rstrip("\n") + "\n\n" + report + ("\n## " + rest if sep else "")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(t, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
