#!/usr/bin/env python3
"""
Замер языковой модели на наших собственных данных.

Проверяются обе работы, которые модель может выполнять по критерию задания
«использовал ллм для логичных замен»:

  Задача А — найти в комментарии ФИО. Эталон известен точно: комментарии
  порождены из таблицы клиентов, поэтому для каждой строки мы знаем, есть
  там имя и какое. Считается полнота (сколько нашла) и точность (сколько
  выдумала).

  Задача Б — придумать правдоподобную замену ФИО. Оценивается формально:
  замена должна быть непохожа на исходное, состоять из двух слов на
  кириллице и не повторяться для разных исходных значений.

Модель вызывается через шлюз Docker Model Runner, совместимый с OpenAI API.

Использование:
    python3 scripts/bench_model.py [имя_модели] [строк_для_задачи_А] [ФИО_для_задачи_Б]
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

try:
    from sanitizer import paths
    from sanitizer.sql_parse import parse_inserts, unquote
except ImportError:  # запуск из исходников, пакет не установлен
    import os
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    from sanitizer import paths
    from sanitizer.sql_parse import parse_inserts, unquote

# Адрес модели — только из окружения, как во всех остальных модулях.
# Прибитый адрес здесь нарушал собственное правило проекта: замер шёл бы
# мимо LLM_ENDPOINT и молча бил в localhost.
ENDPOINT = os.environ.get(
    "LLM_ENDPOINT", "http://localhost:12434/engines/v1/chat/completions")
DEFAULT_MODEL = "ai/qwen3:14b-q4_K_M"

PROMPT_FIND = (
    "/no_think "
    "Ты обрабатываешь комментарии из корпоративной базы данных.\n"
    "Найди в тексте фамилии и имена людей.\n"
    "Ответь только JSON-массивом найденных ФИО, без пояснений. "
    "Если людей в тексте нет, ответь []\n\n"
    "Текст: {text}"
)

PROMPT_REPLACE = (
    "/no_think "
    "Замени русское ФИО на другое, вымышленное, того же рода и вида "
    "(фамилия и имя). Ответь только новым ФИО, без пояснений.\n\n"
    "ФИО: {name}"
)


def ask(model, prompt, timeout=180):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    text = data["choices"][0]["message"]["content"]
    # У рассуждающих моделей ответ может предваряться блоком размышлений.
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def load_ground_truth(dump=None):
    dump = dump or paths.данные("demo_dump.sql")
    """Комментарии и точный перечень ФИО, которые в них есть."""
    tables = parse_inserts(dump)
    cols, rows = tables["customers"]
    ci, ni = cols.index("id"), cols.index("full_name")
    names = {unquote(r[ni]) for r in rows}

    cols, rows = tables["orders"]
    comment_i = cols.index("comment")
    out = []
    for r in rows:
        text = unquote(r[comment_i])
        present = sorted(n for n in names if n in text)
        out.append((text, present))
    return out


def normalize(s):
    return re.sub(r"[^\w]+", " ", s.lower()).strip()


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    cases = load_ground_truth()[:limit]
    with_name = sum(1 for _, p in cases if p)
    print(f"Модель: {model}")
    print(f"Строк в замере: {len(cases)}, из них с ФИО: {with_name}\n")

    tp = fp = fn = 0
    errors = 0
    for text, expected in cases:
        try:
            raw = ask(model, PROMPT_FIND.format(text=text))
        except (urllib.error.URLError, OSError) as e:
            errors += 1
            print(f"  ошибка вызова: {e}")
            continue
        m = re.search(r"\[.*?\]", raw, re.S)
        try:
            got = json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            got = []
        # Модель возвращает ФИО либо строкой, либо разложенным по полям
        # («фамилия», «имя»). Сверяем как множество слов: это устойчиво и к
        # разбиению на поля, и к порядку слов.
        flat = []
        for g in got:
            if isinstance(g, str):
                flat.append(g)
            elif isinstance(g, dict):
                flat.append(" ".join(str(v) for v in g.values() if isinstance(v, str)))
        got_n = {frozenset(normalize(g).split()) for g in flat if g.strip()}
        exp_n = {frozenset(normalize(e).split()) for e in expected}
        tp += len(got_n & exp_n)
        fp += len(got_n - exp_n)
        fn += len(exp_n - got_n)

    print("--- Задача А: поиск ФИО в тексте ---")
    print(f"  найдено верно      : {tp}")
    print(f"  выдумано лишнего   : {fp}")
    print(f"  пропущено          : {fn}")
    if tp + fn:
        print(f"  полнота            : {tp / (tp + fn):.0%}")
    if tp + fp:
        print(f"  точность           : {tp / (tp + fp):.0%}")
    if errors:
        print(f"  вызовов с ошибкой  : {errors}")

    print("\n--- Задача Б: правдоподобная замена ---")
    # Сколько имён брать — из argv, по умолчанию все из выборки. Пять, как было
    # раньше, слишком мало: схлопывание разнообразия видно только на десятках.
    сколько = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    # Имена берём из колонки клиентов, а не из эталона комментариев: в
    # комментариях их всего три, а схлопывание разнообразия видно только
    # на десятках. Это тот же источник, на котором замер делался изначально.
    таблицы = parse_inserts(paths.данные("demo_dump.sql"))
    колонки, строки = таблицы["customers"]
    i = колонки.index("full_name")
    sample = sorted({unquote(r[i]) for r in строки})[:сколько]
    исходные_фамилии = {n.split()[0] for n in sample}
    print(f"  исходных ФИО: {len(sample)}, среди них фамилий: {len(исходные_фамилии)}")
    пары = {}
    seen = {}
    for name in sample:
        try:
            got = ask(model, PROMPT_REPLACE.format(name=name)).strip().strip('"')
        except (urllib.error.URLError, OSError) as e:
            print(f"  {name} -> ошибка: {e}")
            continue
        words = got.split()
        ok_shape = len(words) == 2 and all(re.fullmatch(r"[А-ЯЁ][а-яё\-]+", w) for w in words)
        ok_diff = normalize(got) != normalize(name)
        ok_uniq = got not in seen
        seen[got] = name
        marks = "".join([
            "форма ок " if ok_shape else "ФОРМА НЕ ТА ",
            "отличается " if ok_diff else "СОВПАЛО ",
            "уникально" if ok_uniq else "ПОВТОР",
        ])
        print(f"  {name:22} -> {got:22} [{marks}]")
        пары[name] = got

    # Главное число замера: сколько РАЗНЫХ значений осталось на выходе.
    выданные = set(пары.values())
    фамилии = {v.split()[0] for v in выданные if v.split()}
    print(f"\n  было {len(sample)} ФИО с {len(исходные_фамилии)} фамилиями "
          f"-> стало {len(выданные)} ФИО с {len(фамилии)} фамилиями")
    отчёт = {
        "модель": model,
        "исходных_ФИО": len(sample),
        "исходных_фамилий": len(исходные_фамилии),
        "различных_замен": len(выданные),
        "различных_фамилий_в_заменах": len(фамилии),
        "пары": пары,
    }
    with open("bench_replace_report.json", "w", encoding="utf-8") as fh:
        json.dump(отчёт, fh, ensure_ascii=False, indent=1)
    print("  отчёт: bench_replace_report.json")


if __name__ == "__main__":
    main()
