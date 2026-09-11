#!/usr/bin/env python3
"""
Доработка поверх myanon: сквозная замена персональных данных внутри свободного текста.

Зачем. myanon заменяет значение поля целиком по правилу «колонка → правило» и
не умеет заменять подстроки внутри текста. Из-за этого значение, обработанное
в своей колонке, остаётся нетронутым там, где оно упомянуто в свободном тексте,
и требование сквозной замены не выполняется.

Как. Исходный и очищенный дампы имеют одинаковую структуру и одинаковый порядок
строк, поэтому пара «исходное значение → его замена» восстанавливается сопоставлением
строк по позиции. Дальше каждое исходное значение заменяется на свою замену по всему
очищенному дампу. Никакого распознавания не требуется: заменяются только значения,
которые уже известны из структурированных колонок.

Замены применяются от самой длинной строки к самой короткой, чтобы длинное значение
не оказалось испорчено заменой более короткого, вложенного в него.

Использование:
    python3 text_substitute.py исходный.sql очищенный.sql итоговый.sql
"""
import os
import re
import sys

from . import names as llm_names
from . import pii_patterns
from .sql_parse import parse_inserts, unquote

# Колонки, из которых берутся исходные значения. Совпадают с обработанными в myanon.conf.template.
PII_COLUMNS = {
    "customers": ["full_name", "email", "phone", "inn", "address"],
    "employees": ["full_name", "snils", "email"],
}

# Колонки с ФИО: заменяются правдоподобными именами из пула, порождённого
# языковой моделью, а не хешем. Пул раздаётся детерминированно (llm_names).
NAME_COLUMNS = {
    "customers": ["full_name"],
    "employees": ["full_name"],
}

# Минимальная длина значения, участвующего в замене. Защита от того, чтобы
# короткое значение случайно совпало с фрагментом постороннего текста.
MIN_VALUE_LEN = 5








def build_map(src_path, san_path):
    src, san = parse_inserts(src_path), parse_inserts(san_path)
    mapping = {}
    for table, columns in PII_COLUMNS.items():
        if table not in src or table not in san:
            print(f"  внимание: таблицы {table} нет в одном из дампов, пропущена", file=sys.stderr)
            continue
        src_cols, src_rows = src[table]
        san_cols, san_rows = san[table]
        if len(src_rows) != len(san_rows):
            raise SystemExit(
                f"ОШИБКА: в таблице {table} разное число строк "
                f"({len(src_rows)} и {len(san_rows)}) — сопоставление по позиции невозможно."
            )
        for col in columns:
            if col not in src_cols or col not in san_cols:
                print(f"  внимание: колонки {table}.{col} нет в дампе, пропущена", file=sys.stderr)
                continue
            si, di = src_cols.index(col), san_cols.index(col)
            for s_row, d_row in zip(src_rows, san_rows):
                original, replacement = unquote(s_row[si]), unquote(d_row[di])
                if original == replacement or len(original) < MIN_VALUE_LEN:
                    continue
                previous = mapping.get(original)
                if previous is not None and previous != replacement:
                    raise SystemExit(
                        f"ОШИБКА: значение «{original}» получило две разные замены "
                        f"(«{previous}» и «{replacement}») — сквозная замена нарушена."
                    )
                mapping[original] = replacement
    return mapping


def main(src_path, san_path, out_path):
    mapping = build_map(src_path, san_path)
    known = len(mapping)

    # Расширение карты: значения строгого формата, найденные в ИСХОДНОМ тексте
    # и не совпадающие ни с одной колонкой. Добавляются в ту же карту, поэтому
    # подстановка остаётся одна и двойная замена невозможна.
    secret = os.environ.get("SANITIZE_SECRET")

    # Правдоподобные ФИО из пула. Пул порождён моделью заранее и лежит в файле,
    # поэтому сам прогон модели не требует и воспроизводится где угодно.
    by_name = {}
    if secret:
        try:
            pool = llm_names.load_pool()
        except (OSError, ValueError, KeyError) as e:
            print(f"  ВНИМАНИЕ: пул имён недоступен ({e}). ФИО останутся открытыми, "
                  f"и verify.py на этом прогоне обязан упасть — не принимайте результат.",
                  file=sys.stderr)
            pool = None
        if pool:
            src_tables = parse_inserts(src_path)
            originals = set()
            for table, cols in NAME_COLUMNS.items():
                if table not in src_tables:
                    continue
                tcols, trows = src_tables[table]
                for col in cols:
                    if col in tcols:
                        i = tcols.index(col)
                        originals.update(unquote(r[i]) for r in trows)
            by_name = llm_names.assign(originals, pool, secret)
            mapping.update(by_name)

    if secret:
        src_text = open(src_path, encoding="utf-8").read()
        by_format = pii_patterns.build_replacements(src_text, secret, exclude=set(mapping))
        mapping.update(by_format)
    else:
        by_format = {}
        print("  внимание: SANITIZE_SECRET не задан, распознавание по формату пропущено",
              file=sys.stderr)

    # Замена не должна совпадать ни с одним исходным значением. Иначе исходное
    # значение остаётся видимым в результате (его подставили вместо другого),
    # а число его вхождений меняется — обе проверки verify.py падают. Проверка
    # общая, а не только для ФИО: тот же класс ошибки возможен у любого источника.
    collisions = sorted(v for v in mapping.values() if v in mapping)
    if collisions:
        raise SystemExit(
            "Ошибка: замена совпадает с исходным значением — "
            f"{collisions[:5]} (всего {len(collisions)}). "
            "Результат не записан: такая замена не скрывает данные, а переносит их.")

    text = open(san_path, encoding="utf-8").read()

    total = 0
    applied = 0
    # От длинных значений к коротким: иначе замена вложенной подстроки испортит длинное значение.
    for original in sorted(mapping, key=len, reverse=True):
        count = text.count(original)
        if count:
            text = text.replace(original, mapping[original])
            total += count
            applied += 1

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Значений в карте замен: {len(mapping)}"
          f" (из колонок: {known}, ФИО из пула модели: {len(by_name)},"
          f" распознано по формату: {len(by_format)})")
    print(f"Значений, реально найденных в тексте: {applied}")
    print(f"Всего подстановок: {total}")
    print(f"Записано: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
