"""
README сверяется с кодом машинно, а не глазами.

За один день ручная сверка провалилась трижды, и дважды расхождение внёс тот,
кто перед этим её и делал. Числа в документе — это утверждения о коде и
данных, значит их можно проверять так же, как всё остальное.

Каждый тест вычисляет число из источника истины и требует, чтобы ровно оно
стояло в README. Поменялся код — падает тест, а не рецензент это находит.

Источники истины разные намеренно: часть считается из данных и кода прямо
здесь, часть берётся из сохранённых отчётов в `measurements/` — тех самых,
на которые README ссылается.
"""
import inspect
import json

from sanitizer import paths, pii_patterns
from sanitizer.checks import verify

README = (paths.КОРЕНЬ / "README.md").read_text(encoding="utf-8")
ДАМП = paths.данные("demo_dump.sql")


def отчёт(имя):
    return json.loads((paths.КОРЕНЬ / "measurements" / имя).read_text(encoding="utf-8"))


def test_значений_из_колонок():
    n = len(verify.column_values(ДАМП))
    assert f"0 из {n}" in README, f"в демо-базе {n} значений из колонок, README говорит иначе"
    assert f"пар проверено {n}" in README


def test_значений_строгого_формата():
    n = len(pii_patterns.find_values(open(ДАМП, encoding="utf-8").read()))
    assert f"0 из {n}" in README
    assert f"проверено {n}, неверных 0" in README


def test_число_строк_по_таблицам():
    c = verify.row_counts(ДАМП)
    assert f"customers:{c['customers']} / employees:{c['employees']}" in README
    assert (f"{c['customers']} клиентов, {c['employees']} сотрудников, "
            f"{c['orders']} заказов, {c['payments']} платежей") in README


def test_число_проверок():
    сколько = inspect.getsource(verify.main).count("checks.append")
    словом = {7: "семь", 8: "восемь", 9: "девять"}[сколько]
    assert f"{словом} проверок" in README, f"проверок {сколько}, а README называет другое число"
    схема = (paths.КОРЕНЬ / "docs" / "architecture.archify.json").read_text(encoding="utf-8")
    assert f"{словом}, машинные" in схема, "схема архитектуры отстала от кода"


def test_сканер_на_демо_базе():
    d = отчёт("scan_demo.json")
    assert f"принято: {len(d['находки'])}" in README or \
           f"{len(d['находки'])} колонки принято, {len(d['отброшено'])} отклонено" in README


def test_сканер_на_sakila():
    оф, зер = отчёт("scan_sakila_official.json"), отчёт("scan_sakila_mirror.json")
    assert len(оф["находки"]) == len(зер["находки"]), \
        "после правки образцов оба дистрибутива обязаны давать одно и то же"
    assert f"{len(оф['находки'])} принято, {len(оф['отброшено'])} отклонено" in README


def test_замер_детектора():
    d = отчёт("detect_report.json")
    assert f"Найдено верно  : {d['найдено_верно']}" in README
    assert f"Время          : {int(d['секунд'])} с на {d['записей']} записей" in README
    assert f"Точность       : {d['точность']:.2f}" in README


def test_схлопывание_разнообразия():
    d = отчёт("bench_replace.json")
    assert (f"{d['исходных_ФИО']} исходных ФИО с {d['исходных_фамилий']} разными") in README
    assert (f"{d['различных_замен']} ФИО с {d['различных_фамилий_в_заменах']} фамилиями") in README


def test_нет_ссылок_на_несуществующие_файлы():
    import re
    пропустить = ("http", "#", "mailto:")
    битые = []
    for имя in set(re.findall(r"\[[^\]]+\]\(([^)]+)\)", README)):
        if имя.startswith(пропустить):
            continue
        if not (paths.КОРЕНЬ / имя.split("#")[0]).exists():
            битые.append(имя)
    assert not битые, f"README ссылается на то, чего нет: {битые}"
