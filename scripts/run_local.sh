#!/usr/bin/env bash
# One-command local deployment WITHOUT Docker (verified path in this environment).
# Starts the FastAPI backend (:8010) and a static server for the frontend (:8080).
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-.venv/bin}"
echo "Starting API on http://127.0.0.1:8010 ..."
PYTHONPATH=backend "$VENV/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 &
API_PID=$!

echo "Starting static frontend on http://127.0.0.1:8080 ..."
"$VENV/python" -m http.server 8080 --bind 127.0.0.1 &
WEB_PID=$!

echo ""
echo "  App:  http://127.0.0.1:8080/frontend/index.html"
echo "  API:  http://127.0.0.1:8010/api/health"
echo "  Docs: http://127.0.0.1:8010/docs"
echo ""
echo "Ctrl-C to stop."
trap "kill $API_PID $WEB_PID 2>/dev/null || true" INT TERM
wait
