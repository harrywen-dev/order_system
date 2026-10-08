#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f compose.yaml -f compose.cloud.yaml up -d --wait --wait-timeout 60 db
if ! curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then
    nohup .venv/bin/python scripts/run_backend.py > /tmp/lunch-api.log 2>&1 &
fi
for attempt in {1..30}; do
    if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then break; fi
    sleep 1
done
curl --fail --silent http://127.0.0.1:8000/api/health
if ! curl --fail --silent http://127.0.0.1:5173/ >/dev/null; then
    nohup npm run dev --prefix frontend > /tmp/lunch-web.log 2>&1 &
fi
for attempt in {1..30}; do
    if curl --fail --silent http://127.0.0.1:5173/api/health; then exit 0; fi
    sleep 1
done
exit 1
