FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app     PORT=8002

COPY sellers/classifier/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY sellers /app/sellers

# Unprivileged user; also used by the --network=none worker (python -m sellers.worker).
USER 65534:65534
EXPOSE 8002

CMD ["sh", "-c", "exec uvicorn sellers.classifier.app:app --host 0.0.0.0 --port ${PORT}"]
