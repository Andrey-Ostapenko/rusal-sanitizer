#!/usr/bin/env python3
"""
Разбор INSERT-ов из дампа MySQL.

Вынесено в отдельный модуль после отказа: прежний разборщик писался под
формат нашего генератора (значения со следующей строки после VALUES) и
молча не понимал вывод настоящего mysqldump, где значения стоят на той же
строке. Проверки при этом отрабатывали вхолостую и рапортовали «норма».

Поэтому здесь не регулярное выражение, а посимвольный разбор с учётом
кавычек и экранирования: точка с запятой внутри строкового значения не
должна обрываться за конец выражения.

Поддерживаются оба вида:
    INSERT INTO `t` (`a`,`b`) VALUES\\n(1,'x'),\\n(2,'y');
    INSERT INTO `t` (`a`, `b`) VALUES (1,'x');
"""
import re

HEADER = re.compile(r"INSERT\s+INTO\s+`(\w+)`\s*\(([^)]*)\)\s*VALUES\s*", re.I)


def _scan_to_semicolon(text, start):
    """Конец выражения — точка с запятой вне строкового литерала."""
    i, in_str, esc = start, False, False
    while i < len(text):
        c = text[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == "'":
            in_str = not in_str
        elif c == ";" and not in_str:
            return i
        i += 1
    return len(text)


def _split_rows(body):
    """Разбивает «(...),(...)» на список списков значений."""
    rows, i = [], 0
    while i < len(body):
        if body[i] != "(":
            i += 1
            continue
        depth, j, in_str, esc = 1, i + 1, False, False
        while j < len(body) and depth:
            c = body[j]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == "'":
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            j += 1
        rows.append(_split_values(body[i + 1:j - 1]))
        i = j
    return rows


def _split_values(raw):
    vals, cur, in_str, esc = [], "", False, False
    for c in raw:
        if esc:
            cur += c
            esc = False
        elif c == "\\":
            cur += c
            esc = True
        elif c == "'":
            in_str = not in_str
            cur += c
        elif c == "," and not in_str:
            vals.append(cur.strip())
            cur = ""
        else:
            cur += c
    if cur.strip():
        vals.append(cur.strip())
    return vals


def parse_inserts(path):
    """{таблица: (список колонок, список строк-списков значений)}"""
    text = open(path, encoding="utf-8").read()
    out = {}
    for m in HEADER.finditer(text):
        table = m.group(1)
        cols = [c.strip().strip("`") for c in m.group(2).split(",")]
        end = _scan_to_semicolon(text, m.end())
        rows = _split_rows(text[m.end():end])
        if table in out:
            # mysqldump пишет по одному INSERT на строку — накапливаем.
            out[table][1].extend(rows)
        else:
            out[table] = (cols, rows)
    return out


def unquote(v):
    return v[1:-1] if len(v) >= 2 and v.startswith("'") and v.endswith("'") else v
