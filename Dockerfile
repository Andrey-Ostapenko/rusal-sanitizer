# Образ санитизатора: собирает myanon из исходников и несёт наши доработки.
#
# Сборка вынесена в образ намеренно. На хосте она требует четырёх пакетов
# (autoconf, automake, pkg-config, bison) и обхода того, что системный flex
# в macOS генерирует несовместимый код. В образе этих сложностей нет.
#
# myanon клонируется по закреплённому коммиту, а не копируется из рабочей
# папки: иначе репозиторий невозможно склонировать и собрать — сборка
# молча зависела бы от каталога, которого у проверяющего нет.

FROM debian:bookworm-slim AS build

ARG MYANON_REPO=https://github.com/ppomes/myanon.git
ARG MYANON_COMMIT=5eaafb182cbdc58c36677dff512ee956317677c1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential autoconf automake pkg-config flex bison \
        git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone "$MYANON_REPO" /src/myanon \
    && cd /src/myanon \
    && git checkout --detach "$MYANON_COMMIT" \
    && ./autogen.sh && ./configure && make

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/myanon/main/myanon /usr/local/bin/myanon

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src    ./src
COPY scripts ./scripts
COPY config ./config
COPY data   ./data

RUN pip install --no-cache-dir . && chmod +x /app/scripts/*.sh

# Пакет установлен в site-packages, поэтому путь к данным от него не
# вычисляется — задаётся явно. См. src/sanitizer/paths.py.
ENV SANITIZER_DATA=/app/data \
    SANITIZER_SCRIPTS=/app/scripts \
    SANITIZER_CONFIG=/app/config

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
