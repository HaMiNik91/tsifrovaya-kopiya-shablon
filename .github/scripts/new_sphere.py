#!/usr/bin/env python3
"""Создаёт файлы сфер из шаблонов в «80 Шаблоны».

Запуск из корня хранилища:
    python3 .github/scripts/new_sphere.py          — все сферы
    python3 .github/scripts/new_sphere.py 03 10    — только сферы с кодами 03 и 10
    python3 .github/scripts/new_sphere.py --nova 13 "Короткое" "Полное название"
                                                   — новая своя сфера с кодом 13

Какие сферы есть, программа узнаёт из папок «10 Сферы»: код и порядок — из шапки
оглавления «NN Сфера.md», короткое название — из имени папки, полное — из заголовка
оглавления. Жёсткого списка нет (CLAUDE.md, п. 5.4: `код`, `порядок`, `скрыта`).
Список OSNOVA ниже нужен только пустому хранилищу, где сфер ещё нет.

Программа только ДОБАВЛЯЕТ недостающие файлы и папки. Существующие файлы
не трогает никогда — заполненные записи в безопасности. Если в шаблоны
добавить новый общий файл (и вписать его в SPHERE_FILES), запуск создаст
его во всех сферах.

В шаблонах подставляются заготовки:
    {{NN}}      — номер сферы (01)
    {{Сфера}}   — короткое название (Здоровье и молодость)
    {{Полное}}  — полное название (Здоровье, фитнес, молодость)
    {{date}}    — сегодняшняя дата (2026-10-01)
    {{порядок}} — место сферы на колесе, число (1)
"""
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "80 Шаблоны"
SPHERES_DIR = ROOT / "10 Сферы"

# Основа из 12 сфер для пустого хранилища: код, короткое название (имя папки и файла), полное (заголовок).
# Источник — CLAUDE.md, раздел 4.1. Существующие сферы берутся из папок, не отсюда.
OSNOVA = [
    ("01", "Здоровье и молодость", "Здоровье, фитнес, молодость"),
    ("02", "Эмоции", "Эмоции"),
    ("03", "Интеллект", "Интеллект"),
    ("04", "Качества характера", "Качества характера"),
    ("05", "Духовность", "Духовность"),
    ("06", "Пара, любовь и сексуальность", "Отношения в паре, любовь и сексуальность"),
    ("07", "Семья", "Семья: отношения с детьми и родителями"),
    ("08", "Друзья и окружение", "Друзья и окружение"),
    ("09", "Профессиональная реализация", "Профессиональная реализация, своё дело"),
    ("10", "Финансы", "Финансы, управление деньгами и благосостоянием"),
    ("11", "Хобби и творчество", "Хобби и творчество"),
    ("12", "Качество жизни", "Качество жизни — вещи и приобретения"),
]

# Общие файлы сферы (CLAUDE.md, раздел 5.1), в порядке оглавления.
SPHERE_FILES = [
    "Шкала", "Вопросы после оценки", "Предложенные убеждения", "Сейчас", "Хочу", "Путь", "Опыт", "Инструменты", "Мысли",
    "Идеи", "Убеждения", "Привычки", "Эксперименты", "Выводы",
]

# Папки внутри сферы; пустые хранятся в Git с помощью файла .gitkeep.
SPHERE_FOLDERS = ["Входящие", "Записи", "Опыт", "Путь", "Шкала", "Инструменты"]


def fill(text, nn, short, full, today):
    return (text.replace("{{NN}}", nn)
                .replace("{{Сфера}}", short)
                .replace("{{Полное}}", full)
                .replace("{{порядок}}", str(int(nn)))
                .replace("{{date}}", today))


def write_new(path, content, created):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(path.relative_to(ROOT))


def build_sphere(nn, short, full, today, created):
    folder = SPHERES_DIR / f"{nn} {short}"
    index_tpl = (TEMPLATES / "Шаблон — Оглавление сферы.md").read_text(encoding="utf-8")
    write_new(folder / f"{nn} {short}.md", fill(index_tpl, nn, short, full, today), created)
    for name in SPHERE_FILES:
        tpl = (TEMPLATES / f"Шаблон — {name}.md").read_text(encoding="utf-8")
        write_new(folder / f"{nn} {name}.md", fill(tpl, nn, short, full, today), created)
    for sub in SPHERE_FOLDERS:
        sub_dir = folder / sub
        if not sub_dir.exists() or not any(sub_dir.iterdir()):
            write_new(sub_dir / ".gitkeep", "", created)


def existing_spheres():
    """Сферы из папок: (код, короткое, полное). Код — из оглавления, иначе номер папки."""
    out = []
    if not SPHERES_DIR.exists():
        return out
    for folder in sorted(p for p in SPHERES_DIR.iterdir() if p.is_dir() and re.match(r"^\d{2} ", p.name)):
        index = folder / f"{folder.name}.md"
        text = index.read_text(encoding="utf-8") if index.exists() else ""
        kod = re.search(r'^код:\s*"?(\d{2})"?\s*$', text, re.M)
        head = re.search(r"^# (.+)$", text, re.M)
        short = folder.name[3:]
        out.append((kod.group(1) if kod else folder.name[:2], short, head.group(1).strip() if head else short))
    return out


def main(argv):
    today = datetime.date.today().isoformat()
    created = []
    spheres = existing_spheres() or list(OSNOVA)
    if argv[:1] == ["--nova"]:
        if len(argv) != 4 or not re.match(r"^\d{2}$", argv[1]):
            sys.exit('нужно: --nova NN "Короткое" "Полное название"')
        if any(k == argv[1] for k, _, _ in spheres):
            sys.exit(f"сфера с кодом {argv[1]} уже есть")
        spheres, only = [(argv[1], argv[2], argv[3])], set()
    else:
        only = set(argv)
    for nn, short, full in spheres:
        if only and nn not in only:
            continue
        build_sphere(nn, short, full, today, created)
    print(f"Создано файлов: {len(created)}")
    for p in created:
        print("  +", p)


if __name__ == "__main__":
    main(sys.argv[1:])
