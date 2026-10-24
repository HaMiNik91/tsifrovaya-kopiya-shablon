"""Точечные правки многих файлов сразу — всё или ничего.

Запуск из корня хранилища:
    python3 .github/scripts/pravka.py правки.py          # проверить и записать
    python3 .github/scripts/pravka.py правки.py --check  # только проверить, ничего не писать

Файл правок (держать в рабочей папке, не в хранилище) задаёт список PRAVKI.
Пути — от корня хранилища. Виды правок:

    ("заменить", путь, старый_текст, новый_текст)
        старый текст должен встречаться в файле ровно один раз.
    ("уровни", путь, зона_или_None, {номер: "новый признак", ...})
        меняет строки «| N | … |» в таблице уровней внутри зоны
        (раздел «## Зона «…»» до следующего «## »); None — первая таблица файла.
    ("дописать", путь, текст)
        добавляет текст в конец файла (с пустой строкой перед ним).

Сначала все правки применяются в памяти. Если хоть одна не сошлась
(текст не найден или найден не один раз, нет зоны, нет строки уровня),
программа перечисляет ошибки и не записывает ни одного файла.
У изменённых файлов дата в свойстве «обновлено» ставится сегодняшняя.
"""
import datetime
import pathlib
import re
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _rows(text, zone, new, errs, where):
    try:
        start = text.index('## Зона «%s»' % zone) if zone else text.index('| Уровень')
    except ValueError:
        errs.append(f'{where}: не найдена {"зона «" + zone + "»" if zone else "таблица уровней"}')
        return text
    if zone and text.count('## Зона «%s»' % zone) != 1:
        errs.append(f'{where}: зона «{zone}» встречается не один раз')
        return text
    end = text.find('\n## ', start + 1)
    end = len(text) if end == -1 else end
    block = text[start:end]
    for n, txt in new.items():
        found = re.findall(rf'^\| {n} \| .*\|$', block, re.M)
        if len(found) != 1:
            errs.append(f'{where}: строка уровня {n} найдена {len(found)} раз')
            continue
        block = block.replace(found[0], f'| {n} | {txt} |')
    return text[:start] + block + text[end:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        print(__doc__)
        sys.exit(2)
    check_only = '--check' in sys.argv
    pravki = runpy.run_path(args[0])['PRAVKI']
    texts, errs = {}, []
    for i, p in enumerate(pravki, 1):
        kind, path = p[0], ROOT / p[1]
        where = f'#{i} {p[1]}'
        if path not in texts:
            if not path.exists():
                errs.append(f'{where}: файла нет')
                continue
            texts[path] = path.read_text(encoding='utf-8')
        t = texts[path]
        if kind == 'заменить':
            n = t.count(p[2])
            if n != 1:
                errs.append(f'{where}: старый текст найден {n} раз: {p[2][:70]!r}')
                continue
            texts[path] = t.replace(p[2], p[3])
        elif kind == 'уровни':
            texts[path] = _rows(t, p[2], p[3], errs, where)
        elif kind == 'дописать':
            texts[path] = t.rstrip('\n') + '\n\n' + p[2].strip('\n') + '\n'
        else:
            errs.append(f'{where}: неизвестный вид правки «{kind}»')
    if errs:
        print('✖ Ничего не записано:')
        print('\n'.join('  ' + e for e in errs))
        sys.exit(1)
    today = datetime.date.today().isoformat()
    changed = 0
    for path, t in texts.items():
        if t == path.read_text(encoding='utf-8'):
            continue
        t = re.sub(r'^обновлено: .*$', f'обновлено: {today}', t, count=1, flags=re.M)
        changed += 1
        if not check_only:
            path.write_text(t, encoding='utf-8')
    print(f'{"Проверено" if check_only else "Записано"}: {len(pravki)} правок, файлов изменено: {changed}')


if __name__ == '__main__':
    main()
