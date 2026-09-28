#!/usr/bin/env bash
# scripts/start_frontend.sh - Inicia el servidor de desarrollo Vite en puerto 3006
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../frontend" && pwd)"
cd "$DIR"

PORT=3006
HOST="0.0.0.0"

echo "=========================================================="
echo " Iniciando Servidor Vite Frontend SNII Info TlachIA"
echo " Directorio:    $DIR"
echo " Host / Puerto: $HOST:$PORT"
echo " Proxy API:     http://localhost:5016"
echo " URL:           http://localhost:$PORT/"
echo "=========================================================="

exec npm run dev -- --host "$HOST" --port "$PORT"
