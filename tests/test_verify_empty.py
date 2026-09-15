"""
Пустая проверка не имеет права выглядеть успехом.

Сломанный разбор дампа и по-настоящему чистая база дают один и тот же вывод
«нарушений ноль». Раньше это правило соблюдали три проверки из восьми, а
остальные при пустом входе печатали «норма» — видно на дампе чужой схемы,
где ни одна колонка из `pii_columns.COLUMNS` не встречается.

Здесь закреплено поведение на такой схеме: отказ, отдельная метка
«НЕ ПРОВЕРЕНО» вместо «НАРУШЕНО», и объяснение причины в итоге.
"""
import os
import tempfile

from sanitizer.checks import verify

ЧУЖАЯ_СХЕМА = """CREATE TABLE `actor` (
  `actor_id` smallint NOT NULL,
  `first_name` varchar(45) NOT NULL,
  `last_name` varchar(45) NOT NULL,
  PRIMARY KEY (`actor_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO `actor` (`actor_id`, `first_name`, `last_name`) VALUES (1,'PENELOPE','GUINESS');
INSERT INTO `actor` (`actor_id`, `first_name`, `last_name`) VALUES (2,'NICK','WAHLBERG');
"""


def прогон():
    пути = []
    for _ in range(2):
        f = tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8")
        f.write(ЧУЖАЯ_СХЕМА)
        f.close()
        пути.append(f.name)
    try:
        return verify.main(*пути)
    finally:
        for п in пути:
            os.unlink(п)


def test_чужая_схема_не_даёт_успеха(capsys):
    код = прогон()
    вывод = capsys.readouterr().out
    assert код != 0, "проверка без единого сравнения не может быть успехом"
    assert "Все проверки пройдены" not in вывод


def test_пустая_проверка_помечена_отдельно(capsys):
    прогон()
    вывод = capsys.readouterr().out
    assert "НЕ ПРОВЕРЕНО" in вывод, "пустую проверку надо отличать от нарушения"
    assert "НАРУШЕНО" not in вывод, "нечего сравнивать — это не нарушение"
    assert "pii_columns.COLUMNS" in вывод, "итог должен называть причину"


def test_итог_различает_три_состояния():
    assert verify.итог([], True) is None
    assert verify.итог([1], True) is True
    assert verify.итог([1], False) is False
