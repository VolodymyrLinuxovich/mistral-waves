"""Vercel catch-all serverless entrypoint (ASGI).

Vercel's internal rewrites now pass the rewritten DESTINATION path to the app,
which broke a `/api/(.*) -> /api/index` rewrite (FastAPI then saw `/api/index`).
A catch-all function `api/[...path].py` receives the ORIGINAL request path, so
FastAPI routes (`/api/health`, `/api/heatwave-footprint`, ...) match directly —
no rewrite needed.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("WAVES_CACHE_DIR", "/tmp/waves-cache")

from app.main import app  # noqa: E402

__all__ = ["app"]
