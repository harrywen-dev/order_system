#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci --prefix frontend --cache /workspace/.npm-cache
python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
if not p.exists():
    p.write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\n')
    p.chmod(0o600)
PY
