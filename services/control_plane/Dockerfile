FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services services
COPY shared shared
COPY scenarios scenarios

RUN useradd --create-home --uid 10001 lab \
    && mkdir -p /var/lib/a2a-mcp/artifacts \
    && chown -R 10001:10001 /var/lib/a2a-mcp
USER 10001:10001

WORKDIR /app/services/control_plane
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
