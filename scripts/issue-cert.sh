#!/usr/bin/env bash
# Re-issue Let's Encrypt on Ubuntu. Do not copy Mac cert paths.
# Run AFTER ai.hexxus.net (public 149.154.51.230) NATs 80/443 to this VM.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "re-run as root: sudo $0" >&2
  exit 1
fi

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
install -d -m 0755 /var/www/letsencrypt

certbot --nginx -d ai.hexxus.net --agree-tos --redirect --non-interactive \
  --email "${CERTBOT_EMAIL:-hostmaster@hexxus.net}" || {
  echo "certbot --nginx failed; trying webroot" >&2
  certbot certonly --webroot -w /var/www/letsencrypt -d ai.hexxus.net \
    --agree-tos --non-interactive --email "${CERTBOT_EMAIL:-hostmaster@hexxus.net}"
  install -m 0644 "${REPO}/nginx/open-webui.conf" /etc/nginx/sites-available/open-webui
  nginx -t && systemctl reload nginx
}

systemctl enable --now certbot.timer 2>/dev/null || true
echo "cert issued. curl -I https://ai.hexxus.net"
