#!/usr/bin/env python3
"""
Генератор синтетического mysqldump-совместимого дампа для демонстрации и
тестирования санитизации.

Не требует запущенного MySQL — пишет валидный SQL в том формате, который выдаёт
mysqldump: CREATE TABLE с внешними ключами, затем INSERT с данными. В данных
намеренно заложено: кириллица, повторяющиеся значения ПДн в разных строках
(проверка сквозной замены) и ПДн внутри свободного текста (проверка обработки
неструктурированных полей).

Схема имитирует финансово-кадровый контур: клиенты, сотрудники, заказы, платежи
со связями между ними.

Известное ограничение демо-набора: все ПДн в комментариях порождены из таблицы
customers, поэтому случай «упомянут человек, которого нет ни в одной таблице»
в наборе не представлен — на нём нельзя показать необходимость распознавания.
"""
import os
import random
import sys

try:
    from sanitizer import pii_patterns
except ImportError:  # запуск из исходников, пакет не установлен
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    from sanitizer import pii_patterns

random.seed(42)

FIRST_NAMES_M = ["Александр", "Дмитрий", "Сергей", "Андрей", "Игорь", "Владимир", "Николай", "Михаил"]
FIRST_NAMES_F = ["Елена", "Ольга", "Наталья", "Ирина", "Татьяна", "Марина", "Светлана", "Анна"]
LAST_NAMES = ["Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов", "Попов", "Соколов", "Волков"]
DEPARTMENTS = ["Финансовый отдел", "Бухгалтерия", "Отдел закупок", "Юридический отдел", "IT-отдел"]
CITIES = ["Москва", "Красноярск", "Братск", "Иркутск", "Новокузнецк"]


def full_name(i):
    male = i % 2 == 0
    first = random.choice(FIRST_NAMES_M if male else FIRST_NAMES_F)
    last = random.choice(LAST_NAMES) + ("" if male else "а")
    return f"{last} {first}"


def phone():
    return f"+7{random.randint(9000000000, 9999999999)}"


def inn_fl():
    """ИНН физлица с корректной контрольной суммой — у настоящих она сходится."""
    body = "".join(str(random.randint(0, 9)) for _ in range(10))
    d = [int(c) for c in body]
    c1 = pii_patterns._inn_check(d, pii_patterns.INN12_W1)
    c2 = pii_patterns._inn_check(d + [c1], pii_patterns.INN12_W2)
    return body + str(c1) + str(c2)


def snils():
    """СНИЛС с корректной контрольной суммой."""
    nine = "".join(str(random.randint(0, 9)) for _ in range(9))
    return f"{nine[0:3]}-{nine[3:6]}-{nine[6:9]} {pii_patterns.snils_check(nine)}"


def esc(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


N_CUSTOMERS = 30
N_EMPLOYEES = 15
N_ORDERS = 60
N_PAYMENTS = 60

lines = []
lines.append("-- Синтетический демо-дамп для тестирования санитизации (сгенерирован скриптом, не реальные данные)")
lines.append("SET NAMES utf8mb4;")
lines.append("SET FOREIGN_KEY_CHECKS=0;")
lines.append("")

# --- customers ---
lines.append("DROP TABLE IF EXISTS `customers`;")
lines.append("""CREATE TABLE `customers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `email` varchar(255) NOT NULL,
  `phone` varchar(20) NOT NULL,
  `inn` varchar(12) NOT NULL,
  `city` varchar(100) NOT NULL,
  `address` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

customers = []
for i in range(1, N_CUSTOMERS + 1):
    name = full_name(i)
    email = f"customer{i}@example-mail.ru"
    ph = phone()
    inn = inn_fl()
    city = random.choice(CITIES)
    addr = f"г. {city}, ул. Промышленная, д. {random.randint(1,120)}, кв. {random.randint(1,200)}"
    customers.append((i, name, email, ph, inn, city, addr))

vals = ",\n".join(
    f"({i},'{esc(n)}','{e}','{p}','{inn}','{esc(c)}','{esc(a)}')"
    for (i, n, e, p, inn, c, a) in customers
)
lines.append(f"INSERT INTO `customers` (`id`,`full_name`,`email`,`phone`,`inn`,`city`,`address`) VALUES\n{vals};")
lines.append("")

# --- employees ---
lines.append("DROP TABLE IF EXISTS `employees`;")
lines.append("""CREATE TABLE `employees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `full_name` varchar(255) NOT NULL,
  `department` varchar(100) NOT NULL,
  `snils` varchar(20) NOT NULL,
  `email` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

employees = []
for i in range(1, N_EMPLOYEES + 1):
    name = full_name(i + 100)
    dep = random.choice(DEPARTMENTS)
    sn = snils()
    email = f"{name.split()[1].lower()}.{name.split()[0].lower()}@rusal-demo.local"
    employees.append((i, name, dep, sn, email))

vals = ",\n".join(
    f"({i},'{esc(n)}','{esc(d)}','{s}','{esc(e)}')"
    for (i, n, d, s, e) in employees
)
lines.append(f"INSERT INTO `employees` (`id`,`full_name`,`department`,`snils`,`email`) VALUES\n{vals};")
lines.append("")

# --- orders (FK -> customers, FK -> employees; ПДн внутри свободного текста) ---
lines.append("DROP TABLE IF EXISTS `orders`;")
lines.append("""CREATE TABLE `orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `customer_id` int NOT NULL,
  `manager_id` int NOT NULL,
  `order_date` date NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  `comment` text,
  PRIMARY KEY (`id`),
  KEY `fk_orders_customer` (`customer_id`),
  KEY `fk_orders_manager` (`manager_id`),
  CONSTRAINT `fk_orders_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `fk_orders_manager` FOREIGN KEY (`manager_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

orders = []
comment_templates = [
    "Клиент {name}, тел. {phone}, просил перезвонить после 18:00.",
    "Уточнить адрес доставки: {addr}.",
    "Связаться по email {email} по вопросу счёта.",
    "Стандартный заказ, комментариев нет.",
    "ИНН клиента для документов: {inn}.",
    "Забирал курьер, {third_phone}, пропуск оформлен на месте.",
    "Подрядчик прислал реквизиты, ИНН {third_inn}, счёт проверить до отгрузки.",
    "Копию акта отправили представителю подрядчика на {third_email}.",
]

# Значения третьих лиц: их нет ни в одной таблице, поэтому подстановка
# известных значений до них не дотянется — их ловит распознавание по формату.
def third_phone():
    return f"+7{random.randint(9000000000, 9999999999)}"


def third_inn():
    return inn_fl()


def third_email():
    return f"{random.choice(['kurier','podryad','sklad','logistika'])}{random.randint(1,99)}@partner-demo.ru"
for i in range(1, N_ORDERS + 1):
    cust = random.choice(customers)
    mgr = random.choice(employees)
    date = f"2026-{random.randint(1,8):02d}-{random.randint(1,28):02d}"
    amount = round(random.uniform(1000, 500000), 2)
    tmpl = random.choice(comment_templates)
    comment = tmpl.format(
        name=cust[1], phone=cust[3], addr=cust[6], email=cust[2], inn=cust[4],
        third_phone=third_phone(), third_inn=third_inn(), third_email=third_email(),
    )
    orders.append((i, cust[0], mgr[0], date, amount, comment))

vals = ",\n".join(
    f"({i},{cid},{mid},'{d}',{a},'{esc(c)}')"
    for (i, cid, mid, d, a, c) in orders
)
lines.append(f"INSERT INTO `orders` (`id`,`customer_id`,`manager_id`,`order_date`,`amount`,`comment`) VALUES\n{vals};")
lines.append("")

# --- payments (FK -> orders, FK -> employees) ---
lines.append("DROP TABLE IF EXISTS `payments`;")
lines.append("""CREATE TABLE `payments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `order_id` int NOT NULL,
  `approved_by` int NOT NULL,
  `paid_at` datetime NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_payments_order` (`order_id`),
  KEY `fk_payments_employee` (`approved_by`),
  CONSTRAINT `fk_payments_order` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`),
  CONSTRAINT `fk_payments_employee` FOREIGN KEY (`approved_by`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

payments = []
for i in range(1, N_PAYMENTS + 1):
    order = random.choice(orders)
    emp = random.choice(employees)
    dt = f"2026-{random.randint(1,8):02d}-{random.randint(1,28):02d} {random.randint(8,18):02d}:{random.randint(0,59):02d}:00"
    amount = order[4]
    payments.append((i, order[0], emp[0], dt, amount))

vals = ",\n".join(
    f"({i},{oid},{eid},'{dt}',{a})"
    for (i, oid, eid, dt, a) in payments
)
lines.append(f"INSERT INTO `payments` (`id`,`order_id`,`approved_by`,`paid_at`,`amount`) VALUES\n{vals};")
lines.append("")
lines.append("SET FOREIGN_KEY_CHECKS=1;")

with open("demo_dump.sql", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Готово: demo_dump.sql")
print(f"customers={len(customers)}, employees={len(employees)}, orders={len(orders)}, payments={len(payments)}")
