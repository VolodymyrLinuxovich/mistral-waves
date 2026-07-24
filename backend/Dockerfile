# Backend API image. Python 3.12 (pinned for parity; dev host runs 3.14).
FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Application code + config + the compact processed data needed at runtime.
COPY backend/ ./backend/
COPY config/ ./config/
COPY data/processed/ ./data/processed/
COPY data/boundaries/ ./data/boundaries/
COPY data/demo/ ./data/demo/

ENV PYTHONPATH=/app/backend
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8010/api/health').status==200 else sys.exit(1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
