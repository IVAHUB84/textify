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
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /bin/false appuser

ENV HF_HOME=/opt/models

WORKDIR /app

COPY --from=builder /install /usr/local

RUN python -c "import cv2"

COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY middlewares/ ./middlewares/
COPY services/ ./services/

RUN mkdir -p /app/data && chown appuser:appuser /app/data

RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" \
    && chmod -R a+rX /opt/models

ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

USER appuser

CMD ["python", "bot.py"]
