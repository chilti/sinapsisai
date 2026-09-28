#!/usr/bin/env bash
# scripts/start_api.sh - Inicia el servidor FastAPI de SNII Info TlachIA en puerto 5006
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

PYTHON_BIN="/home/ambientesPy/revistaslatam/bin/python3"
PORT=5016
HOST="0.0.0.0"

echo "=========================================================="
echo " Iniciando Servidor API SNII Info TlachIA (FastAPI)"
echo " Entorno Python: $PYTHON_BIN"
echo " Directorio:     $DIR"
echo " Host / Puerto:  $HOST:$PORT"
echo " Documentación:  http://localhost:$PORT/docs"
echo "=========================================================="

exec "$PYTHON_BIN" -m uvicorn api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 2 \
    --log-level info
