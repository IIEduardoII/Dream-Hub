#!/usr/bin/env sh
# Rotina de Backup Automático a Quente do Dream Hub ([RF14] / Seção 6.3)
set -eu

DB_PATH="${NEXUS_DB:-$HOME/nexus-termux/nexus.db}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/storage/shared/DreamHubBackups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TARGET="$BACKUP_DIR/dreamhub_$TIMESTAMP.db"

if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_PATH" ".backup '$TARGET'"
else
    python3 -c "import sqlite3; src=sqlite3.connect('$DB_PATH'); dst=sqlite3.connect('$TARGET'); src.backup(dst); dst.close(); src.close()"
fi

# Remove backups com mais de 30 dias para poupar armazenamento flash
find "$BACKUP_DIR" -name "dreamhub_*.db" -type f -mtime +30 -delete 2>/dev/null || true
echo "[OK] Backup a quente gerado com sucesso em: $TARGET"
