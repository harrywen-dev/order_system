import os
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if not os.getenv('DATABASE_URL'):
    password = (root / '.env').read_text().strip().split('=', 1)[1]
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://lunch:' + password + '@127.0.0.1:5432/lunch'
subprocess.run([str(root / '.venv/bin/uvicorn'), 'app.main:app', '--host', '0.0.0.0', '--port', '8000'], cwd=root / 'backend', check=True)
