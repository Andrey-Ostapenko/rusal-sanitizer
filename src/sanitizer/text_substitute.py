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
import sys

from . import pii_patterns
from .sql_parse import parse_inserts, unquote

# Перечень колонок — общие данные, а не константа этого модуля: им же
# пользуется проверка, и брать его отсюда значило бы строить проверяющего
# на коде проверяемого. См. pii_columns.py.
from .pii_columns import COLUMNS as PII_COLUMNS

# Минимальная длина значения, участвующего в замене. Защита от того, чтобы
# короткое значение случайно совпало с фрагментом постороннего текста.
from .pii_columns import MIN_VALUE_LEN  # noqa: F401 — общий порог


def найти_имена(src_path, src_text, secret, exclude):
    """
    Карта «имя из свободного текста → нейтральная замена».

    Модель смотрит только на колонки свободного текста: в остальных значение
    целиком берёт myanon по конфигу. Находки проходят два детерминированных
    фильтра из loop_guard: засчитывается только то, что есть во ВХОДНОМ дампе
    (иначе цикл гонялся бы за собственными заменами), и отбрасывается вложенное
    в уже покрытое значение.
    """
    from . import detect as детектор
    from . import loop_guard
    from .db_schema import parse_schema
    from .pii_columns import FREE_TEXT_TYPES as СВОБОДНЫЙ_ТЕКСТ

    схема, данные = parse_schema(src_path), parse_inserts(src_path)
    найдено = []
    осмотрено = 0
    for таблица, инфо in схема.items():
        if таблица not in данные:
            continue
        колонки, строки = данные[таблица]
        for имя, тип in инфо["columns"]:
            if тип not in СВОБОДНЫЙ_ТЕКСТ or имя not in колонки:
                continue
            i = колонки.index(имя)
            for строка in строки:
                значение = unquote(строка[i])
                if not значение:
                    continue
                осмотрено += 1
                найдено.extend(детектор.detect(значение))

    сырых = len(найдено)
    найдено, не_во_входе = loop_guard.actionable(найдено, src_text)
    найдено, вложенные = loop_guard.убрать_вложенные(найдено, exclude)
    карта = {f["значение"]: pii_patterns.fake_name(f["значение"], secret)
             for f in найдено if f["значение"] not in exclude}
    print(f"  детектор имён: осмотрено значений {осмотрено}, "
          f"сырых находок {сырых}, отброшено фильтрами "
          f"{len(не_во_входе)} (нет во входном дампе) + {len(вложенные)} "
          f"(вложены в уже покрытое), принято {len(карта)}")
    return карта


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

    # ФИО заменяет myanon по конфигу, как и адрес: в карту они попадают из
    # сопоставления дампов вместе с остальными колонками. Пул правдоподобных
    # имён из пути замены убран — правдоподобная замена создаёт синтетические
    # персональные данные, а при включённом правиле на full_name пул ещё и
    # перезаписывал замену из колонки, ломая сквозную замену (замерено:
    # 3 расхождения из 186 пар).

    if secret:
        src_text = open(src_path, encoding="utf-8").read()
        by_format = pii_patterns.build_replacements(src_text, secret, exclude=set(mapping))
        mapping.update(by_format)

        # Имена людей в свободном тексте — единственный вид ПДн, у которого нет
        # ни строгого формата, ни источника в колонках. Их ищет модель.
        #
        # Выключено по умолчанию намеренно: прогон обязан воспроизводиться на
        # машине без модели и без сети, иначе проверка «тот же ключ — тот же
        # результат» перестаёт что-либо значить. Включается DETECT_NAMES=1.
        by_name = {}
        if os.environ.get("DETECT_NAMES") == "1":
            by_name = найти_имена(src_path, src_text, secret, exclude=set(mapping))
            mapping.update(by_name)
    else:
        by_format, by_name = {}, {}
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
          f" (из колонок: {known}, распознано по формату: {len(by_format)},"
          f" имён из текста: {len(by_name)})")
    print(f"Значений, реально найденных в тексте: {applied}")
    print(f"Всего подстановок: {total}")
    print(f"Записано: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
