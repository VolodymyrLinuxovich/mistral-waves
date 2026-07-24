"""Vercel serverless entrypoint. Exposes the FastAPI ASGI app as `app`.

Vercel's @vercel/python builder detects the ASGI `app` and serves it. All /api/*
requests are rewritten to this function (see vercel.json); FastAPI routes on the
original path (/api/health, /api/forecast, ...).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Serverless FS is read-only except /tmp — point the cache there.
os.environ.setdefault("WAVES_CACHE_DIR", "/tmp/waves-cache")

from app.main import app  # noqa: E402  (import after sys.path/env setup)

__all__ = ["app"]
