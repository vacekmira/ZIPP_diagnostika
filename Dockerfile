FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
RUN python -m pip install --upgrade pip && python -m pip install .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws", "websockets-sansio", "--ws-ping-interval", "20", "--ws-ping-timeout", "20", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
