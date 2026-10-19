#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# 1. Carrega variáveis de ambiente do .env se existir
if [ -f "$DIR/.env" ]; then
    set -a
    . "$DIR/.env"
    set +a
fi

PHONE_HOST="${PHONE_HOST:-}"
PHONE_PORT="${PHONE_PORT:-8022}"
PHONE_USER="${PHONE_USER:-}"
PHONE_PASS="${PHONE_PASS:-}"
REMOTE_DIR="nexus-termux"

if [ -z "$PHONE_HOST" ] || [ -z "$PHONE_USER" ] || [ -z "$PHONE_PASS" ] || [ "$PHONE_HOST" = "100.x.y.z" ]; then
    echo "====================================================================="
    echo "ERRO: Credenciais de conexão não configuradas!"
    echo "Copie o arquivo .env.example para .env e informe suas credenciais:"
    echo "  cp .env.example .env"
    echo "====================================================================="
    exit 1
fi

echo "=== 1. Executando testes unitários e de integração antes do deploy ==="
if [ -x "$DIR/.venv/bin/python" ]; then
    "$DIR/.venv/bin/python" -m unittest discover -s tests -p "test_*.py"
else
    python3 -m unittest discover -s tests -p "test_*.py"
fi

echo "=== 2. Empacotando arquivos do Dream Hub ==="
TAR_FILE="/tmp/nexus-deploy.tar.gz"
tar --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.db' \
    --exclude='*.db-wal' \
    --exclude='*.db-shm' \
    --exclude='.git' \
    --exclude='.env' \
    -czf "$TAR_FILE" \
    backend frontend services scripts nginx-nexus.conf nginx-nexus-common.conf requirements.txt

echo "=== 3. Enviando pacote para o dispositivo via Tailscale ($PHONE_HOST:$PHONE_PORT) ==="
sshpass -p "$PHONE_PASS" scp -P "$PHONE_PORT" -o StrictHostKeyChecking=no "$TAR_FILE" "$PHONE_USER@$PHONE_HOST:~/"

echo "=== 4. Descompactando e configurando serviços no Termux ==="
sshpass -p "$PHONE_PASS" ssh -p "$PHONE_PORT" -o StrictHostKeyChecking=no "$PHONE_USER@$PHONE_HOST" "bash -s" << 'EOF'
set -eu

mkdir -p "$HOME/nexus-termux"
mkdir -p "$HOME/.local/share/nexus/log/api"
mkdir -p "$HOME/.local/share/nexus/log/nginx"

tar -xzf "$HOME/nexus-deploy.tar.gz" -C "$HOME/nexus-termux"
rm -f "$HOME/nexus-deploy.tar.gz"

chmod +x "$HOME/nexus-termux/scripts/"*
chmod +x "$HOME/nexus-termux/services/"*/* 2>/dev/null || true

# Configura ambiente virtual se não existir
if [ ! -d "$HOME/nexus-termux/.venv" ]; then
    echo "Configurando virtualenv para o Dream Hub..."
    python3 -m venv "$HOME/nexus-termux/.venv"
    "$HOME/nexus-termux/.venv/bin/pip" install -r "$HOME/nexus-termux/requirements.txt"
fi

# Valida sintaxe do Nginx
echo "Validando configuração do Nginx..."
nginx -t -c "$HOME/nexus-termux/nginx-nexus.conf"

# Registra os serviços no supervisor runit do Termux
SV_DIR="$PREFIX/var/service"
if [ -d "$SV_DIR" ]; then
    echo "Registrando serviços nexus-api e nexus-nginx no runit..."
    ln -sfn "$HOME/nexus-termux/services/nexus-api" "$SV_DIR/nexus-api"
    ln -sfn "$HOME/nexus-termux/services/nexus-nginx" "$SV_DIR/nexus-nginx"

    # Notifica o runit para iniciar/recarregar os serviços
    SVDIR="$SV_DIR" sv up nexus-api || true
    SVDIR="$SV_DIR" sv restart nexus-api || true

    SVDIR="$SV_DIR" sv up nexus-nginx || true
    SVDIR="$SV_DIR" sv restart nexus-nginx || true
fi

sleep 2

# Verificação de saúde local no celular
echo "=== Testando conectividade interna ==="
curl -s http://127.0.0.1:8001/api/health || echo "API inicializando..."
curl -I -s http://127.0.0.1:8090/ | head -n 5

EOF

rm -f "$TAR_FILE"
echo "=== Deploy concluído com sucesso! Dream Hub online em http://$PHONE_HOST:8090 ==="
