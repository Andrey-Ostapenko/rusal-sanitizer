"""Пути к данным, прибитые к расположению пакета, а не к текущему каталогу.

До перекладки умолчания выглядели как "control_set.json" и разрешались
относительно текущего каталога: модуль работал из корня проекта и молча
падал отовсюду ещё. Здесь путь считается от файла пакета, поэтому
перемещение каталогов не меняет поведение незаметно.

Переопределяется окружением — этим пользуется образ, где данные лежат
в /app/data, а пакет установлен в site-packages.
"""

import os
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("SANITIZER_DATA", str(КОРЕНЬ / "data")))
SCRIPTS = Path(os.environ.get("SANITIZER_SCRIPTS", str(КОРЕНЬ / "scripts")))
CONFIG = Path(os.environ.get("SANITIZER_CONFIG", str(КОРЕНЬ / "config")))


def данные(имя):
    """Путь к файлу демонстрационных или эталонных данных."""
    return str(DATA / имя)
