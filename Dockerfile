FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

RUN useradd --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY config.py bot.py ./
COPY handlers/ ./handlers/
COPY services/ ./services/

USER appuser

CMD ["python", "bot.py"]
