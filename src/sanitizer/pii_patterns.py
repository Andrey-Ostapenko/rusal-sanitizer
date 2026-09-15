#!/usr/bin/env python3
"""
Распознавание персональных данных строгого формата и детерминированная
замена с сохранением формата.

Зачем отдельно от подстановки известных значений. Подстановка работает от
значений, взятых из колонок: она может заменить только то, что уже где-то
известно. Телефон или ИНН, написанный в комментарии и не совпадающий ни с
одной строкой таблиц, ей не виден. Такие данные распознаются по формату.

Языковая модель для этого не нужна: у телефона, ИНН, СНИЛС и адреса почты
формат строгий, а у ИНН и СНИЛС есть ещё и контрольные суммы, поэтому
распознавание проверяется арифметически, а не на глаз.

Замена сохраняет формат: телефон заменяется телефоном, ИНН — корректным ИНН
с пересчитанной контрольной суммой. Это удерживает разнообразие данных и не
ломает поля, у которых есть ожидаемая форма.

Детерминированность: замена выводится из HMAC-SHA256 от значения с тем же
секретом, что и у остальной цепочки. Одинаковый вход всегда даёт одинаковый
выход, поэтому сквозная замена не нарушается.
"""
import hashlib
import hmac
import re

# --- Контрольные суммы -------------------------------------------------------
# Веса по приказу ФНС для ИНН и по правилам ПФР для СНИЛС.

INN12_W1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
INN12_W2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
INN10_W = [2, 4, 10, 3, 5, 9, 4, 6, 8]


def _inn_check(digits, weights):
    return sum(d * w for d, w in zip(digits, weights)) % 11 % 10


def _degenerate(digits):
    """Все цифры одинаковые — не идентификатор, а совпадение по форме."""
    return len(set(digits)) == 1


def inn12_valid(s):
    if len(s) != 12 or not s.isdigit() or _degenerate(s):
        return False
    d = [int(c) for c in s]
    return d[10] == _inn_check(d[:10], INN12_W1) and d[11] == _inn_check(d[:11], INN12_W2)


def inn10_valid(s):
    """Оставлен для проверок; в распознавателях ПДн не используется — см. RECOGNIZERS."""
    if len(s) != 10 or not s.isdigit() or _degenerate(s):
        return False
    d = [int(c) for c in s]
    return d[9] == _inn_check(d[:9], INN10_W)


def snils_check(nine):
    """nine — строка из 9 цифр. Возвращает две цифры контрольной суммы."""
    total = sum(int(c) * (9 - i) for i, c in enumerate(nine))
    if total < 100:
        chk = total
    elif total in (100, 101):
        chk = 0
    else:
        chk = total % 101
        if chk in (100, 101):
            chk = 0
    return f"{chk:02d}"


def snils_valid(s):
    digits = re.sub(r"\D", "", s)
    if len(digits) != 11 or _degenerate(digits):
        return False
    return snils_check(digits[:9]) == digits[9:]


# --- Детерминированный источник цифр и букв ----------------------------------

def _stream(value, secret, salt):
    """Байты, однозначно определяемые значением, секретом и назначением."""
    return hmac.new(secret.encode(), (salt + "|" + value).encode("utf-8"), hashlib.sha256).digest()


def _digits(value, secret, salt, n):
    out = ""
    counter = 0
    while len(out) < n:
        block = _stream(value, secret, f"{salt}#{counter}")
        out += "".join(str(b % 10) for b in block)
        counter += 1
    return out[:n]


def _letters(value, secret, salt, n):
    out = ""
    counter = 0
    while len(out) < n:
        block = _stream(value, secret, f"{salt}#{counter}")
        out += "".join(chr(ord("a") + b % 26) for b in block)
        counter += 1
    return out[:n]


# --- Замены с сохранением формата --------------------------------------------

def fake_phone(value, secret):
    """Замена приводится к каноническому виду +7 9XXXXXXXXX.

    Исходное написание (скобки, дефисы, ведущая восьмёрка) не сохраняется:
    номер остаётся номером, но разделители теряются. Осознанный размен —
    сохранять форму каждого написания значит хранить сведения об исходной
    записи, а пользы для читаемости это не даёт.
    """
    return "+79" + _digits(value, secret, "phone", 9)


def fake_inn12(value, secret):
    body = _digits(value, secret, "inn12", 10)
    d = [int(c) for c in body]
    c1 = _inn_check(d, INN12_W1)
    c2 = _inn_check(d + [c1], INN12_W2)
    return body + str(c1) + str(c2)


def fake_inn10(value, secret):
    body = _digits(value, secret, "inn10", 9)
    d = [int(c) for c in body]
    return body + str(_inn_check(d, INN10_W))


def fake_snils(value, secret):
    nine = _digits(value, secret, "snils", 9)
    return f"{nine[0:3]}-{nine[3:6]}-{nine[6:9]} {snils_check(nine)}"


def fake_email(value, secret):
    domain = value.split("@", 1)[1] if "@" in value else "example.com"
    return _letters(value, secret, "email", 10) + "@" + domain


# --- Распознаватели ----------------------------------------------------------
# Каждый: имя, регулярное выражение, дополнительная проверка, генератор замены.

# Телефон: и +7, и ведущая восьмёрка, с разделителями и без. Требование
# девятки в начале кода отсекает основную часть ложных срабатываний —
# одиннадцатизначные номера счетов и заказов под шаблон уже не подходят.
PHONE_RE = re.compile(r"(?<![\d+])(?:\+7|8)[\s\-]?\(?9\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)")

# Адрес почты: локальная часть и домен могут содержать не только латиницу.
# Прежний шаблон принимал только ASCII и молча пропускал адреса с кириллицей —
# в русскоязычной системе это прямая утечка.
EMAIL_RE = re.compile(r"[^\s@'\"(),;<>]+@[^\s@'\"(),;<>]*[^\s@'\"(),;<>.]\.[^\W\d_]{2,}")

RECOGNIZERS = [
    ("snils", re.compile(r"\b\d{3}-\d{3}-\d{3}\s\d{2}\b"), snils_valid, fake_snils),
    ("phone", PHONE_RE, lambda s: True, fake_phone),
    ("email", EMAIL_RE, lambda s: True, fake_email),
    ("inn12", re.compile(r"\b\d{12}\b"), inn12_valid, fake_inn12),
]

# Десятизначный ИНН сознательно не распознаётся как персональные данные:
# он принадлежит юридическому лицу, а не человеку. Плюс у него одна
# контрольная цифра, поэтому случайное десятизначное число (номер заказа,
# счёта) проходит проверку примерно в одном случае из одиннадцати — цена
# ложных срабатываний выше пользы. Если заказчик отнесёт реквизиты компаний
# к конфиденциальным данным (открытый вопрос про состав), распознаватель
# добавляется одной строкой.


def fake_name(value, secret):
    """
    Замена для имени, найденного в свободном тексте.

    У такого имени нет источника в колонках, поэтому замену неоткуда взять —
    её надо породить. Порождается тем же детерминированным механизмом, что и
    остальные замены, и того же вида, что даёт myanon для колонок с ФИО:
    буквенная строка той же длины. Правдоподобное имя здесь недопустимо —
    это были бы синтетические персональные данные.
    """
    return _letters(value, secret, "name", max(5, min(len(value), 20)))


def find_values(text):
    """Возвращает {значение: тип} для всех распознанных вхождений в тексте."""
    found = {}
    for name, pattern, validator, _ in RECOGNIZERS:
        for m in pattern.finditer(text):
            value = m.group(0)
            if value in found:
                continue
            if validator(value):
                found[value] = name
        # порядок распознавателей значим: СНИЛС проверяется до ИНН,
        # иначе его цифровая часть может быть прочитана как другое число
    return found


def build_replacements(text, secret, exclude):
    """
    Карта «найденное значение → замена того же формата».
    exclude — значения, которые уже обрабатываются другим механизмом
    (взяты из колонок); повторно их трогать нельзя.
    """
    generators = {name: gen for name, _, _, gen in RECOGNIZERS}
    mapping = {}
    for value, kind in find_values(text).items():
        if value in exclude:
            continue
        mapping[value] = generators[kind](value, secret)
    return mapping


if __name__ == "__main__":
    import sys
    # Самопроверка контрольных сумм на порождённых значениях:
    # если генератор и проверка согласованы, все проверки обязаны пройти.
    secret = "self-check"
    ok = True
    for i in range(200):
        seed = f"проба-{i}"
        if not inn12_valid(fake_inn12(seed, secret)):
            print(f"ОШИБКА: порождённый ИНН-12 не проходит проверку: {fake_inn12(seed, secret)}")
            ok = False
        if not inn10_valid(fake_inn10(seed, secret)):
            print(f"ОШИБКА: порождённый ИНН-10 не проходит проверку: {fake_inn10(seed, secret)}")
            ok = False
        if not snils_valid(fake_snils(seed, secret)):
            print(f"ОШИБКА: порождённый СНИЛС не проходит проверку: {fake_snils(seed, secret)}")
            ok = False
    print("Самопроверка контрольных сумм:", "пройдена" if ok else "ПРОВАЛЕНА")
    print("Пример ИНН-12:", fake_inn12("Иванова Ольга", secret))
    print("Пример СНИЛС :", fake_snils("Иванова Ольга", secret))
    print("Пример телефона:", fake_phone("Иванова Ольга", secret))
    sys.exit(0 if ok else 1)
