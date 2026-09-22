#!/usr/bin/env bash
# First-pass bring-up of the Ubuntu gateway: Docker, nginx, certbot, proxy.
# Run on hexxus-ai-01 as a sudo-capable user:
#   sudo ./scripts/bootstrap.sh
set -euo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OPT_WEBUI=/opt/open-webui
OPT_PROXY=/opt/xai-proxy

if [[ "${EUID}" -ne 0 ]]; then
  echo "re-run as root: sudo $0 $*" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> packages"
apt-get update -y
apt-get install -y --no-install-recommends \
  docker.io \
  docker-compose-v2 \
  nginx \
  certbot \
  python3-certbot-nginx \
  python3-venv \
  python3-pip \
  ufw \
  rsync \
  curl \
  ca-certificates \
  openssl

systemctl enable --now docker
systemctl enable --now nginx

install_user="${SUDO_USER:-btahedl}"
usermod -aG docker "${install_user}"

echo "==> data dirs"
install -d -m 0755 "${OPT_WEBUI}/data"
install -d -m 0755 /var/www/letsencrypt
if [[ ! -f "${OPT_WEBUI}/open-webui.env" ]]; then
  install -m 0600 /dev/null "${OPT_WEBUI}/open-webui.env"
  secret="$(openssl rand -hex 32)"
  if [[ -f "${REPO}/proxy/.env" ]]; then
    # shellcheck disable=SC1091
    set -a
    source "${REPO}/proxy/.env"
    set +a
  fi
  cat > "${OPT_WEBUI}/open-webui.env" <<EOF
WEBUI_IMAGE_TAG=main-slim
WEBUI_SECRET_KEY=${secret}
XAI_API_KEY=${XAI_API_KEY:-xai-replace-me}
OPENAI_API_KEY=${XAI_API_KEY:-xai-replace-me}
AUDIO_TTS_OPENAI_API_KEY=${XAI_API_KEY:-xai-replace-me}
AUDIO_STT_OPENAI_API_KEY=${XAI_API_KEY:-xai-replace-me}
EOF
  chmod 600 "${OPT_WEBUI}/open-webui.env"
fi
install -m 0644 "${REPO}/compose/docker-compose.yml" "${OPT_WEBUI}/docker-compose.yml"
# compose interpolates WEBUI_IMAGE_TAG from this file
ln -sfn "${OPT_WEBUI}/open-webui.env" "${OPT_WEBUI}/.env"

echo "==> audio proxy"
id xai-proxy >/dev/null 2>&1 || useradd --system --home "${OPT_PROXY}" --shell /usr/sbin/nologin xai-proxy
install -d -m 0755 -o xai-proxy -g xai-proxy "${OPT_PROXY}"
install -m 0644 -o xai-proxy -g xai-proxy "${REPO}/proxy/xai_audio_proxy.py" "${OPT_PROXY}/xai_audio_proxy.py"
install -m 0644 -o xai-proxy -g xai-proxy "${REPO}/proxy/mapping.py" "${OPT_PROXY}/mapping.py"
install -m 0644 -o xai-proxy -g xai-proxy "${REPO}/proxy/requirements.txt" "${OPT_PROXY}/requirements.txt"
if [[ ! -f "${OPT_PROXY}/.env" ]]; then
  if [[ -f "${REPO}/proxy/.env" ]]; then
    install -m 0600 -o xai-proxy -g xai-proxy "${REPO}/proxy/.env" "${OPT_PROXY}/.env"
  else
    install -m 0600 -o xai-proxy -g xai-proxy "${REPO}/proxy/.env.example" "${OPT_PROXY}/.env"
    echo "WARNING: ${OPT_PROXY}/.env is still the example — put XAI_API_KEY in it" >&2
  fi
fi
if [[ ! -x "${OPT_PROXY}/venv/bin/python" ]]; then
  python3 -m venv "${OPT_PROXY}/venv"
fi
"${OPT_PROXY}/venv/bin/pip" install --upgrade pip
"${OPT_PROXY}/venv/bin/pip" install -r "${OPT_PROXY}/requirements.txt"
chown -R xai-proxy:xai-proxy "${OPT_PROXY}"
install -m 0644 "${REPO}/systemd/xai-audio-proxy.service" /etc/systemd/system/xai-audio-proxy.service
systemctl daemon-reload
systemctl enable --now xai-audio-proxy.service

echo "==> nginx (HTTP until certbot)"
install -m 0644 "${REPO}/nginx/websocket-map.conf" /etc/nginx/conf.d/00-websocket-map.conf
if [[ ! -f /etc/letsencrypt/live/ai.hexxus.net/fullchain.pem ]]; then
  install -m 0644 "${REPO}/nginx/open-webui.http-only.conf" /etc/nginx/sites-available/open-webui
else
  install -m 0644 "${REPO}/nginx/open-webui.conf" /etc/nginx/sites-available/open-webui
fi
ln -sfn /etc/nginx/sites-available/open-webui /etc/nginx/sites-enabled/open-webui
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Open WebUI"
if ! docker compose -f "${OPT_WEBUI}/docker-compose.yml" --env-file "${OPT_WEBUI}/open-webui.env" up -d; then
  echo "docker compose failed (image pull?). fix and re-run." >&2
  exit 1
fi

echo "==> waiting for loopback listeners"
for _ in $(seq 1 60); do
  if curl -sf --max-time 2 http://127.0.0.1:8787/health >/dev/null \
    && curl -sf --max-time 2 http://127.0.0.1:8080/health >/dev/null; then
    echo "proxy and Open WebUI are up on 127.0.0.1"
    break
  fi
  sleep 2
done

curl -sS http://127.0.0.1:8787/health || true
echo
echo "bootstrap done."
echo "Next:"
echo "  1. Put the real XAI_API_KEY in ${OPT_PROXY}/.env and ${OPT_WEBUI}/open-webui.env (chmod 600), then:"
echo "       systemctl restart xai-audio-proxy"
echo "       docker compose -f ${OPT_WEBUI}/docker-compose.yml --env-file ${OPT_WEBUI}/open-webui.env up -d"
echo "  2. Smoke: curl -sS http://127.0.0.1:8080/health && curl -sS http://127.0.0.1:8787/health"
echo "  3. Rsync Studio data: ${REPO}/scripts/migrate-data.sh"
echo "  4. Point ai.hexxus.net here, then: certbot --nginx -d ai.hexxus.net"
echo "  5. ${install_user} was added to group docker — new shells pick that up"
