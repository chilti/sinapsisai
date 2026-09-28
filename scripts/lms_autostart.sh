#!/usr/bin/env bash
set -euo pipefail

# Iniciar servidor LM Studio si no está corriendo
/usr/local/bin/lms server start

# Esperar a que el servidor esté activo (máximo 15 segundos)
for i in {1..15}; do
    if /usr/local/bin/lms server status 2>&1 | grep -q "running on port"; then
        break
    fi
    sleep 1
done

# Cargar el modelo openai/gpt-oss-20b en memoria GPU si no está cargado
if ! /usr/local/bin/lms ps 2>&1 | grep -q "openai/gpt-oss-20b"; then
    echo "Cargando modelo openai/gpt-oss-20b con GPU máxima..."
    /usr/local/bin/lms load openai/gpt-oss-20b --gpu max -y
fi

echo "LM Studio Server y modelo openai/gpt-oss-20b listos."
