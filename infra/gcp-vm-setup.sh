#!/bin/bash
# Setup inicial da VM no GCP — rode UMA VEZ como root.
# Testado em Debian 12 (recomendado) e Ubuntu 22.04.
#
# Uso:
#   gcloud compute ssh VM_NAME -- 'bash -s' < infra/gcp-vm-setup.sh

set -euo pipefail

REPO_URL="https://github.com/mepoupeze-crawd/trip-assistant.git"
APP_DIR="/app"
DEPLOY_USER="deploy"

echo "=== [1/5] Instalando Docker ==="
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker

echo "=== [2/5] Criando usuário deploy ==="
id -u "$DEPLOY_USER" &>/dev/null || useradd -m -s /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"

echo "=== [3/5] Configurando chave SSH para GitHub Actions ==="
mkdir -p /home/"$DEPLOY_USER"/.ssh
chmod 700 /home/"$DEPLOY_USER"/.ssh
ssh-keygen -t ed25519 \
  -f /home/"$DEPLOY_USER"/.ssh/deploy_key \
  -N "" \
  -C "github-actions-deploy" \
  -q
cat /home/"$DEPLOY_USER"/.ssh/deploy_key.pub \
  >> /home/"$DEPLOY_USER"/.ssh/authorized_keys
chmod 600 /home/"$DEPLOY_USER"/.ssh/authorized_keys
chown -R "$DEPLOY_USER":"$DEPLOY_USER" /home/"$DEPLOY_USER"/.ssh

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  COPIE A CHAVE ABAIXO PARA O SECRET GCP_SSH_KEY NO GITHUB  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
cat /home/"$DEPLOY_USER"/.ssh/deploy_key
echo "══════════════════════════════════════════════════════════════"
echo ""

echo "=== [4/5] Clonando repositório ==="
git clone "$REPO_URL" "$APP_DIR"
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"

echo "=== [5/5] Criando .env a partir do exemplo ==="
cp "$APP_DIR/.env.example" "$APP_DIR/.env"
chown "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR/.env"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                 SETUP CONCLUÍDO                         ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Próximos passos:"
echo ""
echo "  1. Edite os secrets de produção:"
echo "       sudo -u deploy nano $APP_DIR/.env"
echo ""
echo "  2. Edite o Caddyfile com o seu domínio:"
echo "       sudo -u deploy nano $APP_DIR/Caddyfile"
echo ""
echo "  3. Execute as migrations (primeira vez):"
echo "       cd $APP_DIR && sudo -u deploy docker compose \\"
echo "         -f docker-compose.yml -f docker-compose.prod.yml \\"
echo "         run --rm migrate"
echo ""
echo "  4. Suba todos os serviços:"
echo "       cd $APP_DIR && sudo -u deploy docker compose \\"
echo "         -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo ""
echo "  5. No GitHub, adicione os secrets:"
echo "       GCP_SSH_KEY  → a chave privada impressa acima"
echo "       GCP_VM_HOST  → $(curl -s ifconfig.me 2>/dev/null || echo '<IP_EXTERNO_DA_VM>')"
echo "       GCP_VM_USER  → deploy"
echo ""
