#!/usr/bin/env python3
"""
Проверка детерминированности пайплайна.

Отдельным скриптом, а не однострочником в терминале, по причине из практики:
сравнение писалось вручную три раза подряд и три раза давало ложное
расхождение — не из-за данных, а из-за неверного фильтра служебных
комментариев. Фильтр должен существовать в одном месте и быть проверен.

Проверяет два утверждения:
  1. Тот же ключ -> результат побайтово тот же.
  2. Другой ключ -> результат другой (иначе ключ ни на что не влияет).

Использование:
    python3 check_determinism.py исходный.sql
"""
import os
import subprocess
import sys
import tempfile

from ..paths import SCRIPTS
from .verify import strip_noise

SANITIZE = str(SCRIPTS / "sanitize.sh")


def run(src, out, secret):
    env = dict(os.environ, SANITIZE_SECRET=secret)
    r = subprocess.run([SANITIZE, src, out], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Прогон не удался (ключ «{secret}»):\n{r.stderr}")
    return strip_noise(open(out, encoding="utf-8").read())


def main(src):
    with tempfile.TemporaryDirectory() as tmp:
        a = run(src, os.path.join(tmp, "a.sql"), "kluch-odin")
        b = run(src, os.path.join(tmp, "b.sql"), "kluch-odin")
        c = run(src, os.path.join(tmp, "c.sql"), "kluch-dva")

    same_key_stable = a == b
    other_key_differs = a != c

    print()
    print(f"Тот же ключ -> результат тот же      : {'норма' if same_key_stable else 'НАРУШЕНО'}")
    print(f"Другой ключ -> результат другой      : {'норма' if other_key_differs else 'НАРУШЕНО'}")
    print()

    if not same_key_stable:
        la, lb = a.splitlines(), b.splitlines()
        for i, (x, y) in enumerate(zip(la, lb), 1):
            if x != y:
                print(f"Первое расхождение, строка {i}:")
                print(f"  прогон 1: {x[:120]}")
                print(f"  прогон 2: {y[:120]}")
                break
    if not other_key_differs:
        print("Ключ не влияет на результат — соль не работает.")

    return 0 if (same_key_stable and other_key_differs) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
