#!/usr/bin/env bash
# =============================================================================
# backup_neo4j.sh
# Respaldo de Neo4j 5.23 (Community, Docker) con dos modalidades:
#
#   ./backup_neo4j.sh            → dump offline (más confiable, ~1 min downtime)
#   ./backup_neo4j.sh --online   → export APOC Cypher (sin downtime)
#
# Los respaldos se guardan en NEO4J_BACKUP_DIR con fecha en el nombre.
# Se conservan los últimos KEEP_BACKUPS respaldos automáticamente.
# =============================================================================

set -euo pipefail

# ── Configuración ─────────────────────────────────────────────────────────────
CONTAINER="neo4j"
IMAGE="neo4j:5.23"
NEO4J_DATA="/mnt/expansion/dockers_drives/neo4j_data"
NEO4J_IMPORT="/mnt/expansion/dockers_drives/neo4j_import"
NEO4J_BACKUP_DIR="/mnt/expansion/dockers_drives/neo4j_backups"
DATABASE="neo4j"
KEEP_BACKUPS=7          # Número de respaldos a conservar
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# ── Ayuda ─────────────────────────────────────────────────────────────────────
usage() {
  echo "Uso: $0 [--online] [--help]"
  echo ""
  echo "  Sin flags  : dump offline via neo4j-admin (recomendado, ~1 min downtime)"
  echo "  --online   : export APOC Cypher (sin downtime, requiere Neo4j corriendo)"
  exit 0
}

ONLINE=false
for arg in "$@"; do
  case $arg in
    --online) ONLINE=true ;;
    --help|-h) usage ;;
  esac
done

mkdir -p "$NEO4J_BACKUP_DIR"

# ── Función: Backup offline con neo4j-admin dump ───────────────────────────────
backup_offline() {
  local DUMP_FILE="neo4j_${TIMESTAMP}.dump"
  local DUMP_PATH="${NEO4J_BACKUP_DIR}/${DUMP_FILE}"

  echo "🛑 Deteniendo contenedor ${CONTAINER}..."
  docker stop "$CONTAINER"

  echo "📦 Generando dump: ${DUMP_FILE} ..."
  docker run --rm \
    -v "${NEO4J_DATA}:/data" \
    -v "${NEO4J_BACKUP_DIR}:/backups" \
    "$IMAGE" \
    neo4j-admin database dump "$DATABASE" \
      --to-path=/backups/ \
      --overwrite-destination=true

  # neo4j-admin dump genera el archivo con nombre fijo; lo renombramos
  if [ -f "${NEO4J_BACKUP_DIR}/${DATABASE}.dump" ]; then
    mv "${NEO4J_BACKUP_DIR}/${DATABASE}.dump" "$DUMP_PATH"
  fi

  echo "🚀 Reiniciando contenedor ${CONTAINER}..."
  docker start "$CONTAINER"

  echo "✅ Dump guardado en: ${DUMP_PATH}"
  echo "   Tamaño: $(du -sh "$DUMP_PATH" | cut -f1)"
}

# ── Función: Backup online con APOC ───────────────────────────────────────────
backup_online() {
  local EXPORT_FILE="backup_${TIMESTAMP}.cypher"
  local NEO4J_URL="${NEO4J_URL:-bolt://localhost:7687}"
  local NEO4J_USER="${NEO4J_USER:-neo4j}"
  local NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"

  echo "📤 Exportando con APOC (sin downtime)..."
  echo "   Archivo destino: ${NEO4J_IMPORT}/${EXPORT_FILE}"

  # Ejecutar la exportación vía cypher-shell dentro del contenedor
  docker exec "$CONTAINER" \
    cypher-shell \
      -u "$NEO4J_USER" \
      -p "$NEO4J_PASSWORD" \
      --format plain \
      "CALL apoc.export.cypher.all('${EXPORT_FILE}', {format: 'cypher-shell', useOptimizations: {type: 'UNWIND_BATCH', unwindBatchSize: 500}}) YIELD file, batches, source, format, nodes, relationships, properties, time, rows, batchSize RETURN file, nodes, relationships, time;"

  # Mover el archivo generado (queda en neo4j_import) al directorio de backups
  if [ -f "${NEO4J_IMPORT}/${EXPORT_FILE}" ]; then
    mv "${NEO4J_IMPORT}/${EXPORT_FILE}" "${NEO4J_BACKUP_DIR}/${EXPORT_FILE}"
    # Comprimir para ahorrar espacio
    gzip "${NEO4J_BACKUP_DIR}/${EXPORT_FILE}"
    echo "✅ Export guardado en: ${NEO4J_BACKUP_DIR}/${EXPORT_FILE}.gz"
    echo "   Tamaño: $(du -sh "${NEO4J_BACKUP_DIR}/${EXPORT_FILE}.gz" | cut -f1)"
  else
    echo "⚠️  No se encontró el archivo exportado. Revisa los logs de APOC."
    exit 1
  fi
}

# ── Limpieza: conservar solo los últimos N respaldos ──────────────────────────
cleanup_old_backups() {
  echo "🧹 Conservando los últimos ${KEEP_BACKUPS} respaldos..."
  local count
  count=$(ls -1 "${NEO4J_BACKUP_DIR}" | wc -l)
  if [ "$count" -gt "$KEEP_BACKUPS" ]; then
    ls -1t "${NEO4J_BACKUP_DIR}" | tail -n +"$((KEEP_BACKUPS + 1))" | \
      xargs -I{} rm -f "${NEO4J_BACKUP_DIR}/{}"
    echo "   Eliminados: $((count - KEEP_BACKUPS)) respaldo(s) antiguo(s)."
  else
    echo "   Sin respaldos a eliminar ($count / ${KEEP_BACKUPS})."
  fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
echo "======================================================"
echo "  Neo4j Backup — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Modo: $([ "$ONLINE" = true ] && echo 'ONLINE (APOC)' || echo 'OFFLINE (neo4j-admin dump)')"
echo "======================================================"

if [ "$ONLINE" = true ]; then
  backup_online
else
  backup_offline
fi

cleanup_old_backups

echo ""
echo "📁 Respaldos disponibles en: ${NEO4J_BACKUP_DIR}"
ls -lh "${NEO4J_BACKUP_DIR}" | tail -"$KEEP_BACKUPS"
echo "======================================================"
