FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY services/ ./services/

USER appuser

CMD ["python", "bot.py"]
