#!/usr/bin/env bash
# Assemble the static site into public/ for Vercel (served at root).
# Frontend source stays in frontend/; public/ is the materialized deploy output.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf public && mkdir -p public/data
cp frontend/index.html public/index.html
cp frontend/config.js public/config.js 2>/dev/null || cp frontend/config.example.js public/config.js
cp -r data/boundaries public/data/boundaries
echo "public/ assembled:"; find public -type f | sort
