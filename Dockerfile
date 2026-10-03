FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QWEN_SETTINGS=/data/settings.json \
    QWEN_HOST=0.0.0.0 \
    QWEN_PORT=8787

WORKDIR /app

COPY . /app

RUN pip install . && \
    chmod +x /app/docker-entrypoint.sh /app/qwen-gen.sh && \
    mkdir -p /data

EXPOSE 8787
VOLUME ["/data"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD []
