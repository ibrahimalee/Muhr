FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY registry/requirements.txt /app/registry-requirements.txt
RUN pip install --no-cache-dir -r /app/registry-requirements.txt

COPY shared /app/shared
COPY registry /app/registry
# The live-demo endpoint runs the buyer flow in-process (DEMO wallet only).
COPY buyer_mcp/__init__.py buyer_mcp/budget.py buyer_mcp/flow.py buyer_mcp/lightning.py buyer_mcp/registry_client.py /app/buyer_mcp/

# Matches docker-compose: DATABASE_URL=sqlite:////app/data/muhr.db
RUN mkdir -p /app/data && chown 65534:65534 /app/data
USER 65534:65534
ENV HOME=/tmp

EXPOSE 8000

CMD ["uvicorn", "registry.main:app", "--host", "0.0.0.0", "--port", "8000"]
