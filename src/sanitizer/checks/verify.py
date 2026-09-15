#!/usr/bin/env python3
"""
Проверка результата санитизации. Печатает таблицу, по которой видно,
выполнены ли требования, — без обращения к СУБД, только по двум дампам.

Проверяется:
  1. Персональные данные из колонок не остались нигде в результате.
  2. Данные строгого формата (телефон, ИНН, СНИЛС, почта) не остались нигде.
  3. Число строк по таблицам совпадает с исходным.
  4. Разнообразие значений сохранено — одинаковых замен не появилось.
  5. Замены сквозные: одно исходное значение заменено везде одинаково.
  6. Порождённые ИНН и СНИЛС проходят проверку контрольной суммы.

Использование:
    python3 verify.py исходный.sql результат.sql
"""
import re
import sys

from .. import pii_patterns
from ..sql_parse import parse_inserts, unquote
from ..pii_columns import COLUMNS as PII_COLUMNS

# Комментарии, которые myanon дописывает в хвост дампа: содержат время
# выполнения и потому меняются от прогона к прогону. При сравнении двух
# прогонов их надо вычищать, иначе сравнение даёт ложное расхождение.
NOISE = re.compile(r"-- (?:Total execution time|Time spent for anonymization):.*$", re.M)


def strip_noise(text):
    return NOISE.sub("", text)


def _пары(src_path, out_path):
    """
    Карта «было → стало», построенная независимо от слоя подстановки.

    Это намеренное дублирование, а не недосмотр. Раньше проверка брала карту
    у `text_substitute` — того самого модуля, который эти замены и делает.
    Ошибка в построении карты была бы для проверки невидимой: обе стороны
    пользовались бы одним и тем же неверным результатом. Здесь пары
    восстанавливаются заново, сопоставлением дампов по позиции строк.
    """
    src, out = parse_inserts(src_path), parse_inserts(out_path)
    пары = {}
    for table, columns in PII_COLUMNS.items():
        if table not in src or table not in out:
            continue
        s_cols, s_rows = src[table]
        o_cols, o_rows = out[table]
        if len(s_rows) != len(o_rows):
            continue
        for col in columns:
            if col not in s_cols or col not in o_cols:
                continue
            si, oi = s_cols.index(col), o_cols.index(col)
            for s_row, o_row in zip(s_rows, o_rows):
                было, стало = unquote(s_row[si]), unquote(o_row[oi])
                if было == стало or len(было) < 5:
                    continue
                пары.setdefault(было, стало)
    return пары


СВЯЗЬ = re.compile(
    r"CREATE\s+TABLE\s+`(\w+)`(.*?)ENGINE", re.S | re.I)
ССЫЛКА = re.compile(
    r"FOREIGN\s+KEY\s*\(\s*`(\w+)`\s*\)\s*REFERENCES\s+`(\w+)`\s*\(\s*`(\w+)`\s*\)", re.I)


def связи(path):
    """[(таблица, колонка, родитель, колонка_родителя)] — из объявлений схемы."""
    текст = open(path, encoding="utf-8").read()
    out = []
    for m in СВЯЗЬ.finditer(текст):
        таблица, тело = m.group(1), m.group(2)
        for r in ССЫЛКА.finditer(тело):
            out.append((таблица, r.group(1), r.group(2), r.group(3)))
    return out


def сироты(path):
    """
    Строки, у которых значение внешнего ключа не встречается в родительской
    таблице. Проверяется по дампу, а не запросом к базе: дамп загружается с
    FOREIGN_KEY_CHECKS=0, поэтому успешная загрузка ссылочную целостность
    не доказывает — осиротевшая строка прошла бы молча.

    Возвращает (сколько связей проверено, сколько строк осиротело, примеры).
    """
    данные = parse_inserts(path)
    проверено, битые = 0, []
    for таблица, колонка, родитель, ключ in связи(path):
        if таблица not in данные or родитель not in данные:
            continue
        кол_д, стр_д = данные[таблица]
        кол_р, стр_р = данные[родитель]
        if колонка not in кол_д or ключ not in кол_р:
            continue
        i, j = кол_д.index(колонка), кол_р.index(ключ)
        допустимые = {unquote(r[j]) for r in стр_р}
        проверено += 1
        for r in стр_д:
            v = unquote(r[i])
            if v and v.upper() != "NULL" and v not in допустимые:
                битые.append(f"{таблица}.{колонка}={v}")
    return проверено, len(битые), битые[:3]


def итог(есть_что_сравнивать, нет_нарушений):
    """
    Итог одной проверки: True — норма, False — нарушение, None — сравнивать
    было нечего.

    Пустая проверка не может быть успехом: сломанный разбор дампа и чистая
    база дают один и тот же вывод «нарушений ноль». Раньше это правило
    соблюдали три проверки из восьми, а остальные при пустом входе печатали
    «норма» — замерено на дампе чужой схемы, где ни одна колонка из перечня
    не встречается. Отдельное состояние нужно, чтобы отказ не выглядел
    нарушением: «0 из 0» на базе без российских идентификаторов означает не
    утечку, а то, что проверять было нечего.
    """
    if not есть_что_сравнивать:
        return None
    return bool(нет_нарушений)


def column_values(path):
    """Все значения из колонок, объявленных персональными."""
    tables = parse_inserts(path)
    out = set()
    for table, columns in PII_COLUMNS.items():
        if table not in tables:
            continue
        cols, rows = tables[table]
        for col in columns:
            if col not in cols:
                continue
            i = cols.index(col)
            for row in rows:
                v = unquote(row[i])
                if len(v) >= 5:
                    out.add(v)
    return out


def row_counts(path):
    return {t: len(rows) for t, (cols, rows) in parse_inserts(path).items()}


def diversity(path):
    out = {}
    for t, (cols, rows) in parse_inserts(path).items():
        for i, col in enumerate(cols):
            out[f"{t}.{col}"] = len({unquote(r[i]) for r in rows})
    return out


def main(src_path, out_path):
    src = open(src_path, encoding="utf-8").read()
    res = open(out_path, encoding="utf-8").read()

    checks = []

    # 1. Значения из колонок
    col_vals = column_values(src_path)
    leaked_cols = sorted(v for v in col_vals if v in res)
    checks.append(("Персональные данные из колонок в результате",
                   f"{len(leaked_cols)} из {len(col_vals)}",
                   итог(col_vals, not leaked_cols)))

    # 2. Значения строгого формата
    fmt_vals = pii_patterns.find_values(src)
    leaked_fmt = sorted(v for v in fmt_vals if v in res)
    checks.append(("Данные строгого формата в результате",
                   f"{len(leaked_fmt)} из {len(fmt_vals)}",
                   итог(fmt_vals, not leaked_fmt)))

    # 3. Число строк
    a, b = row_counts(src_path), row_counts(out_path)
    checks.append(("Число строк по таблицам",
                   " / ".join(f"{t}:{b.get(t, 0)}" for t in sorted(a)),
                   итог(a, a == b)))

    # 4. Разнообразие
    da, db = diversity(src_path), diversity(out_path)
    lost = {k: (da[k], db[k]) for k in da if k in db and db[k] < da[k]}
    checks.append(("Разнообразие значений",
                   "совпадает везде" if not lost else f"упало в {len(lost)} полях",
                   итог(da, not lost)))

    # 5. Сквозная замена — проверяется прямо, а не по числу уникальных значений.
    #    Для каждой пары «было → стало» число вхождений обязано совпасть:
    #    если исходное значение встречалось трижды, замена обязана встретиться
    #    трижды. Меньше — значит где-то не заменили, больше — значит замена
    #    совпала с посторонним текстом.
    pairs = _пары(src_path, out_path)
    mismatch = []
    for original, replacement in pairs.items():
        was, became = src.count(original), res.count(replacement)
        if was != became:
            mismatch.append((original, was, became))
    checks.append(("Сквозная замена: число вхождений «было» = «стало»",
                   f"пар проверено {len(pairs)}, расхождений {len(mismatch)}",
                   итог(pairs, not mismatch)))

    grown = {k: (da[k], db[k]) for k in da if k in db and db[k] > da[k]}
    checks.append(("Одно значение не получило двух замен",
                   "норма" if not grown else f"нарушено в {len(grown)} полях",
                   итог(da, not grown)))

    # 6. Контрольные суммы порождённых значений
    produced = pii_patterns.find_values(res)
    bad = [v for v, k in produced.items()
           if (k == "inn12" and not pii_patterns.inn12_valid(v))
           or (k == "snils" and not pii_patterns.snils_valid(v))]
    # 7. Ссылочная целостность. Загрузка результата в базу её не доказывает:
    #    дамп идёт с FOREIGN_KEY_CHECKS=0, и осиротевшая строка пройдёт молча.
    связей, осиротело, примеры = сироты(out_path)
    результат = f"связей проверено {связей}, осиротевших строк {осиротело}"
    if примеры:
        результат += f" — {', '.join(примеры)}"
    checks.append(("Ссылочная целостность: внешние ключи указывают на существующие строки",
                   результат, итог(связей, осиротело == 0)))

    checks.append(("Контрольные суммы порождённых ИНН и СНИЛС",
                   f"проверено {len(produced)}, неверных {len(bad)}",
                   итог(produced, not bad)))

    width = max(len(name) for name, _, _ in checks)
    print()
    print(f"{'Проверка'.ljust(width)}  {'Результат'.ljust(24)}  Итог")
    print("-" * (width + 36))
    for name, value, ok in checks:
        метка = "норма" if ok else ("НЕ ПРОВЕРЕНО" if ok is None else "НАРУШЕНО")
        print(f"{name.ljust(width)}  {value.ljust(24)}  {метка}")
    print()

    if leaked_cols[:3]:
        print("Примеры оставшихся значений из колонок:", leaked_cols[:3])
    if leaked_fmt[:3]:
        print("Примеры оставшихся значений строгого формата:", leaked_fmt[:3])
    if mismatch[:3]:
        print("Примеры расхождений по числу вхождений:", mismatch[:3])

    нарушено = [n for n, _, ok in checks if ok is False]
    пусто = [n for n, _, ok in checks if ok is None]
    if нарушено:
        print(f"Провалено проверок: {len(нарушено)}")
    if пусто:
        print(f"Проверок не с чем было сравнивать: {len(пусто)}. "
              "Это не успех: на чужой схеме так выглядит незаполненный перечень "
              "колонок в pii_columns.COLUMNS — заполните его по отчёту сканера.")
    if нарушено or пусто:
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
