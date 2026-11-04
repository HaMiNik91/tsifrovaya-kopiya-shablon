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
            return ok({"default_branch": "main", "permissions": {"push": True}})
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

    def __init__(self, ctx, port, nachalo=None, vhod=True, worker=None):
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
        if vhod:
            self.page.add_init_script(f"""try{{localStorage.setItem('tk.repo','{OWNER}/{REPO}');
                localStorage.setItem('tk.token','proba');localStorage.setItem('tk.via','key');}}catch(e){{}}""")
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
        self.page.goto(self.base + hash_)
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
