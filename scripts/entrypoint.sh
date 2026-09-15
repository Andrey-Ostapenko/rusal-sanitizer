#!/bin/sh
# Сквозной прогон: база на входе -> база на выходе.
#
# Выгрузка исходной базы и загрузка результата выполняются здесь, а не
# руками в терминале: задание говорит «на вход подаём бд — на выход
# получаем бд», и цепочка должна быть замкнутой без ручных шагов.

set -eu

HOST="${MYSQL_HOST:-mysql}"
USER="${MYSQL_USER:-root}"
PASS="${MYSQL_PASSWORD:-rootpass}"
SRC_DB="${SOURCE_DB:-sanitizer_demo}"
DST_DB="${TARGET_DB:-sanitizer_final}"
WORK=/work

# MySQL генерирует самоподписанный сертификат, а клиент MariaDB (именно он
# ставится в Debian как default-mysql-client) по умолчанию проверяет цепочку
# и отказывается соединяться. Отключаем ТОЛЬКО проверку сертификата, а не
# шифрование: соединение внутри частной сети контейнеров остаётся закрытым.
SSL="--ssl-verify-server-cert=0"

: "${SANITIZE_SECRET:?переменная SANITIZE_SECRET не задана}"

mkdir -p "$WORK"

echo "Жду базу $HOST..."
i=0
until mysqladmin $SSL ping -h "$HOST" -u "$USER" -p"$PASS" --silent 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo "База не поднялась за 60 попыток" >&2; exit 1; }
  sleep 2
done

echo "Готовлю исходные данные..."
cd "$WORK" && python3 /app/scripts/generate_demo_dump.py
mysql $SSL -h "$HOST" -u "$USER" -p"$PASS" \
      -e "DROP DATABASE IF EXISTS \`$SRC_DB\`; CREATE DATABASE \`$SRC_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql $SSL -h "$HOST" -u "$USER" -p"$PASS" "$SRC_DB" < "$WORK/demo_dump.sql"
echo "Исходная база $SRC_DB загружена."

echo
echo "Выгружаю базу в дамп..."
# --hex-blob обязателен: без него двоичные колонки попадают в дамп как сырые
# байты, и разбор падает на не-UTF-8. Найдено на публичной базе sakila, где
# есть staff.picture типа BLOB.
mysqldump $SSL -h "$HOST" -u "$USER" -p"$PASS" \
          --skip-extended-insert --complete-insert --no-tablespaces --hex-blob \
          "$SRC_DB" > "$WORK/source.sql"

echo "Санитизация..."
/app/scripts/sanitize.sh "$WORK/source.sql" "$WORK/clean.sql"

echo
echo "Загружаю результат в базу $DST_DB..."
mysql $SSL -h "$HOST" -u "$USER" -p"$PASS" \
      -e "DROP DATABASE IF EXISTS \`$DST_DB\`; CREATE DATABASE \`$DST_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql $SSL -h "$HOST" -u "$USER" -p"$PASS" "$DST_DB" < "$WORK/clean.sql"

echo
echo "=== Проверка результата ==="
python3 -m sanitizer.checks.verify "$WORK/source.sql" "$WORK/clean.sql"

echo "=== Проверка детерминированности ==="
python3 -m sanitizer.checks.determinism "$WORK/source.sql"

echo
echo "Готово. Сравнить базы можно запросами к $SRC_DB и $DST_DB."
