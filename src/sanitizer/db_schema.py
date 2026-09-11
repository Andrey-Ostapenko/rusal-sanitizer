#!/usr/bin/env python3
"""
Разбор схемы из дампа: колонки таблиц и колонки, участвующие в ключах.

Зачем отдельно от `sql_parse.py`: тот разбирает данные (INSERT), а здесь нужна
структура (CREATE TABLE). Смешивать не стоит — у них разные поводы ломаться.

Главное здесь — `key_columns`. Это предохранитель цикла автонастройки:
если модель отнесёт `customer_id` к персональным данным и правило уйдёт в
конфиг, хеширование внешнего ключа разрушит связи между таблицами — ровно то,
что задание требует сохранить. Поэтому ключевые колонки исключаются
детерминированно, из текста схемы, а не по решению модели.
"""
from . import paths
import re

CREATE = re.compile(r"CREATE\s+TABLE\s+`(\w+)`\s*\((.*?)\)\s*ENGINE", re.S | re.I)
COLUMN = re.compile(r"^\s*`(\w+)`\s+([a-z]+)", re.I)
KEY_LINE = re.compile(r"^\s*(?:PRIMARY\s+KEY|UNIQUE\s+KEY|KEY|CONSTRAINT|FOREIGN\s+KEY)", re.I)
IN_BACKTICKS = re.compile(r"`(\w+)`")
FK_COLS = re.compile(r"FOREIGN\s+KEY\s*\(([^)]*)\)", re.I)
KEY_COLS = re.compile(r"(?:PRIMARY\s+KEY|UNIQUE\s+KEY|KEY)\s*(?:`\w+`\s*)?\(([^)]*)\)", re.I)


def parse_schema(path):
    """
    Возвращает {таблица: {"columns": [(имя, тип), ...], "keys": {имена}}}.

    В keys попадают все колонки, упомянутые в строках с KEY, PRIMARY KEY,
    CONSTRAINT и FOREIGN KEY — включая ту сторону внешнего ключа, на которую
    ссылаются из другой таблицы.
    """
    text = open(path, encoding="utf-8").read()
    schema = {}
    for table, body in CREATE.findall(text):
        columns, keys = [], set()
        for line in body.splitlines():
            if KEY_LINE.match(line):
                # Берём имена ТОЛЬКО из скобок после самого ключевого слова.
                # Брать все имена в обратных кавычках подряд нельзя: в строке
                # CONSTRAINT ... FOREIGN KEY (`x`) REFERENCES `t` (`y`)
                # так в колонки попадает имя чужой таблицы. Найдено
                # самопроверкой этого же файла.
                m = FK_COLS.search(line) or KEY_COLS.search(line)
                if m:
                    keys.update(IN_BACKTICKS.findall(m.group(1)))
                continue
            m = COLUMN.match(line)
            if m:
                columns.append((m.group(1), m.group(2).lower()))
        schema[table] = {"columns": columns, "keys": keys}

    # колонка, на которую ссылается внешний ключ из другой таблицы,
    # тоже неприкосновенна
    for table, body in CREATE.findall(text):
        for m in re.finditer(r"REFERENCES\s+`(\w+)`\s*\(([^)]*)\)", body, re.I):
            ref_table, ref_cols = m.group(1), IN_BACKTICKS.findall(m.group(2))
            if ref_table in schema:
                schema[ref_table]["keys"].update(ref_cols)
    return schema


def _самопроверка(path=None):
    path = path or paths.данные("demo_dump.sql")
    s = parse_schema(path)
    if not s:
        print("ОТКАЗ: схема не разобрана — проверять нечего.")
        return 1
    сбои = []
    for t, d in sorted(s.items()):
        cols = [c for c, _ in d["columns"]]
        print(f"{t}: колонок {len(cols)}, ключевых {len(d['keys'])} -> {sorted(d['keys'])}")
        if not cols:
            сбои.append(f"{t}: колонок не найдено")
        if "id" not in d["keys"]:
            сбои.append(f"{t}: первичный ключ id не распознан")
        # имена ограничений не должны попадать в список колонок
        for k in d["keys"]:
            if k not in cols:
                сбои.append(f"{t}: в ключах имя, которого нет среди колонок: {k}")
    print()
    if сбои:
        print("НАРУШЕНО:", *сбои, sep="\n  ")
        return 1
    print("Схема разобрана, ключевые колонки определены.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_самопроверка(sys.argv[1] if len(sys.argv) > 1 else paths.данные("demo_dump.sql")))
