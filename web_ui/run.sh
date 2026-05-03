#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
VENV="$HERE/venv"
if [ ! -d "$VENV" ]; then
  echo "Virtualenv not found. Creating..."
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
  "$VENV/bin/pip" install -r "$HERE/../requirements.txt"
fi

PORT=${PORT:-8080}
echo "Starting web UI on http://0.0.0.0:${PORT}"
exec "$VENV/bin/python" - <<PY
from web_ui.app import app
app.run(host='0.0.0.0', port=int(${PORT}))
PY
