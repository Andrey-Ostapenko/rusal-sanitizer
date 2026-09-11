#!/usr/bin/env python3
"""
Правдоподобные замены ФИО с участием языковой модели.

Разделение ролей, полученное из замеров (см. claude/poc_run_4_model.md):

  Модель ПОРОЖДАЕТ пул правдоподобных ФИО — по одному вызову на род.
  Детерминированный хеш РАСПРЕДЕЛЯЕТ пул по исходным значениям.

Почему не «модель придумывает замену на каждое значение»: замерено, что при
независимых вызовах она тяготеет к частотным именам — 20 исходных ФИО с 10
фамилиями превратились в 7 ФИО с 4 фамилиями, два разных клиента слились в
одного. Это ломает требование сохранить разнообразие данных. При раздаче
хешем разнообразие гарантировано по построению, а не поведением модели.

Пул кешируется в файл: модель нужна один раз, дальше прогон идёт без неё и
воспроизводится на машине без доступа к модели.
"""
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request

ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://localhost:12434/engines/v1/chat/completions")
MODEL = os.environ.get("LLM_MODEL", "ai/qwen3:14b-q4_K_M")
# Путь к пулу отсчитывается от самого файла, а не от текущего каталога:
# sanitize.sh запускается из разных мест (с хоста, из контейнера), и привязка
# к cwd приводила бы к «пул не найден» в зависимости от места запуска.
POOL_FILE = os.environ.get(
    "NAME_POOL_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "name_pool.json"))
POOL_SIZE = int(os.environ.get("NAME_POOL_SIZE", "60"))


def _ask(prompt, timeout=600):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,   # для пула нужна вариативность, а не повторяемость
        "max_tokens": 1500,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    text = data["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def _request_pool(gender, count):
    slovo = "мужских" if gender == "m" else "женских"
    prompt = (
        f"/no_think Придумай {count} РАЗНЫХ вымышленных русских {slovo} ФИО "
        f"в формате «Фамилия Имя». Все фамилии должны быть разными. "
        f"Не используй самые частотные фамилии подряд, разнообразь. "
        f"Ответь только JSON-массивом строк, без пояснений."
    )
    raw = _ask(prompt)
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        raise ValueError(f"модель вернула не JSON: {raw[:200]}")
    names = [x.strip() for x in json.loads(m.group(0)) if isinstance(x, str)]
    return [n for n in names if len(n.split()) == 2]


def build_pool(path=POOL_FILE, size=POOL_SIZE):
    """Порождает пул моделью и сохраняет в файл. Требует доступной модели."""
    pool = {}
    for g in ("m", "f"):
        got, tries = [], 0
        while len(set(got)) < size and tries < 4:
            got.extend(_request_pool(g, size))
            tries += 1
        uniq = sorted(set(got))
        if len(uniq) < 10:
            raise ValueError(f"модель дала слишком мало имён для рода {g}: {len(uniq)}")
        pool[g] = uniq
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "pool": pool}, f, ensure_ascii=False, indent=1)
    return pool


def load_pool(path=POOL_FILE):
    """Читает пул из файла. Модель при этом не нужна."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["pool"]


def gender_of(fio):
    """Род по окончанию фамилии. Женские русские фамилии оканчиваются на -а/-ая."""
    sur = fio.split()[0] if fio.split() else fio
    return "f" if sur.endswith(("а", "ая")) else "m"


def assign(values, pool, secret):
    """
    Раздаёт пул исходным значениям детерминированно и без совпадений.

    Значение определяет позицию в пуле через HMAC от значения с секретом.
    Если позиция занята другим исходным значением, берётся следующая свободная —
    это гарантирует, что два разных клиента не станут одним человеком.

    Обход в отсортированном порядке: иначе результат зависел бы от порядка
    перебора и перестал быть воспроизводимым.

    Имена, совпадающие с исходными, из пула исключаются. Модель порождает
    правдоподобные русские ФИО, а исходные данные — тоже правдоподобные русские
    ФИО, поэтому пересечение неизбежно (замерено: «Иванова Ольга» оказалась и
    в пуле, и в базе). Без исключения замена одного человека давала бы имя
    другого реального человека из той же базы: исходное значение оставалось бы
    видимым в результате, а число его вхождений менялось.
    """
    value_set = set(values)
    # Фильтрация вынесена из цикла: набор исходных значений один на весь прогон,
    # поэтому и отфильтрованный пул один — позиции в нём должны совпадать у всех
    # значений, иначе занятые позиции считались бы по разным спискам.
    free = {}
    for g in ("m", "f"):
        free[g] = [n for n in (pool.get(g) or pool["m"]) if n not in value_set]
        if not free[g]:
            raise ValueError(f"после исключения совпадений пул рода {g} пуст")

    taken = {"m": {}, "f": {}}
    mapping = {}
    for value in sorted(values):
        g = gender_of(value)
        names = free[g]
        h = hmac.new(secret.encode(), ("name|" + value).encode("utf-8"), hashlib.sha256).digest()
        start = int.from_bytes(h[:8], "big") % len(names)
        for step in range(len(names)):
            idx = (start + step) % len(names)
            if idx not in taken[g]:
                taken[g][idx] = value
                mapping[value] = names[idx]
                break
        else:
            raise ValueError(
                f"пул рода {g} исчерпан: значений больше, чем имён ({len(names)}). "
                f"Увеличьте NAME_POOL_SIZE."
            )
    return mapping


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        p = build_pool()
        print(f"Пул создан: мужских {len(p['m'])}, женских {len(p['f'])} -> {POOL_FILE}")
    else:
        pool = load_pool()
        print(f"Пул: мужских {len(pool['m'])}, женских {len(pool['f'])}")
        print("Примеры:", pool["m"][:3], pool["f"][:3])
