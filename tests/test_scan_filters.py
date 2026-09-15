"""
Детерминированные фильтры сканера — что не доходит до модели и почему.

Этот путь ронял данные дважды, оба раза на чужой схеме:
  * обычный `KEY` считался ключевым — фамилия под индексом не санитизировалась;
  * перечень типов знал `blob`, но не `mediumblob` — колонка с фотографией
    показывалась модели и могла получить `texthash`.
Оба случая закреплены здесь на форме объявления из sakila. Модель заглушена:
проверяются именно фильтры, а не её ответ.
"""
import tempfile
import os

from sanitizer import scan_columns

ДАМП = """CREATE TABLE `staff` (
  `staff_id` tinyint NOT NULL,
  `last_name` varchar(45) NOT NULL,
  `email` varchar(50) DEFAULT NULL,
  `picture` mediumblob DEFAULT NULL,
  `bio` text,
  PRIMARY KEY (`staff_id`),
  KEY `idx_staff_last_name` (`last_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO `staff` (`staff_id`, `last_name`, `email`, `picture`, `bio`) VALUES (1,'Hillyer','mike@sakila.invalid',NULL,'Works nights');
"""


def отброшенное(monkeypatch):
    monkeypatch.setattr(scan_columns, "_вызов", lambda prompt, timeout=180: "[]")
    f = tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8")
    f.write(ДАМП)
    f.close()
    try:
        _, отброшено = scan_columns.scan(f.name)
    finally:
        os.unlink(f.name)
    return {(т, к): п for т, к, п in отброшено}


def test_двоичная_колонка_не_доходит_до_модели(monkeypatch):
    карта = отброшенное(monkeypatch)
    assert ("staff", "picture") in карта
    assert "двоичные" in карта[("staff", "picture")]


def test_свободный_текст_отброшен_с_другой_причиной(monkeypatch):
    карта = отброшенное(monkeypatch)
    assert "свободный текст" in карта[("staff", "bio")]


def test_фамилия_под_обычным_индексом_доходит_до_модели(monkeypatch):
    карта = отброшенное(monkeypatch)
    assert ("staff", "last_name") not in карта


def test_первичный_ключ_не_доходит(monkeypatch):
    карта = отброшенное(monkeypatch)
    assert "ключевая" in карта[("staff", "staff_id")]
