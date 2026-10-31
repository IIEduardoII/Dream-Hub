#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "[ERRO] Arquivo .env nao encontrado em $PROJECT_ROOT/.env"
    echo "       Copie .env.example para .env e preencha DUCKDNS_DOMAIN e DUCKDNS_TOKEN."
    exit 1
fi

# Carrega variaveis locais
set -a
source "$PROJECT_ROOT/.env"
set +a

TERMUX_HOST="${TERMUX_HOST:-${PHONE_HOST:-}}"
TERMUX_PORT="${TERMUX_PORT:-${PHONE_PORT:-8022}}"
TERMUX_USER="${TERMUX_USER:-${PHONE_USER:-}}"
TERMUX_PASS="${TERMUX_PASS:-${PHONE_PASS:-}}"

if [ -z "$TERMUX_HOST" ] || [ -z "$TERMUX_USER" ] || [ -z "$TERMUX_PASS" ]; then
    echo "[ERRO] Defina TERMUX_HOST, TERMUX_PORT, TERMUX_USER e TERMUX_PASS no arquivo .env"
    exit 1
fi

if [ -z "${DUCKDNS_DOMAIN:-}" ] || [ -z "${DUCKDNS_TOKEN:-}" ] \
   || [ "$DUCKDNS_TOKEN" = "cole_seu_token_do_duckdns_aqui" ] \
   || [ "$DUCKDNS_DOMAIN" = "seu-subdominio.duckdns.org" ]; then
    echo "[ERRO] Preencha DUCKDNS_DOMAIN e DUCKDNS_TOKEN reais no arquivo $PROJECT_ROOT/.env"
    echo "       1. Acesse https://www.duckdns.org/ e crie seu subdominio apontando para $TERMUX_HOST"
    echo "       2. Edite .env com seu subdominio e token e rode este script novamente."
    exit 1
fi

# Limpa protocolo (http/https), portas e barras caso o usuario tenha colado uma URL completa
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN#*://}"
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN%%/*}"
DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN%%:*}"
DUCKDNS_DOMAIN="$(echo "$DUCKDNS_DOMAIN" | tr -d '[:space:]')"

# Normaliza dominio caso o usuario tenha informado apenas o prefixo
if [[ "$DUCKDNS_DOMAIN" != *.duckdns.org ]]; then
    DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN}.duckdns.org"
fi
SUBDOMAIN="${DUCKDNS_DOMAIN%.duckdns.org}"

echo "==> [1/4] Atualizando IP Tailscale ($TERMUX_HOST) no DuckDNS para '$SUBDOMAIN'..."
DUCK_RESP=$(curl -fsSL "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=${TERMUX_HOST}")
if [ "$DUCK_RESP" != "OK" ]; then
    echo "[ERRO] Falha ao atualizar DuckDNS (resposta: '$DUCK_RESP'). Verifique subdominio e token."
    exit 1
fi
echo "    [OK] Registro A de $DUCKDNS_DOMAIN apontado para $TERMUX_HOST"

echo "==> [2/4] Conectando ao Redmi A3 ($TERMUX_HOST:$TERMUX_PORT) para emitir certificado Let's Encrypt (DNS-01)..."
sshpass -p "$TERMUX_PASS" ssh -o StrictHostKeyChecking=no -p "$TERMUX_PORT" "${TERMUX_USER}@${TERMUX_HOST}" \
    "DUCKDNS_DOMAIN='$DUCKDNS_DOMAIN' DUCKDNS_TOKEN='$DUCKDNS_TOKEN' bash -s" << 'REMOTE_EOF'
set -euo pipefail

SV_DIR="${PREFIX:-/data/data/com.termux/files/usr}/var/service"

# Garante dependencias basicas no Termux
pkg install -y curl openssl-tool cronie >/dev/null 2>&1 || true

# Instala acme.sh se ainda nao estiver instalado
if [ ! -f "$HOME/.acme.sh/acme.sh" ]; then
    curl -fsSL https://get.acme.sh | sh -s email="admin@${DUCKDNS_DOMAIN}"
fi

export DuckDNS_Token="$DUCKDNS_TOKEN"

# Define Let's Encrypt como autoridade certificadora padrao
"$HOME/.acme.sh/acme.sh" --set-default-ca --server letsencrypt

# Emite certificado ECC P-256 via desafio DNS-01 na API do DuckDNS (sem abrir portas 80/443)
"$HOME/.acme.sh/acme.sh" --issue \
    --dns dns_duckdns \
    -d "$DUCKDNS_DOMAIN" \
    --keylength ec-256 \
    --force

mkdir -p "$HOME/nexus-termux/certs"

# Persiste o dominio configurado para futuros deploys preservarem o server_name
echo "$DUCKDNS_DOMAIN" > "$HOME/nexus-termux/.duckdns_domain"

# Atualiza o server_name no nginx-nexus.conf se contiver o placeholder ou versao anterior
if [ -f "$HOME/nexus-termux/nginx-nexus.conf" ]; then
    sed -i "s/__DUCKDNS_DOMAIN__/${DUCKDNS_DOMAIN}/g" "$HOME/nexus-termux/nginx-nexus.conf"
    if ! grep -q "$DUCKDNS_DOMAIN" "$HOME/nexus-termux/nginx-nexus.conf"; then
        sed -i "s/server_name .*100\.107\.212\.104 localhost;/server_name ${DUCKDNS_DOMAIN} 100.107.212.104 localhost;/g" "$HOME/nexus-termux/nginx-nexus.conf"
    fi
fi

# Faz backup do certificado autoassinado antigo na primeira vez
if [ -f "$HOME/nexus-termux/certs/server.crt" ] && [ ! -f "$HOME/nexus-termux/certs/server.crt.selfsigned.bak" ]; then
    cp "$HOME/nexus-termux/certs/server.crt" "$HOME/nexus-termux/certs/server.crt.selfsigned.bak"
    cp "$HOME/nexus-termux/certs/server.key" "$HOME/nexus-termux/certs/server.key.selfsigned.bak"
fi

# Instala o certificado oficial e configura o hook de reload do Nginx no Runit
"$HOME/.acme.sh/acme.sh" --install-cert -d "$DUCKDNS_DOMAIN" --ecc \
    --fullchain-file "$HOME/nexus-termux/certs/server.crt" \
    --key-file "$HOME/nexus-termux/certs/server.key" \
    --reloadcmd "SVDIR=$SV_DIR sv restart nexus-nginx"

# Valida sintaxe do Nginx apos instalacao do certificado
nginx -t -c "$HOME/nexus-termux/nginx-nexus.conf"
SVDIR="$SV_DIR" sv restart nexus-nginx || true

# Registra cronjob do acme.sh e ativa crond para renovacao automatica a cada 60 dias (RF04)
"$HOME/.acme.sh/acme.sh" --install-cronjob >/dev/null 2>&1 || true
SVDIR="$SV_DIR" sv-enable crond >/dev/null 2>&1 || crond >/dev/null 2>&1 || true

echo "    [OK] Certificado Let's Encrypt instalado com sucesso em ~/nexus-termux/certs/!"
REMOTE_EOF

echo "==> [3/4] Validando resposta HTTPS oficial na porta 8445..."
sleep 2
curl -fsSL --resolve "${DUCKDNS_DOMAIN}:8445:${TERMUX_HOST}" "https://${DUCKDNS_DOMAIN}:8445/api/health"
echo ""
echo "==> [4/4] CONCLUIDO! Acesse no navegador do Redmi 13 Pro 5G (com Tailscale ativo):"
echo "    https://${DUCKDNS_DOMAIN}:8445"
echo "    No Chrome Android: Menu (3 pontos) -> 'Instalar aplicativo' para gerar o WebAPK nativo!"
