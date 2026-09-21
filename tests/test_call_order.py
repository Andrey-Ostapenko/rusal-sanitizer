"""
Раздел «Порядок вызова» в README и AGENTS.md сверяется со скриптами.

Порядок шагов живёт в entrypoint.sh и sanitize.sh. Документ, который его
пересказывает, устаревает молча, если его не проверять.
"""
from sanitizer import paths

ПРОГОН = ["python3 -m pytest", "generate_demo_dump.py", "mysqldump",
          "scripts/sanitize.sh", "sanitizer.checks.verify", "sanitizer.checks.determinism"]
САНИТИЗАЦИЯ = ['"$BIN" -f', "sanitizer.text_substitute"]
В_ДОКУМЕНТЕ = ["pytest", "generate_demo_dump.py", "mysqldump", "sanitize.sh", "myanon",
               "sanitizer.text_substitute", "sanitizer.checks.verify",
               "sanitizer.checks.determinism", "sanitizer.scan_columns",
               "sanitizer.config_builder"]


def по_порядку(текст, шаги):
    позиции = [текст.find(шаг) for шаг in шаги]
    assert -1 not in позиции, f"не найден шаг: {шаги[позиции.index(-1)]}"
    assert позиции == sorted(позиции), f"шаги не по порядку: {шаги}"


def код(имя):
    строки = (paths.КОРЕНЬ / "scripts" / имя).read_text(encoding="utf-8").splitlines()
    return "\n".join(s for s in строки if not s.lstrip().startswith("#"))


def раздел(имя):
    текст = (paths.КОРЕНЬ / имя).read_text(encoding="utf-8")
    начало = текст.index("Порядок вызова")
    return текст[начало:текст.index("\n#", начало)]


def test_скрипты():
    по_порядку(код("entrypoint.sh"), ПРОГОН)
    по_порядку(код("sanitize.sh"), САНИТИЗАЦИЯ)


def test_документы():
    for имя in ("README.md", "AGENTS.md"):
        по_порядку(раздел(имя), В_ДОКУМЕНТЕ)
