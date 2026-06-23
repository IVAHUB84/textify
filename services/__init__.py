import asyncio

# Глобальный лимит на тяжёлые ЛОКАЛЬНЫЕ операции (OCR и локальный Whisper).
# На слабом сервере (1 vCPU / 1.9 GB) параллельные локальные задачи создают
# риск OOM/перегрузки CPU. CF-вызовы (ASR, LLM) под этот семафор не попадают.
# См. ADR-010, Решение 3.
HEAVY_LOCAL_CONCURRENCY = 1
HEAVY_LOCAL_SEMAPHORE = asyncio.Semaphore(HEAVY_LOCAL_CONCURRENCY)
