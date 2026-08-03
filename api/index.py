"""Vercel serverless entrypoint (FastAPI ASGI app).

Serves BOTH the API and the static frontend from one function, so we don't
depend on Vercel's evolving static/rewrite routing (a recent platform change
made internal rewrites pass the destination path, which broke /api routing).
`app.main` mounts the static `public/` dir when WAVES_PUBLIC_DIR is set.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("WAVES_CACHE_DIR", "/tmp/waves-cache")
os.environ.setdefault("WAVES_PUBLIC_DIR", str(ROOT / "public"))

from app.main import app  # noqa: E402

__all__ = ["app"]
