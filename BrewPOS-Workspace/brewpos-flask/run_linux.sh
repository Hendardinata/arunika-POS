#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Virtual environment detection
if [ -f "$SCRIPT_DIR/venv_linux/bin/activate" ]; then
    PYTHON="$SCRIPT_DIR/venv_linux/bin/python"
    GUNICORN="$SCRIPT_DIR/venv_linux/bin/gunicorn"
elif [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/activate"
    GUNICORN="$SCRIPT_DIR/venv/bin/gunicorn"
else
    echo "[!] Linux Virtual Environment not found. Creating venv_linux..."
    python3 -m venv --copies venv_linux
    ./venv_linux/bin/pip install -r requirements.txt
    ./venv_linux/bin/pip install gunicorn
    PYTHON="$SCRIPT_DIR/venv_linux/bin/python"
    GUNICORN="$SCRIPT_DIR/venv_linux/bin/gunicorn"
fi

# Load environment variables from .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PORT="${PORT:-3001}"
MODE="${1:-dev}"

echo "=========================================="
echo " Arunika-POS Flask Server (Linux)"
echo " Mode: $MODE | Port: $PORT"
echo "=========================================="

if [ "$MODE" = "prod" ] || [ "$MODE" = "production" ] || [ "$MODE" = "host" ]; then
    echo "[*] Starting production server with Gunicorn on 0.0.0.0:$PORT..."
    exec "$GUNICORN" -w 4 -b "0.0.0.0:$PORT" --timeout 120 "run:app"
elif [ "$MODE" = "seed" ]; then
    echo "[*] Running database seed..."
    exec "$PYTHON" seed.py
elif [ "$MODE" = "test" ]; then
    echo "[*] Running pytest suite..."
    exec "$SCRIPT_DIR/venv_linux/bin/pytest"
else
    echo "[*] Starting development server on 0.0.0.0:$PORT..."
    exec "$PYTHON" run.py
fi
