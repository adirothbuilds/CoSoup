ARG POSTGRES_IMAGE=postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652
FROM ${POSTGRES_IMAGE} AS pgtools

FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN --mount=type=secret,id=build_ca,required=false,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then printf 'Acquire::https::CaInfo "/run/secrets/build_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; fi; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=0 -o Acquire::https::Timeout=20 -o APT::Update::Error-Mode=any update \
    && apt-get install -y --no-install-recommends \
    ca-certificates libpq5 libldap-2.5-0 libgssapi-krb5-2 liblz4-1 libzstd1 \
    tesseract-ocr poppler-utils bubblewrap && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-build-ca
COPY --from=pgtools /usr/lib/postgresql/17/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgtools /usr/lib/postgresql/17/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=pgtools /usr/lib/x86_64-linux-gnu/libpq.so.5.18 /usr/lib/x86_64-linux-gnu/libpq.so.5.18
RUN ln -sf libpq.so.5.18 /usr/lib/x86_64-linux-gnu/libpq.so.5
COPY requirements.txt /app/requirements.txt
COPY apps/server/requirements.txt /app/apps/server/requirements.txt
RUN --mount=type=secret,id=build_ca,required=false,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python -m pip install -r apps/server/requirements.txt && python -m pip check
COPY stock_scanner /app/stock_scanner
COPY config.json scanner.py /app/
COPY apps /app/apps
RUN chmod -R a+rX /app && groupadd -g 10001 scanner && useradd -u 10001 -g scanner -M scanner
USER 10001:10001
ENTRYPOINT ["python", "-m", "apps.server"]
CMD ["api"]

FROM base AS codex
USER root
# Dedicated terminal image; the host's Codex installation/configuration is never mounted.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=secret,id=build_ca,required=false,mode=0444 \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install -g @openai/codex@0.160.0 --ignore-scripts \
    && codex --version \
    && npm cache clean --force
USER 10001:10001
