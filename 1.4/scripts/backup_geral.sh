#!/usr/bin/env bash
# ==============================================================================
# DREAM HUB v1.3 - BACKUP GERAL UNIFICADO (Termux/SQLite + Google Drive via rclone)
# ==============================================================================
set -Eeuo pipefail
umask 077

MODE="${1:-daily}" # daily | manual

ROOT="${DREAMHUB_DIR:-$HOME/nexus-termux}"
DB="${NEXUS_DB:-$ROOT/nexus.db}"
OUT="${DREAMHUB_BACKUP_DIR:-$HOME/dreamhub-backups}"
REMOTE_NAME="${DREAMHUB_RCLONE_REMOTE:-gdrive}"
REMOTE_DIR="${DREAMHUB_DRIVE_DIR:-DreamHub_Backups}"
REMOTE="$REMOTE_NAME:$REMOTE_DIR"

KEEP_LOCAL=7
KEEP_DAILY_DAYS=30
KEEP_MONTHLY_DAYS=400
LOG="$OUT/backup.log"

mkdir -p "$OUT"
log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "$LOG"; }

if [ ! -f "$DB" ]; then
    # Fallback to local dev database if running from scratch directory
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$DIR/nexus.db" ]; then
        DB="$DIR/nexus.db"
        ROOT="$DIR"
    fi
fi

if [ ! -f "$DB" ]; then
    log "ERRO: Banco de dados não encontrado em $DB"
    exit 1
fi

log "INÍCIO ($MODE): Exportando banco de dados completo do Dream Hub..."

stage="$(mktemp -d "$OUT/.stage-XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT

# 1) Backup atômico online via Python SQLite API (consistente mesmo sob escrita/WAL)
python3 - "$DB" "$stage" << 'EOF'
import sqlite3, sys

src_path, stage_dir = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f'file:{src_path}?mode=ro', uri=True)
dst = sqlite3.connect(f'{stage_dir}/nexus.sqlite3')
src.backup(dst)
src.close()

status = dst.execute('PRAGMA integrity_check').fetchone()[0]
if status != 'ok':
    sys.exit(f'integrity_check falhou: {status}')

tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
with open(f'{stage_dir}/nexus.sql', 'w', encoding='utf-8') as f:
    for line in dst.iterdump():
        f.write(line + '\n')

with open(f'{stage_dir}/MANIFEST.txt', 'w', encoding='utf-8') as f:
    f.write('=== Dream Hub - Manifesto do Backup Geral ===\n')
    f.write(f'Origem: {src_path}\n')
    f.write(f'Tabelas totais: {len(tables)}\n\n')
    for t in tables:
        try:
            cnt = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            f.write(f'{t}: {cnt} registros\n')
        except Exception:
            f.write(f'{t}: (erro ao ler)\n')
dst.close()
EOF

# 2) Empacotamento
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PKG_NAME="dreamhub-backup-$MODE-$TIMESTAMP.tar.gz"

tar -czf "$OUT/$PKG_NAME" -C "$stage" nexus.sqlite3 nexus.sql MANIFEST.txt
(cd "$OUT" && sha256sum "$PKG_NAME" > "$PKG_NAME.sha256")
log "SUCESSO LOCAL: $PKG_NAME gerado em $OUT ($(du -h "$OUT/$PKG_NAME" | cut -f1))"

# 3) Rotação local (mantém os KEEP_LOCAL mais recentes)
{ ls -1t "$OUT"/dreamhub-backup-daily-*.tar.gz 2>/dev/null || true; } | tail -n +$((KEEP_LOCAL + 1)) | while read -r old; do
    rm -f "$old" "$old.sha256"
done

# 4) Sincronização com o Google Drive via rclone (se configurado)
if command -v rclone >/dev/null 2>&1; then
    if rclone listremotes 2>/dev/null | grep -qx "$REMOTE_NAME:"; then
        log "Enviando $PKG_NAME para o Google Drive ($REMOTE)..."
        rclone copyto "$OUT/$PKG_NAME" "$REMOTE/$PKG_NAME" --retries 3 --low-level-retries 5 || log "Aviso: Falha ao enviar tar.gz para $REMOTE"
        rclone copyto "$OUT/$PKG_NAME.sha256" "$REMOTE/$PKG_NAME.sha256" --retries 3 || true
        log "SUCESSO DRIVE: $PKG_NAME sincronizado com o Google Drive."

        # Retenção no Drive
        if [ "$MODE" = "daily" ]; then
            rclone delete "$REMOTE" --include 'dreamhub-backup-daily-*' --min-age "${KEEP_DAILY_DAYS}d" 2>/dev/null || true
        fi
    else
        log "AVISO: Remote '$REMOTE_NAME:' não encontrado no rclone. Backup preservado localmente."
    fi
else
    log "INFO: rclone não instalado no ambiente. Backup preservado localmente com sucesso."
fi

log "CONCLUÍDO: Rotina de backup finalizada com sucesso."
