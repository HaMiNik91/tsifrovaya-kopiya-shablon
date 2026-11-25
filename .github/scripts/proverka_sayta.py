#!/usr/bin/env python3
"""Проверка страницы заполнения (docs/) на подменённом GitHub — без сети и без записи в настоящее хранилище.

    python3 .github/scripts/proverka_sayta.py               — все проверки
    python3 .github/scripts/proverka_sayta.py novoe opros   — только названные (имена — функции t_<имя> ниже)
    python3 .github/scripts/proverka_sayta.py --spisok      — список проверок
    python3 .github/scripts/proverka_sayta.py --snimki DIR  — ещё и снимки экранов (телефон 390×844) в папку DIR

Как устроено. Папка docs/ раздаётся местным сервером. Браузер (Chrome через Playwright) открывает страницу
как владелец, вошедший по ключу; все запросы к api.github.com и raw.githubusercontent.com отвечает этот файл
из файлов хранилища (текущая рабочая папка), запись (PUT contents) идёт в память — как коммит. Так проверяется
то, что из песочницы Claude нельзя проверить по-настоящему: запись в хранилище, столкновения, повторы.
Шрифты и прочие адреса отключены. Нужны: pip-пакет playwright и Chrome (/usr/bin/google-chrome) или Chromium
Playwright.

Каждая проверка получает Gh (подменённый GitHub: .files — путь → текст, .commits — список (путь, сообщение))
и открытую страницу; изменить данные до открытия — Sayt(nachalo={путь: текст}).
Код выхода 1 — хоть одна проверка не прошла.
"""
import base64
import hashlib
import http.server
import json
import pathlib
import re
import subprocess
import sys
import threading
import traceback
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OWNER, REPO = "vladelec", "moya-kopiya"
CHROME = "/usr/bin/google-chrome"


def sha_of(text):
    b = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


class Gh:
    """Подменённый GitHub: файлы хранилища в памяти, запись — коммитом в память."""

    def __init__(self, nachalo=None):
        self.shablon = False  # True — хранилище помечено как шаблон (is_template)
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        self.files = {}
        for rel in out.decode("utf-8").split("\0"):
            if rel.endswith(".md") and (ROOT / rel).exists():
                self.files[rel] = (ROOT / rel).read_text(encoding="utf-8")
        for k, v in (nachalo or {}).items():
            if v is None:
                self.files.pop(k, None)
            else:
                self.files[k] = v
        self.commits = []
        self.konflikt = set()   # пути, у которых следующая запись получит 409 (как при пересчёте GitHub Actions)
        self.issues = []

    def by_sha(self, sha):
        return next((t for t in self.files.values() if sha_of(t) == sha), None)

    def answer(self, route, request):
        u = urllib.parse.urlparse(request.url)
        path = urllib.parse.unquote(u.path)
        base = f"/repos/{OWNER}/{REPO}"
        m = request.method

        def ok(data, status=200):
            route.fulfill(status=status, content_type="application/json", body=json.dumps(data, ensure_ascii=False),
                          headers={"Access-Control-Allow-Origin": "*"})

        if m == "OPTIONS":
            return route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
                                                      "Access-Control-Allow-Methods": "GET, PUT, POST"})
        if path == base and m == "GET":
            return ok({"default_branch": "main", "permissions": {"push": True}, "is_template": self.shablon})
        if path.startswith(base + "/git/trees/"):
            return ok({"tree": [{"path": p, "type": "blob", "sha": sha_of(t)} for p, t in sorted(self.files.items())]})
        if path.startswith(base + "/git/blobs/"):
            t = self.by_sha(path.rsplit("/", 1)[1])
            return ok({"content": base64.b64encode(t.encode()).decode(), "sha": sha_of(t)}) if t is not None else ok({"message": "Not Found"}, 404)
        if path.startswith(base + "/contents/"):
            fp = path[len(base + "/contents/"):]
            if m == "GET":
                t = self.files.get(fp)
                return ok({"content": base64.b64encode(t.encode()).decode(), "sha": sha_of(t)}) if t is not None else ok({"message": "Not Found"}, 404)
            if m == "PUT":
                body = json.loads(request.post_data)
                cur = self.files.get(fp)
                if fp in self.konflikt:
                    self.konflikt.discard(fp)
                    return ok({"message": "is at abc but expected def"}, 409)
                if (cur is None and body.get("sha")) or (cur is not None and body.get("sha") != sha_of(cur)):
                    return ok({"message": "sha does not match"}, 409)
                new = base64.b64decode(body["content"]).decode("utf-8")
                self.files[fp] = new
                self.commits.append((fp, body["message"]))
                return ok({"content": {"sha": sha_of(new)}}, 201 if cur is None else 200)
        if path.endswith("/issues") and m == "GET":
            return ok(self.issues)
        return ok({"message": f"не подменено: {m} {path}"}, 404)

    def raw(self, route, request):
        path = urllib.parse.unquote(urllib.parse.urlparse(request.url).path)
        fp = path.split("/", 4)[4] if path.count("/") >= 4 else ""
        t = self.files.get(fp)
        route.fulfill(status=200 if t is not None else 404, body=t or "", headers={"Access-Control-Allow-Origin": "*"})


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def server():
    h = lambda *a, **k: _Quiet(*a, directory=str(DOCS), **k)  # noqa: E731
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class Sayt:
    """Страница, открытая владельцем (вход по ключу) на подменённом GitHub."""

    def __init__(self, ctx, port, nachalo=None, vhod=True, worker=None, anketa=False):
        self.gh = Gh(nachalo)
        self.page = ctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: m.type == "error" and not m.text.startswith("Failed to load resource") and self.errors.append(m.text))
        self.page.route("https://api.github.com/**", self.gh.answer)
        self.page.route("https://raw.githubusercontent.com/**", self.gh.raw)
        self.page.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r, q: r.abort())
        self.page.route(re.compile(r"https://challenges\.cloudflare\.com/.*"), lambda r, q: r.fulfill(
            status=200, content_type="text/javascript",
            body="window.turnstile={render:(el,o)=>{setTimeout(()=>o.callback('proba-turnstile'),10);return 'w1'},reset(){}};"
                 "(window.onTurnstile||function(){})();"))
        self.worker = worker
        self.page.route(f"http://127.0.0.1:{port}/vhod/**", self._vhod)
        self.page.route(re.compile(rf"http://127\.0\.0\.1:{port}/idei.*"), self._vhod)
        if vhod:
            self.page.add_init_script(f"""try{{localStorage.setItem('tk.repo','{OWNER}/{REPO}');
                localStorage.setItem('tk.token','proba');localStorage.setItem('tk.via','key');}}catch(e){{}}""")
            if not anketa:  # анкету уже предлагали — другие проверки начинают с колеса или опросника
                self.page.add_init_script(f"try{{localStorage.setItem('an.{OWNER}/{REPO}.auto','1')}}catch(e){{}}")
        self.base = f"http://127.0.0.1:{port}/index.html"

    def _vhod(self, route, request):
        if self.worker:
            return self.worker(route, request)
        route.fulfill(status=404, body="{}", content_type="application/json")

    def open(self, hash_="#/"):
        self.page.goto(self.base + hash_)
        self.page.wait_for_selector(".head, .note.err, h1", timeout=15000)
        return self

    def ждать(self, cond, timeout=10000, what=""):
        """Ждать, пока cond() верно (опрос из Python: строгие правила CSP страницы запрещают eval в браузере)."""
        import time
        end = time.time() + timeout / 1000
        while time.time() < end:
            try:
                if cond():
                    return
            except Exception:  # noqa: BLE001
                pass
            self.page.wait_for_timeout(50)
        raise AssertionError(f"не дождался: {what or cond}")

    def ждать_текст(self, s, timeout=10000):
        self.ждать(lambda: s.lower() in self.page.inner_text("body").lower(), timeout, f"текст «{s}»")

    def go(self, hash_):
        """Открыть экран заново (полная загрузка — страница читает файлы с подменённого GitHub)."""
        self._n = getattr(self, "_n", 0) + 1
        self.page.goto(f"{self.base}?z={self._n}{hash_}")
        self.ждать(lambda: self.page.locator("#app .center").count() == 0, 15000, "загрузка экрана")

    def click(self, selector_or_text):
        loc = self.page.locator(selector_or_text) if selector_or_text[:1] in "[.#" else self.page.get_by_text(selector_or_text, exact=True)
        loc.first.click()
        self.page.wait_for_timeout(30)

    def ждать_записи(self, n=None, timeout=10000):
        """Дождаться, пока очередь записи пуста (и, если задано, коммитов не меньше n)."""
        pill = lambda: self.page.inner_text("#pill")  # noqa: E731
        self.ждать(lambda: pill() != "" and "Сохраняю" not in pill() and (n is None or len(self.gh.commits) >= n), timeout, "запись")
        if n is not None:
            assert len(self.gh.commits) >= n, f"коммитов {len(self.gh.commits)}, ждали {n}: {self.gh.commits}"

    def programmy(self, *names):
        """Записанное страницей — в пробную копию хранилища, и там запустить программы (без --write): ошибок быть не должно."""
        import shutil
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp(prefix="sayt-")) / "kopiya"
        shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git"))
        for fp, _ in self.gh.commits:
            (d / fp).parent.mkdir(parents=True, exist_ok=True)
            (d / fp).write_text(self.gh.files[fp], encoding="utf-8")
        for n in names:
            r = subprocess.run([sys.executable, str(d / ".github/scripts" / n)], cwd=d, capture_output=True, text=True)
            assert r.returncode == 0 and "✖" not in r.stdout, f"{n}: {r.stdout[-800:]}{r.stderr[-400:]}"
        shutil.rmtree(d.parent)

    def text(self):
        """Текст экрана строчными буквами (часть подписей CSS показывает заглавными)."""
        return self.page.inner_text("#app").lower()

    def snimok(self, d, name):
        if d:
            self.page.screenshot(path=str(pathlib.Path(d) / f"{name}.png"), full_page=True)


def fm_get(text, key):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out, cur = None, False
    for line in (m.group(1) if m else "").split("\n"):
        if cur and re.match(r"^\s+-\s", line):
            out.append(line.split("-", 1)[1].strip().strip('"'))
            continue
        cur = False
        if line.split(":")[0].strip() == key and not line.startswith(" "):
            v = line.split(":", 1)[1].strip()
            if v:
                return v.strip('"')
            out, cur = [], True
    return out


# ───────── Проверки ─────────
LUCH = "10 Сферы/03 Интеллект/Шкала"


def t_osnova(ctx, port, snimki):
    """Колесо, скрытие и возврат луча и сферы, «примерно» снимается оценкой по линейке."""
    g = Gh()
    ray = next(p for p in g.files if p.startswith(LUCH + "/") and len(fm_get(g.files[p], "оценки") or []) == 1)
    t = g.files[ray].replace("точность:\n", "точность: примерно\n", 1) if "\nточность:\n" in g.files[ray] else g.files[ray]
    key = fm_get(t, "оценки")[0].rsplit(":", 1)[0]
    t = t.replace(f'"{key}: нет"', f'"{key}: 5"', 1)
    s = Sayt(ctx, port, {ray: t}).open()
    assert "колесо сфер" in s.text(), "нет колеса"
    s.snimok(snimki, "osnova-koleso")
    s.go("#/03")
    assert "примерно" in s.text(), "в списке лучей нет пометки «примерно»"
    rays = s.page.locator(".rows .row .name").all_inner_texts()
    i = next(k for k, x in enumerate(rays) if x.startswith(fm_get(t, "луч") or key))
    s.go(f"#/03/{i}")
    assert "оценка «примерно»" in s.text()
    s.click(".lv >> nth=3")   # уровень 7
    s.click("Моя оценка — 7")
    s.ждать_записи(1)
    new = s.gh.files[ray]
    assert f'"{key}: 7"' in new, "оценка не записана"
    assert not fm_get(new, "точность"), f"точность не снята: {fm_get(new, 'точность')}"
    s.go(f"#/03/{i}")
    s.click("Скрыть луч — не моё")
    s.ждать_записи(2)
    assert fm_get(s.gh.files[ray], "скрыт") == "true"
    assert "скрытые лучи" in s.text()
    s.page.locator("details summary", has_text="Скрытые лучи").click()
    s.click("Вернуть")
    s.ждать_записи(3)
    assert fm_get(s.gh.files[ray], "скрыт") == "false"
    s.go("#/03")
    s.click("Скрыть сферу — не моё сейчас")
    s.ждать_записи(4)
    idx = "10 Сферы/03 Интеллект/03 Интеллект.md"
    assert fm_get(s.gh.files[idx], "скрыта") == "true"
    assert "скрытые сферы: 1" in s.text()
    s.programmy("shkala.py")
    assert not s.errors, s.errors


def t_novoe(ctx, port, snimki):
    """«Что нового»: версии шаблона, кнопка обновления у старой копии, сделанные пожелания."""
    g = Gh()
    f = "00 Старт/Что нового.md"
    tv = fm_get(g.files[f], "версия")
    s = Sayt(ctx, port)
    s.gh.issues = [{"title": "Тёмная тема на телефоне", "labels": [{"name": "сделано"}]}]
    old = s.gh.files[f]
    # копия отстала: в шаблоне (raw) — нынешний файл, в копии — версия 1.0
    s.page.unroute("https://raw.githubusercontent.com/**")
    s.page.route("https://raw.githubusercontent.com/**", lambda r, q: r.fulfill(status=200, body=old, headers={"Access-Control-Allow-Origin": "*"}))
    s.gh.files[f] = old.replace(f'версия: "{tv}"', 'версия: "1.0"', 1)
    s.page.add_init_script(f"try{{localStorage.setItem('op.{OWNER}/{REPO}.auto','1')}}catch(e){{}}")  # опросник уже предлагали — сразу колесо
    s.open()
    s.ждать_текст("Вышла версия")
    s.go("#/novoe")
    s.ждать_текст("Есть обновление")
    txt = s.text()
    assert f"есть обновление: 1.0 → {tv}" in txt, txt[:300]
    assert "тёмная тема на телефоне" in txt and "ещё нет у вас" in txt
    assert s.page.locator("a.btn.main", has_text="Обновить копию").get_attribute("href").endswith("/actions/workflows/obnovlenie.yml")
    s.snimok(snimki, "novoe")
    assert not s.errors, s.errors


def t_opros(ctx, port, snimki):
    """Опросник: пара и дети, общий вопрос ставит «примерно» лучам без оценки, уточнение кусочком линейки."""
    s = Sayt(ctx, port).open()
    g = s.gh.files
    para = next(p for p, t in g.items() if fm_get(t, "код") == "06.04" and fm_get(t, "тип") == "луч")
    deti = next(p for p, t in g.items() if fm_get(t, "код") == "07.01" and fm_get(t, "тип") == "луч")
    s.ждать_текст("Начать")  # новый человек без оценок попадает в опросник сразу
    assert "#/opros" in s.page.url, s.page.url
    s.snimok(snimki, "opros-start")
    s.click("Начать")
    s.ждать_текст("Есть ли у вас сейчас пара")
    s.click("Нет")
    s.ждать_текст("Есть ли у вас дети")
    assert fm_get(s.gh.files[para], "скрыт") == "true" or s.page.inner_text("#pill"), "пара"
    s.click("Нет")
    s.ждать_текст("Как в целом обстоят дела со здоровьем")
    s.snimok(snimki, "opros-sfera")
    s.click("[data-act='opros:main'][data-v='5']")
    s.ждать_текст("Хватает ли вам сил")
    s.ждать_записи()
    sfera01 = [p for p in s.gh.files if p.startswith("10 Сферы/01 ") and "/Шкала/" in p and fm_get(s.gh.files[p], "тип") == "луч"]
    for p in sfera01:
        t = s.gh.files[p]
        if fm_get(t, "скрыт") == "true":
            continue
        assert all(x.endswith(": 5") for x in fm_get(t, "оценки")), (p, fm_get(t, "оценки"))
        assert fm_get(t, "точность") == "примерно", p
    knopki = s.page.locator("[data-act='opros:bucket']").all_inner_texts()
    assert knopki[0].startswith("Да, бодр") and knopki[2].startswith("Устаю"), knopki  # свои ответы, хорошее — первым
    s.click("[data-act='opros:bucket'][data-v='sre']")
    s.ждать_текст("берите нижний")
    s.snimok(snimki, "opros-kusok")
    s.click("[data-act='opros:lvl'][data-v='6']")
    s.ждать_записи()
    sil = next(p for p in sfera01 if fm_get(s.gh.files[p], "код") == "01.12")
    t = s.gh.files[sil]
    assert fm_get(t, "оценки")[0].endswith(": 6") and not fm_get(t, "точность"), (fm_get(t, "оценки"), fm_get(t, "точность"))
    # уточнение зоны: луч остаётся «примерно»
    s.ждать_текст("Как вы спите")
    s.snimok(snimki, "opros-otvety")
    s.click("[data-act='opros:bucket'][data-v='hor']")
    s.click("[data-act='opros:lvl'][data-v='8']")
    s.ждать_записи()
    son = next(p for p in sfera01 if fm_get(s.gh.files[p], "код") == "01.07")
    assert "Сон: 8" in " ".join(fm_get(s.gh.files[son], "оценки")) and fm_get(s.gh.files[son], "точность") == "примерно"
    assert fm_get(s.gh.files[para], "скрыт") == "true", "без пары луч 06.04 не скрыт"
    # сфера 06 без пары: запасной вариант вопросов
    for _ in range(40):
        if "· 06 " in s.page.inner_text(".sub") and s.page.locator("[data-act='opros:main']").count():
            break
        s.click("Пропустить")
    assert "без пары" in s.text(), s.text()[:200]
    s.snimok(snimki, "opros-bez-pary")
    s.click("Пропустить")
    s.ждать_текст("Готовы ли вы к отношениям сейчас")
    s.click("Пропустить")
    s.click("Пропустить")
    s.ждать_текст("Вспомните последние отношения")
    # дошли до сферы 07: общий ответ не трогает «Свои дети»
    for _ in range(40):
        if "· 07 семья" in s.page.inner_text(".sub").lower() and s.page.locator("[data-act='opros:main']").count():
            break
        s.click("Пропустить")
    else:
        raise AssertionError("не дошёл до сферы 07: " + s.text()[:200])
    s.click("[data-act='opros:main'][data-v='7']")
    s.ждать_записи()
    oc = fm_get(s.gh.files[deti], "оценки")
    assert "Свои дети: нет" in oc and "Готовность: 7" in oc, oc
    # признаки «Мама» / «Папа» — по отдельности, «нет такого человека»
    s.ждать_текст("— Мама")
    s.click("Нет такого человека")
    s.ждать_текст("— Папа")
    assert "сфера 7 из 12" in s.page.inner_text(".sub").lower(), s.page.inner_text(".sub")
    s.ждать_записи()
    s.programmy("shkala.py", "oprosnik.py", "sled_shag.py")
    assert not s.errors, s.errors
    s.snimok(snimki, "opros-priznak")


PROFIL = "00 Старт/Профиль.md"


def nastroyka_v_gh(gh):
    """Как GitHub Actions после коммита «Профиля»: nastroyka.py в пробной копии, изменения — в подменённый GitHub."""
    import shutil
    d = kopiya({PROFIL: gh.files[PROFIL]})
    r = subprocess.run([sys.executable, str(d / ".github/scripts/nastroyka.py")], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for f in d.rglob("*.md"):
        rel = str(f.relative_to(d))
        if rel.startswith(".git"):
            continue
        text = f.read_text(encoding="utf-8")
        if gh.files.get(rel) != text and (rel in gh.files or not rel.startswith("80 Шаблоны/")):
            gh.files[rel] = text
    shutil.rmtree(d.parent)
    return r.stdout


def t_anketa(ctx, port, snimki):
    """Анкета при первом входе: ответы → «Профиль» одним коммитом → nastroyka.py → опросник с вопросами модуля; «Обо мне»."""
    s = Sayt(ctx, port, anketa=True).open()
    s.ждать_текст("Давайте познакомимся")
    assert "#/anketa" in s.page.url, s.page.url
    s.snimok(snimki, "anketa-start")
    s.click("Начать")
    s.page.fill("[data-an='imya']", "Анна")
    s.click("Дальше")
    s.ждать_текст("Ваш год рождения")
    s.page.fill("[data-an='god']", "1990")
    s.click("Дальше")
    s.click("Женский")
    s.ждать_текст("Хотите отмечать месячный цикл")
    s.click("Да")
    s.page.fill("[data-an='strana']", "Германия")
    s.click("Дальше")
    s.ждать_текст("Есть ли у вас сейчас пара")
    s.click("Нет")
    s.ждать_текст("Есть ли у вас дети")
    s.click("Нет")
    s.ждать_текст("домашние животные")
    s.click("Есть")
    s.ждать_текст("ограничения по здоровью")
    s.click("Есть")
    s.ждать_текст("Чем вы сейчас живёте")
    s.click("Работа")
    s.ждать_текст("Сколько часов в неделю")
    s.click("3 ч")
    s.ждать_текст("большое событие")
    s.click("Переезд")
    s.ждать_текст("С чего начать")
    s.click("6 главных сфер, остальные потом")
    s.ждать_текст("важнее всего")
    names = s.page.locator("[data-act='anketa:prio']").all_inner_texts()
    assert len(names) == 6 and not any("Духовность" in x for x in names), names  # «Лёгкий старт» — 6 сфер
    s.click("[data-act='anketa:prio'][data-v='10']")
    s.click("[data-act='anketa:prio'][data-v='01']")
    s.snimok(snimki, "anketa-prio")
    s.click("Дальше")
    s.ждать_текст("вот что мы настроим")
    txt = s.text()
    for need in ("включится модуль «питомцы»", "включится модуль «цикл»", "скроются сферы", "скроется луч «совместная жизнь»",
                 "в приоритете: 1 — финансы, 2 — здоровье и молодость", "германия", "посоветуйтесь с врачом", "ветку «переезд»"):
        assert need in txt, (need, txt[:900])
    s.snimok(snimki, "anketa-itog")
    s.click("Всё верно")
    s.ждать_записи(1)
    assert len(s.gh.commits) == 1 and s.gh.commits[0][0] == PROFIL, s.gh.commits
    pr = s.gh.files[PROFIL]
    for k, v in (("имя", "Анна"), ("год рождения", "1990"), ("пол", "женский"), ("страна", "Германия"), ("пара", "нет"), ("дети", "нет"),
                 ("ограничения здоровья", "да"), ("этап жизни", "работа"), ("часов в неделю", "3"), ("событие", "переезд"), ("набор", "Лёгкий старт")):
        assert fm_get(pr, k) == v, (k, fm_get(pr, k))
    assert fm_get(pr, "приоритеты") == ["10", "01"] and fm_get(pr, "модули") == ["Основа", "Питомцы", "Цикл"], (fm_get(pr, "приоритеты"), fm_get(pr, "модули"))
    assert fm_get(pr, "анкета пройдена"), "нет «анкета пройдена»"
    s.ждать_текст("Настраиваю копию")
    out = nastroyka_v_gh(s.gh)   # «GitHub Actions»
    for need in ("модуль «Питомцы» включён", "модуль «Цикл» включён", "скрыт луч «Совместная жизнь»", "приоритет 1", "валюта EUR", "анкета применена"):
        assert need in out, (need, out)
    s.ждать(lambda: "#/opros" in s.page.url and "Начать" in s.page.inner_text("#app"), 30000, "переход к опроснику")
    s.click("Начать")
    s.ждать_текст("Как в целом обстоят дела со здоровьем")   # пара и дети уже в «Профиле» — опросник их не спрашивает
    for _ in range(12):
        if "модуль ·" in s.text():
            break
        s.click("Пропустить")
    assert "модуль · луч «цикл»" in s.text() and "знаю свой цикл" in s.text(), s.text()[:300]
    s.snimok(snimki, "anketa-modul")
    s.click("[data-act='opros:bucket'][data-v='hor']")
    s.click("[data-act='opros:lvl'][data-v='8']")
    s.ждать_записи()
    cikl = next(p for p, t in s.gh.files.items() if fm_get(t, "код") == "01.13" and p.startswith("10 Сферы/"))
    assert "Знаю свой цикл: 8" in fm_get(s.gh.files[cikl], "оценки"), fm_get(s.gh.files[cikl], "оценки")
    # колесо здоровается; у физического луча — напоминание; «Следующий шаг» подсказывает ветку
    s.go("#/")
    s.ждать_текст("Здравствуйте, Анна")
    assert "обо мне" in s.text()
    sila = next(p for p, t in s.gh.files.items() if fm_get(t, "код") == "01.06")
    s.go("#/01")
    i = next(k for k, x in enumerate(s.page.locator(".rows .row .name").all_inner_texts()) if x.startswith(fm_get(s.gh.files[sila], "луч")))
    s.go(f"#/01/{i}")
    s.ждать_текст("Сначала посоветуйтесь с врачом")
    s.go("#/shag")
    s.ждать_текст("Впереди: переезд")
    # «Обо мне»: прежние ответы на месте, повторный проход не трогает модули
    s.go("#/anketa")
    s.ждать_текст("Обо мне")
    s.click("Пройти")
    assert s.page.input_value("[data-an='imya']") == "Анна"
    n = len(s.gh.commits)
    for _ in range(20):
        if "вот что мы настроим" in s.text():
            break
        if s.page.locator("[data-act='anketa:txt']").count():
            s.click("[data-act='anketa:txt']")
        else:
            s.click("Пропустить") if s.page.get_by_text("Пропустить", exact=True).count() else s.click("Дальше")
    txt = s.text()
    assert "включится модуль" not in txt and "выключится" not in txt and "скроются сферы" not in txt, txt[:600]
    s.click("Всё верно")
    s.ждать_записи(n + 1)
    pr2 = s.gh.files[PROFIL]
    assert fm_get(pr2, "модули") == ["Основа", "Питомцы", "Цикл"] and fm_get(pr2, "имя") == "Анна" and fm_get(pr2, "приоритеты") == ["10", "01"]
    s.programmy("nastroyka.py", "shkala.py", "sled_shag.py")
    assert not s.errors, s.errors


def t_shablon(ctx, port, snimki):
    """Хранилище-шаблон (is_template): страница не загружает его для записи и предлагает создать копию."""
    s = Sayt(ctx, port)
    s.gh.shablon = True
    s.open()
    s.ждать_текст("в него ответы не сохраняются")
    assert s.page.locator("a", has_text="Создать свою копию").get_attribute("href").endswith("/generate")
    assert not s.gh.commits, s.gh.commits
    s.snimok(snimki, "shablon")
    assert not s.errors, s.errors


def kopiya(files):
    """Пробная копия хранилища с этими файлами (путь → текст) — для сравнения с программами."""
    import shutil
    import tempfile
    d = pathlib.Path(tempfile.mkdtemp(prefix="sayt-")) / "kopiya"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git"))
    for fp, text in files.items():
        (d / fp).parent.mkdir(parents=True, exist_ok=True)
        (d / fp).write_text(text, encoding="utf-8")
    return d


def ocenki(text, val, kromе=None):
    """Все строки `оценки` луча — одной цифрой."""
    return re.sub(r'^(\s+-\s+"[^"]+?):\s*(нет|\d+)"', lambda m: f'{m.group(1)}: {val}"', text, flags=re.M)


def t_shag(ctx, port, snimki):
    """«Следующий шаг»: те же помощники, что у sled_shag.py; «Взять в Путь» — тот же файл, что --vzyat."""
    g = Gh()
    nach = {}
    for p, t in g.files.items():
        if p.startswith("10 Сферы/01 ") and "/Шкала/" in p and fm_get(t, "тип") == "луч":
            nach[p] = ocenki(t, 4 if fm_get(t, "код") == "01.12" else 8)
    shk = "10 Сферы/01 Здоровье и молодость/01 Шкала.md"
    nach[shk] = re.sub(r"^приоритет:.*$", "приоритет: 1", g.files[shk], count=1, flags=re.M)
    s = Sayt(ctx, port, nach).open()
    s.go("#/shag")
    s.ждать_текст("Взять в Путь")
    txt = s.text()
    d = kopiya(nach)
    subprocess.run([sys.executable, ".github/scripts/shkala.py", "--write"], cwd=d, capture_output=True, check=True)
    r = subprocess.run([sys.executable, ".github/scripts/sled_shag.py"], cwd=d, capture_output=True, text=True)
    prio = r.stdout.split("## Остальные сферы")[0]
    names = re.findall(r"\[\[(Помощник — [^\]]+)\]\]", prio)
    assert names, r.stdout[:500]
    for n in names:
        assert n.replace("Помощник — ", "").lower() in txt, f"нет на странице: {n}"
    shown = s.page.locator(".card.pom b").all_inner_texts()
    assert len(shown) == len(names), (shown, names)
    s.snimok(snimki, "shag")
    name = names[0]
    s.page.locator(".card.pom", has_text=name.replace("Помощник — ", "")).get_by_text("Взять в Путь").click()
    s.ждать_записи(1)
    fp, msg = s.gh.commits[0]
    r = subprocess.run([sys.executable, ".github/scripts/sled_shag.py", "--vzyat", name], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    want = (d / fp).read_text(encoding="utf-8")
    assert s.gh.files[fp] == want, f"файл шага не как у sled_shag.py:\n{s.gh.files[fp]}\n---\n{want}"
    s.ждать_текст("в «пути»")
    import shutil
    shutil.rmtree(d.parent)
    assert not s.errors, s.errors


def t_nedelya(ctx, port, snimki):
    """«Эта неделя»: +30 мин создаёт план недели и пишет `сделано` (читает nedelya.py), файл календаря .ics."""
    import datetime
    g = Gh()
    nach = {}
    for nn, prio, chasy in (("01 Здоровье и молодость", 1, 2), ("10 Финансы", 2, 1.5)):
        f = f"10 Сферы/{nn}/{nn[:2]} Шкала.md"
        t = re.sub(r"^приоритет:.*$", f"приоритет: {prio}", g.files[f], count=1, flags=re.M)
        nach[f] = re.sub(r"^часы:.*$", f"часы: {chasy}", t, count=1, flags=re.M)
    s = Sayt(ctx, port, nach).open()
    s.go("#/nedelya")
    s.ждать_текст("+30 мин")
    s.snimok(snimki, "nedelya-pusto")
    plus = s.page.locator("[data-act='nedelya:add'][data-nn='01'][data-h='0.5']")
    plus.click(); s.ждать_записи(2)
    plus.click(); s.ждать_записи(3)
    s.page.locator("[data-act='nedelya:add'][data-nn='10'][data-h='0.5']").click(); s.ждать_записи(4)
    s.page.locator("[data-act='nedelya:add'][data-nn='01'][data-h='-0.5']").click(); s.ждать_записи(5)
    mon = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    fp = f"20 Журнал/{mon.isoformat()} План недели.md"
    assert s.gh.commits[0][0] == fp, s.gh.commits
    sd = fm_get(s.gh.files[fp], "сделано")
    assert sd == ["01 Здоровье и молодость: 0,5", "10 Финансы: 0,5"], sd
    assert "# План недели " in s.gh.files[fp]
    s.ждать_текст("1 ч из 3,5 ч плана")
    s.programmy("nedelya.py")
    s.click("Добавить блоки в календарь")
    s.ждать_текст("Скачать файл календаря")
    with s.page.expect_download() as dl:
        s.click("Скачать файл календаря")
    ics = pathlib.Path(dl.value.path()).read_text(encoding="utf-8")
    left = 7 - datetime.date.today().weekday()
    assert ics.startswith("BEGIN:VCALENDAR") and ics.count("BEGIN:VEVENT") == 4, ics[:400]   # 2 ч + 1,5 ч блоками по 60 мин
    assert "Блок внимания: Здоровье и молодость" in ics.replace("\r\n ", "")
    s.snimok(snimki, "nedelya")
    assert left >= 1
    assert not s.errors, s.errors


def t_vygruzka(ctx, port, snimki):
    """Выгрузка: только Медкарта и колесо — текстом (.md) и для печати в PDF."""
    s = Sayt(ctx, port).open()
    s.go("#/vygruzka")
    s.ждать_текст("Отметьте, что выгрузить")
    s.page.locator("input[value='medkarta']").check()
    s.ждать_текст("Собрать (файлов:")
    s.snimok(snimki, "vygruzka-vybor")
    s.page.locator("[data-act='vygruzka:build']").click()
    s.ждать_текст("Выгрузка готова")
    txt = s.text()
    assert "карта тела" in txt and "замеры тела" in txt and "колесо и оценки" in txt, txt[:400]
    assert "журнал" not in txt.split("выгрузка готова")[1].split("цифровая копия — выгрузка")[0], "лишнее в выгрузке"
    with s.page.expect_download() as dl:
        s.click("Скачать текстом (.md)")
    md = pathlib.Path(dl.value.path()).read_text(encoding="utf-8")
    assert "# Медкарта" in md and "## 01 Карта тела" in md and "# Колесо и оценки" in md, md[:300]
    assert "```base" not in s.page.inner_html(".print-doc"), "таблица Obsidian попала в печать"
    s.page.emulate_media(media="print")
    if snimki:
        s.page.pdf(path=str(pathlib.Path(snimki) / "vygruzka.pdf"))
    assert not s.page.locator(".top").is_visible(), "шапка сайта видна при печати"
    s.page.emulate_media(media="screen")
    s.snimok(snimki, "vygruzka")
    assert not s.errors, s.errors


def t_ideya(ctx, port, snimki):
    """«Предложить идею» без входа: Turnstile, отправка в помощник, ответ с номером; без настроек — ссылка на GitHub."""
    sent = []

    def worker(route, req):
        if req.url.endswith("/idei/config"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"sitekey": "0x4AAA", "ready": True}))
        if req.url.endswith("/idei") and req.method == "POST":
            sent.append(json.loads(req.post_data))
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "number": 7}))
        route.fulfill(status=404, body="{}", content_type="application/json")
    s = Sayt(ctx, port, vhod=False, worker=worker)
    s.page.goto(s.base + "#/ideya")
    s.ждать_текст("Не пишите личного")
    s.ждать(lambda: s.page.locator("#ideaSend").is_enabled(), what="Turnstile дал токен")
    s.click("Что-то не работает")
    s.page.fill("#ideaText", "После входа с телефона не сохраняется оценка")
    s.snimok(snimki, "ideya")
    s.page.locator("#ideaSend").click()
    s.ждать_текст("Получено № 7")
    assert sent and sent[0]["vid"] == "ошибка" and sent[0]["token"] == "proba-turnstile" and "не сохраняется" in sent[0]["text"], sent
    assert not s.errors, s.errors
    # помощник без настроек — ссылка на GitHub
    s2 = Sayt(ctx, port, vhod=False)
    s2.page.goto(s2.base + "#/ideya")
    s2.ждать_текст("Форма пока не настроена")
    assert not s2.errors, s2.errors


def t_dengi(ctx, port, snimki):
    """Деньги: начало учёта, расход, доход, перевод, сверка, новый счёт, удаление строки — всё читает dengi.py."""
    import datetime
    s = Sayt(ctx, port).open()
    s.go("#/dengi")
    s.ждать_текст("Начало учёта")
    s.page.fill("[data-st='Кошелёк']", "50")
    s.page.fill("[data-st='Банк']", "1 200,50")
    s.click("Начать учёт"); s.ждать_записи(2)
    ym = datetime.date.today().strftime("%Y-%m")
    fp = next(p for p in s.gh.files if p.endswith(f"/Деньги/10 {ym} Деньги.md"))
    s.ждать_текст("Записать")
    s.page.fill("#dnSum", "12,5"); s.page.select_option("#dnAcc2", "Банк"); s.page.fill("#dnStat", "Еда"); s.page.fill("#dnWhat", "рынок | овощи")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(3)
    s.click("Доход")
    s.page.fill("#dnSum", "900"); s.page.select_option("#dnAcc2", "Банк"); s.page.fill("#dnStat", "Зарплата")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(4)
    s.click("Перевод")
    s.page.fill("#dnSum", "100"); s.page.select_option("#dnFrom", "Банк"); s.page.select_option("#dnTo", "Кошелёк")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(5)
    s.click("Расход")
    s.page.fill("#dnSum", "3"); s.page.select_option("#dnAcc2", "Кошелёк"); s.page.fill("#dnStat", "Кофе")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(6)
    s.page.on("dialog", lambda d: d.accept())
    s.page.locator(".op", has_text="Кофе").locator("[data-act='dengi:del']").click(); s.ждать_записи(7)
    s.page.locator("details summary", has_text="Сверка").click()
    s.page.fill("[data-sv='Кошелёк']", "149")
    s.click("Записать сверку"); s.ждать_записи(8)
    s.page.locator("details summary", has_text="Счета:").click()
    s.page.fill("#dnAcc", "Мне должны"); s.click("долг"); s.click("Добавить счёт"); s.ждать_записи(9)
    t = s.gh.files[fp]
    assert "| 12,50 | Банк | Расход: Еда | рынок / овощи |" in t and "| 900 | Доход: Зарплата | Банк |" in t and "| 100 | Банк | Кошелёк |" in t, t
    assert "Кофе" not in t, "строка не удалилась"
    assert "| Банк | 1200,50 |" in t and f"На: {datetime.date.today().isoformat()}" in t, t
    assert "| Кошелёк | 149 |" in t
    nas = next(p for p in s.gh.files if p.endswith("/Деньги/10 Деньги.md"))
    assert "Мне должны: долг" in s.gh.files[nas]
    d = kopiya({p: s.gh.files[p] for p, _ in s.gh.commits})
    r = subprocess.run([sys.executable, ".github/scripts/dengi.py", "--write"], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0 and "✖" not in r.stdout, r.stdout
    itog = (d / fp).read_text(encoding="utf-8")
    s.gh.files[fp] = itog
    s.go("#/dengi")
    s.ждать_текст("Итоги месяца")
    assert "−12,50" in s.page.inner_text(".ops") or "−12,5" in s.page.inner_text(".ops")
    s.snimok(snimki, "dengi")
    import shutil
    shutil.rmtree(d.parent)
    assert not s.errors, s.errors


def t_valyuty(ctx, port, snimki):
    """Деньги с валютами: основная валюта, счёт в USD, курс, расход в USD, перевод «100 USD → 91» — dengi.py считает."""
    s = Sayt(ctx, port).open()
    s.go("#/dengi")
    s.ждать_текст("Основная валюта")
    s.click("[data-act='dengi:osn'][data-v='EUR']"); s.ждать_записи(1)
    nas = next(p for p in s.gh.files if p.endswith("/Деньги/10 Деньги.md"))
    assert fm_get(s.gh.files[nas], "валюта") == "EUR"
    s.page.locator("details summary", has_text="Счета:").click()
    s.page.fill("#dnAcc", "Revolut"); s.click("банк"); s.page.select_option("#dnAccCur", "USD"); s.click("Добавить счёт"); s.ждать_записи(2)
    assert "Revolut: банк · USD" in s.gh.files[nas]
    s.ждать_текст("USD: курса нет")
    s.page.locator("details summary", has_text="Курсы валют").click() if not s.page.locator("#dnRate").is_visible() else None
    s.page.fill("#dnRate", "0,92"); s.page.fill("#dnRateDate", "2026-01-01"); s.click("Записать курс"); s.ждать_записи(3)
    assert "USD: 0,92 · 2026-01-01" in s.gh.files[nas], s.gh.files[nas][:600]
    s.page.fill("[data-st='Банк']", "1000"); s.page.fill("[data-st='Revolut']", "200")
    s.click("Начать учёт"); s.ждать_записи(5)
    s.ждать_текст("Записать")
    s.page.select_option("#dnAcc2", "Revolut")
    assert s.page.inner_text("#dnCur") == "$", s.page.inner_text("#dnCur")
    s.page.fill("#dnSum", "50"); s.page.fill("#dnStat", "Подписки")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(6)
    s.click("Перевод")
    s.page.select_option("#dnFrom", "Revolut"); s.page.select_option("#dnTo", "Банк")
    assert s.page.locator("#dnSum2").is_visible(), "нет поля «сколько пришло»"
    s.page.fill("#dnSum", "100"); s.page.fill("#dnSum2", "91")
    s.page.locator("[data-act='dengi:add']").click(); s.ждать_записи(7)
    import datetime
    ym = datetime.date.today().strftime("%Y-%m")
    fp = next(p for p in s.gh.files if p.endswith(f"/Деньги/10 {ym} Деньги.md"))
    t = s.gh.files[fp]
    assert "| 50 USD | Revolut | Расход: Подписки |" in t and "| 100 USD → 91 | Revolut | Банк |" in t and "| Revolut | 200 |" in t, t
    d = kopiya({p: s.gh.files[p] for p, _ in s.gh.commits})
    r = subprocess.run([sys.executable, ".github/scripts/dengi.py", "--write"], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0 and "✖" not in r.stdout, r.stdout
    itog = (d / fp).read_text(encoding="utf-8")
    assert "| Revolut | 200 $ | 50 $ |" in itog and "| Подписки | 46 |" in itog and "| Банк | 1 000 € | 1 091 € |" in itog, itog[itog.find("<!-- dengi"):]
    s.gh.files[fp] = itog
    s.go("#/dengi")
    s.ждать_текст("Итоги месяца")
    assert "−50 $" in s.page.inner_text(".ops"), s.page.inner_text(".ops")
    s.snimok(snimki, "valyuty")
    import shutil
    shutil.rmtree(d.parent)
    assert not s.errors, s.errors


def kopiya_gh(gh):
    """Пробная копия ровно с файлами подменённого GitHub (.md): удалённые на нём — удалены и здесь."""
    d = kopiya({k: v for k, v in gh.files.items()})
    for f in list(d.rglob("*.md")):
        rel = f.relative_to(d).as_posix()
        if not rel.startswith(".git") and rel not in gh.files and not rel.startswith("80 Шаблоны/"):
            f.unlink()
    return d


def nastroyka_vse(gh):
    """Как GitHub Actions после поручения «Мои сферы»: nastroyka.py в копии со всеми файлами GitHub; переносы и удаления — обратно."""
    import shutil
    d = kopiya_gh(gh)
    r = subprocess.run([sys.executable, str(d / ".github/scripts/nastroyka.py")], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    est = set()
    for f in d.rglob("*.md"):
        rel = f.relative_to(d).as_posix()
        if rel.startswith(".git") or rel.startswith("80 Шаблоны/"):
            continue
        est.add(rel)
        text = f.read_text(encoding="utf-8")
        if gh.files.get(rel) != text:
            gh.files[rel] = text
    for rel in [k for k in gh.files if not k.startswith("80 Шаблоны/") and k not in est]:
        del gh.files[rel]
    shutil.rmtree(d.parent)
    return r.stdout


def proverit_gh(gh, *names):
    """Программы хранилища на файлах подменённого GitHub (без --write): без ошибок."""
    import shutil
    d = kopiya_gh(gh)
    for n in names:
        r = subprocess.run([sys.executable, str(d / ".github/scripts" / n)], cwd=d, capture_output=True, text=True)
        assert r.returncode == 0 and "✖" not in r.stdout and "Битых ссылок: " not in r.stdout, f"{n}: {r.stdout[-900:]}{r.stderr[-400:]}"
    shutil.rmtree(d.parent)


MOI = "00 Старт/Мои сферы.md"


def t_sfery(ctx, port, snimki):
    """«Мои сферы»: порядок, переименовать, своя сфера с лучами, луч в сфере шаблона, скрыть — поручение → nastroyka.py → ссылки целы."""
    s = Sayt(ctx, port).open()
    s.go("#/")
    s.ждать_текст("Мои сферы")
    s.go("#/sfery")
    s.ждать_текст("Порядок на колесе")
    assert "на колесе — 12" in s.text(), s.text()[:300]
    s.snimok(snimki, "sfery-spisok")
    # 1. порядок: «Духовность» на ступень выше
    s.click("[data-act='sfery:up'][data-v='05']")
    s.ждать_текст("Сохранить порядок")
    s.click("Сохранить порядок")
    s.ждать_записи(1)
    assert s.gh.commits[-1][0] == MOI, s.gh.commits
    z = fm_get(s.gh.files[MOI], "заявка")
    assert len(z) == 1 and z[0].split(" · ")[1:] == ["порядок", "01, 02, 03, 05, 04, 06, 07, 08, 09, 10, 11, 12"], z
    s.ждать_текст("Меняю сферы")
    out = nastroyka_vse(s.gh)
    assert "порядок на колесе" in out, out
    s.ждать_текст("порядок на колесе: 01, 02, 03, 05, 04", 30000)
    assert fm_get(s.gh.files["10 Сферы/05 Духовность/05 Духовность.md"], "порядок") == "4"
    names = [x.strip() for x in s.page.locator("#app .twh b").all_inner_texts()]
    assert names[3] == "Духовность", names
    # 2. неверное название — не отправляется
    s.go("#/sfery/imya/05")
    s.page.fill("#sfShort", "Смыслы/ценности")
    n = len(s.gh.commits)
    s.click("Переименовать")
    s.ждать(lambda: "нельзя знаки" in s.page.inner_text("#toast"), 3000, "подсказка о знаках")
    assert len(s.gh.commits) == n
    # 3. переименовать
    s.page.fill("#sfShort", "Смыслы")
    s.page.fill("#sfFull", "Смыслы и ценности")
    s.snimok(snimki, "sfery-imya")
    s.click("Переименовать")
    s.ждать_записи(n + 1)
    out = nastroyka_vse(s.gh)
    assert "переименовано: 05 Духовность → 05 Смыслы" in out, out
    s.ждать_текст("переименовано: 05 Духовность → 05 Смыслы", 30000)
    assert "10 Сферы/05 Смыслы/05 Смыслы.md" in s.gh.files and not any(k.startswith("10 Сферы/05 Духовность/") for k in s.gh.files)
    assert not any("[[05 Духовность]]" in v for k, v in s.gh.files.items() if not k.startswith(("80 Шаблоны/", "90 Архив/")))
    # 4. своя сфера с лучами
    s.go("#/sfery/novaya")
    s.page.fill("#sfShort", "Путешествия")
    s.page.fill("#sfFull", "Путешествия и открытия")
    s.page.fill("#sfRays", "Страны и города\nПоходы и горы")
    s.snimok(snimki, "sfery-novaya")
    s.click("Добавить сферу")
    s.ждать_записи(n + 2)
    out = nastroyka_vse(s.gh)
    assert "добавлена сфера 13 Путешествия" in out, out
    s.ждать_текст("добавлена сфера 13 путешествия", 30000)
    luch = "10 Сферы/13 Путешествия/Шкала/13 Луч — Страны и города.md"
    assert fm_get(s.gh.files[luch], "код") == "13.01" and fm_get(s.gh.files["10 Сферы/13 Путешествия/13 Путешествия.md"], "порядок") == "13"
    s.go("#/13")
    s.ждать_текст("Походы и горы")
    # 5. луч в сфере шаблона — код с 51
    s.go("#/sfery/imya/02")
    s.page.fill("#sfLuch", "Юмор")
    s.click("Добавить луч")
    s.ждать_записи(n + 3)
    out = nastroyka_vse(s.gh)
    s.ждать_текст("добавлен луч 02 луч — юмор", 30000)
    assert fm_get(s.gh.files["10 Сферы/02 Эмоции/Шкала/02 Луч — Юмор.md"], "код") == "02.51"
    assert "[[02 Луч — Юмор]]" in s.gh.files["10 Сферы/02 Эмоции/02 Шкала.md"]
    # 6. скрыть свою сферу и вернуть
    s.go("#/sfery/imya/13")
    s.click("Скрыть сферу — не моё сейчас")
    s.ждать_записи(n + 4)
    assert fm_get(s.gh.files["10 Сферы/13 Путешествия/13 Путешествия.md"], "скрыта") == "true"
    s.ждать_текст("Скрытые — не на колесе")
    s.click("[data-act='sfery:skryt'][data-v='false']")
    s.ждать_записи(n + 5)
    assert fm_get(s.gh.files["10 Сферы/13 Путешествия/13 Путешествия.md"], "скрыта") == "false"
    proverit_gh(s.gh, "check_links.py", "shkala.py", "sled_shag.py", "nedelya.py", "oprosnik.py", "pomoshniki.py")
    assert not s.errors, s.errors


PROVERKI = {k[2:]: v for k, v in list(globals().items()) if k.startswith("t_")}


def main():
    args = sys.argv[1:]
    snimki = None
    if "--snimki" in args:
        i = args.index("--snimki")
        snimki = args[i + 1]
        pathlib.Path(snimki).mkdir(parents=True, exist_ok=True)
        del args[i:i + 2]
    if "--spisok" in args:
        for k, f in PROVERKI.items():
            print(f"{k} — {f.__doc__}")
        return 0
    names = args or list(PROVERKI)
    from playwright.sync_api import sync_playwright
    srv = server()
    port = srv.server_address[1]
    bad = 0
    with sync_playwright() as p:
        kw = {"executable_path": CHROME} if pathlib.Path(CHROME).exists() else {}
        b = p.chromium.launch(args=["--no-sandbox"], **kw)
        for n in names:
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="ru-RU", timezone_id="Europe/Madrid")
            try:
                PROVERKI[n](ctx, port, snimki)
                print(f"✓ {n}")
            except Exception as e:  # noqa: BLE001
                bad += 1
                print(f"✖ {n}: {e}")
                traceback.print_exc(limit=3)
            finally:
                ctx.close()
        b.close()
    srv.shutdown()
    print("Все проверки прошли." if not bad else f"Не прошло: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
