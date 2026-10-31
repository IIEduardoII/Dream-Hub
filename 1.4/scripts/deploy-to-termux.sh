#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f "$DIR/.env" ]; then
    set -a
    source "$DIR/.env"
    set +a
fi

PHONE_HOST="${TERMUX_HOST:-${PHONE_HOST:-}}"
PHONE_PORT="${TERMUX_PORT:-${PHONE_PORT:-8022}}"
PHONE_USER="${TERMUX_USER:-${PHONE_USER:-}}"
PHONE_PASS="${TERMUX_PASS:-${PHONE_PASS:-}}"
REMOTE_DUCKDNS_DOMAIN=""

if [ -n "${DUCKDNS_DOMAIN:-}" ] && [ "$DUCKDNS_DOMAIN" != "seu-subdominio.duckdns.org" ]; then
    CLEAN_DOMAIN="${DUCKDNS_DOMAIN#*://}"
    CLEAN_DOMAIN="${CLEAN_DOMAIN%%/*}"
    CLEAN_DOMAIN="${CLEAN_DOMAIN%%:*}"
    CLEAN_DOMAIN="$(echo "$CLEAN_DOMAIN" | tr -d '[:space:]')"
    if [[ "$CLEAN_DOMAIN" != *.duckdns.org ]]; then
        CLEAN_DOMAIN="${CLEAN_DOMAIN}.duckdns.org"
    fi
    REMOTE_DUCKDNS_DOMAIN="$CLEAN_DOMAIN"
fi

if [ -z "$PHONE_HOST" ] || [ -z "$PHONE_USER" ] || [ -z "$PHONE_PASS" ]; then
    echo "[ERRO] Configure TERMUX_HOST, TERMUX_PORT, TERMUX_USER e TERMUX_PASS no arquivo .env"
    exit 1
fi

echo "=== 1. Executando testes unitários e de integração antes do deploy ==="
"$DIR/.venv/bin/python" -m unittest discover -s tests -p "test_*.py"

echo "=== 2. Empacotando arquivos do Dream Hub v1.3 ==="
TAR_FILE="/tmp/nexus-deploy.tar.gz"
tar --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    --exclude='.env' \
    --exclude='certs' \
    --exclude='data' \
    --exclude='uploads' \
    --exclude='node_modules' \
    --exclude='.git' \
    -czf "$TAR_FILE" \
    backend frontend services scripts nginx-nexus.conf nginx-nexus-common.conf requirements.txt

echo "=== 3. Enviando pacote para o celular via Tailscale ($PHONE_HOST:$PHONE_PORT) ==="
sshpass -p "$PHONE_PASS" scp -P "$PHONE_PORT" -o StrictHostKeyChecking=no "$TAR_FILE" "$PHONE_USER@$PHONE_HOST:~/"

echo "=== 4. Executando backup preventivo, proteção TLS, merge e atualização no Termux ==="
sshpass -p "$PHONE_PASS" ssh -p "$PHONE_PORT" -o StrictHostKeyChecking=no "$PHONE_USER@$PHONE_HOST" \
    "REMOTE_DUCKDNS_DOMAIN='$REMOTE_DUCKDNS_DOMAIN' PHONE_HOST='$PHONE_HOST' bash -s" << 'EOF'
set -eu

BACKUP_TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HOME/backups-deploy-$BACKUP_TS"
mkdir -p "$BACKUP_DIR"

echo "Criando backup de segurança em $BACKUP_DIR..."
if [ -f "$HOME/nexus-termux/nexus.db" ]; then
    cp "$HOME/nexus-termux/nexus.db"* "$BACKUP_DIR/" 2>/dev/null || true
    echo "  Backup de nexus.db concluído."
fi
if [ -f "$HOME/.local/share/ritmo/ritmo.sqlite3" ]; then
    cp "$HOME/.local/share/ritmo/ritmo.sqlite3"* "$BACKUP_DIR/" 2>/dev/null || true
    echo "  Backup de ritmo.sqlite3 concluído."
fi

mkdir -p "$HOME/nexus-termux"
mkdir -p "$HOME/nexus-termux/uploads"
mkdir -p "$HOME/nexus-termux/certs"
mkdir -p "$HOME/.local/share/nexus/log/api"
mkdir -p "$HOME/.local/share/nexus/log/nginx"

tar -xzf "$HOME/nexus-deploy.tar.gz" -C "$HOME/nexus-termux"
rm -f "$HOME/nexus-deploy.tar.gz"

chmod +x "$HOME/nexus-termux/scripts/"*
chmod +x "$HOME/nexus-termux/services/"*/* 2>/dev/null || true

# [RNF02] Proteção estrita do certificado TLS (jamais sobrescreve Let's Encrypt existente)
if [ ! -s "$HOME/nexus-termux/certs/server.crt" ] || [ ! -s "$HOME/nexus-termux/certs/server.key" ]; then
    echo "Gerando certificado TLS autoassinado inicial em ~/nexus-termux/certs/..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$HOME/nexus-termux/certs/server.key" \
        -out "$HOME/nexus-termux/certs/server.crt" \
        -subj "/CN=${PHONE_HOST}" >/dev/null 2>&1
else
    echo "Preservando certificado TLS existente em ~/nexus-termux/certs/..."
fi

# Injeta o domínio DuckDNS no server_name do Nginx (ou usa o domínio já persistido no Termux)
ACTIVE_DOMAIN=""
if [ -f "$HOME/nexus-termux/.duckdns_domain" ]; then
    ACTIVE_DOMAIN=$(cat "$HOME/nexus-termux/.duckdns_domain" | tr -d '[:space:]')
elif [ -n "${REMOTE_DUCKDNS_DOMAIN:-}" ]; then
    ACTIVE_DOMAIN="$REMOTE_DUCKDNS_DOMAIN"
fi

if [ -n "$ACTIVE_DOMAIN" ]; then
    sed -i "s/__DUCKDNS_DOMAIN__/${ACTIVE_DOMAIN}/g" "$HOME/nexus-termux/nginx-nexus.conf"
else
    sed -i "s/__DUCKDNS_DOMAIN__ //g" "$HOME/nexus-termux/nginx-nexus.conf"
fi

# Configura ambiente virtual se não existir
if [ ! -d "$HOME/nexus-termux/.venv" ]; then
    echo "Configurando virtualenv para o Nexus..."
    if [ -d "$HOME/ritmo-termux/.venv" ]; then
        ln -s "$HOME/ritmo-termux/.venv" "$HOME/nexus-termux/.venv"
    else
        python3 -m venv "$HOME/nexus-termux/.venv"
        "$HOME/nexus-termux/.venv/bin/pip" install -r "$HOME/nexus-termux/requirements.txt"
    fi
fi

PYTHON_BIN="$HOME/nexus-termux/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "=== Executando unificação/migração idempotente do banco de dados ==="
"$PYTHON_BIN" "$HOME/nexus-termux/scripts/merge_ritmo_data.py" \
    "$HOME/.local/share/ritmo/ritmo.sqlite3" \
    "$HOME/nexus-termux/nexus.db"

# Valida sintaxe do Nginx
echo "Validando configuração do Nginx..."
nginx -t -c "$HOME/nexus-termux/nginx-nexus.conf"

# Registra e reinicia os serviços no supervisor runit do Termux
SV_DIR="${PREFIX:-/data/data/com.termux/files/usr}/var/service"
if [ -d "$SV_DIR" ]; then
    echo "Reiniciando serviços nexus-api e nexus-nginx no runit..."
    ln -sfn "$HOME/nexus-termux/services/nexus-api" "$SV_DIR/nexus-api"
    ln -sfn "$HOME/nexus-termux/services/nexus-nginx" "$SV_DIR/nexus-nginx"

    pkill -f "nexus-termux.*gunicorn" 2>/dev/null || true
    sleep 1
    SVDIR="$SV_DIR" sv restart nexus-api || SVDIR="$SV_DIR" sv up nexus-api || true
    SVDIR="$SV_DIR" sv restart nexus-nginx || SVDIR="$SV_DIR" sv up nexus-nginx || true
    # Orphan nginx masters (started outside runit) keep ports bound with stale config: reload them.
    for pid in $(pgrep -x nginx 2>/dev/null); do
        if [ "$(ps -o ppid= -p "$pid" | tr -d ' ')" = "1" ]; then kill -HUP "$pid" 2>/dev/null || true; fi
    done
    SVDIR="$SV_DIR" sv-enable sshd 2>/dev/null || true
fi

sleep 3

# Verificação de saúde local no celular (HTTP 8090 e HTTPS 8445)
echo "=== Testando conectividade interna (HTTP :8090 e HTTPS :8445) ==="
curl -s http://127.0.0.1:8001/api/health || echo "API inicializando..."
echo ""
curl -I -s http://127.0.0.1:8090/ | head -n 5
curl -k -I -s https://127.0.0.1:8445/ | head -n 5

EOF

rm -f "$TAR_FILE"
echo "=== Deploy concluído com sucesso! Dream Hub online em http://$PHONE_HOST:8090 e https://$PHONE_HOST:8445 ==="
