#!/usr/bin/env python3
"""Ищет битые ссылки в хранилище.

Запуск из корня хранилища:
    python3 .github/scripts/check_links.py

Проверяет:
  - вики-ссылки [[Имя]], [[Имя|подпись]], [[Имя#раздел]], ![[Имя]] —
    по имени файла (.md, .canvas, .base) и по псевдонимам (aliases);
  - обычные ссылки [текст](путь/файл.md) и [текст](<путь с пробелами.md>) —
    по пути относительно файла.
Пропускает: папку «80 Шаблоны» (в шаблонах заготовки вида {{Сфера}}),
«90 Архив» (оригиналы не правятся), блоки кода и комментарии.
Код выхода 1, если найдены битые ссылки, — так проверку можно
запускать автоматически (GitHub Actions).

Заодно предупреждает (без ошибки) о файлах-планах (в имени «План») и
README.md больше SIZE_LIMIT знаков — правило «Короткие планы»,
CLAUDE.md, раздел 6.
"""
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".obsidian", ".github", "80 Шаблоны", "90 Архив"}
LINKABLE = {".md", ".canvas", ".base"}

CODE_BLOCK = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
COMMENT = re.compile(r"<!--.*?-->", re.S)
WIKI = re.compile(r"!?\[\[([^\]]+?)\]\]")
MD_LINK = re.compile(r"\[[^\]]*\]\((<[^>\n]+>|[^)\s]+)\)")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SIZE_LIMIT = 30_000  # знаков, не байтов


def skipped(path):
    return any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)


def aliases_of(text):
    """Псевдонимы из шапки: aliases: [a, b] или списком строк ниже."""
    m = FRONTMATTER.match(text)
    if not m:
        return []
    result, inside = [], False
    for line in m.group(1).splitlines():
        if line.startswith("aliases:"):
            rest = line[len("aliases:"):].strip()
            if rest.startswith("["):
                result += [a.strip().strip('"\'') for a in rest.strip("[]").split(",") if a.strip()]
            inside = not rest
            continue
        if inside and line.lstrip().startswith("- "):
            result.append(line.lstrip()[2:].strip().strip('"\''))
        elif inside:
            inside = False
    return result


def main():
    files = [p for p in ROOT.rglob("*") if p.is_file() and not skipped(p)]
    # Цели ссылок: имена всех файлов (включая шаблоны — ссылка на шаблон допустима).
    names = {p.stem for p in ROOT.rglob("*") if p.suffix in LINKABLE and ".git" not in p.parts}
    names |= {p.name for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts}
    notes = [p for p in files if p.suffix == ".md"]
    for p in notes:
        names |= set(aliases_of(p.read_text(encoding="utf-8")))

    broken = []
    for p in notes:
        text = p.read_text(encoding="utf-8")
        body = COMMENT.sub("", INLINE_CODE.sub("", CODE_BLOCK.sub("", text)))
        for target in WIKI.findall(body):
            name = target.split("|")[0].split("#")[0].strip()
            if name and name not in names and pathlib.Path(name).name not in names:
                broken.append((p, f"[[{target}]]"))
        for target in MD_LINK.findall(body):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            if target.startswith("<"):  # [текст](<имя с пробелами.md>)
                target = target[1:-1]
            rel = urllib.parse.unquote(target.split("#")[0])
            if rel and not (p.parent / rel).exists():
                broken.append((p, f"({target})"))

    for p in notes:
        if "План" in p.stem or p.name == "README.md":
            size = len(p.read_text(encoding="utf-8"))
            if size > SIZE_LIMIT:
                rel = p.relative_to(ROOT)
                print(f"::warning file={rel}::Предупреждение: {rel} — {size} знаков, "
                      f"больше {SIZE_LIMIT}. Готовые разделы — в свои файлы (CLAUDE.md, раздел 6).")

    if broken:
        print(f"Битых ссылок: {len(broken)}")
        for p, link in broken:
            print(f"  {p.relative_to(ROOT)}: {link}")
        sys.exit(1)
    print(f"Проверено файлов: {len(notes)}. Битых ссылок нет.")


if __name__ == "__main__":
    main()
