#!/usr/bin/env bash
# 将本地 Streamlit (8501) 暴露到公网。需本机已运行: streamlit run app.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8501}"

if ! lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "端口 $PORT 无服务。请先: cd \"$ROOT\" && source .venv/bin/activate && streamlit run app.py"
  exit 1
fi

if [[ -x "$ROOT/bin/cloudflared" ]]; then
  exec "$ROOT/bin/cloudflared" tunnel --url "http://127.0.0.1:$PORT"
fi

if command -v cloudflared >/dev/null 2>&1; then
  exec cloudflared tunnel --url "http://127.0.0.1:$PORT"
fi

echo "未找到 cloudflared，改用 localtunnel…"
exec npx --yes localtunnel --port "$PORT"
