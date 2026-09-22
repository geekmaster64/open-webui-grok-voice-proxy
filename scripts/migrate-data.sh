#!/usr/bin/env bash
# Copy Open WebUI data/ off the Studio into /opt/open-webui/data.
# Stop writes on the Mac first (quit the desktop app).
#
# Usage:
#   ./scripts/migrate-data.sh user@studio.example:/Users/btahedl/Library/Application\ Support/open-webui/data/
#   ./scripts/migrate-data.sh /path/to/copied/data/
set -euo pipefail

DEST=/opt/open-webui/data
COMPOSE=/opt/open-webui/docker-compose.yml
ENVFILE=/opt/open-webui/open-webui.env

if [[ "${#}" -lt 1 ]]; then
  echo "usage: $0 <rsync-source>" >&2
  echo "  source is the Studio data/ directory, trailing slash, e.g." >&2
  echo "  btahedl@mac:/Users/btahedl/Library/Application\\ Support/open-webui/data/" >&2
  exit 1
fi

SRC="${1}"
if [[ "${EUID}" -ne 0 ]]; then
  echo "re-run as root: sudo $0 $*" >&2
  exit 1
fi

if [[ ! -f "${COMPOSE}" ]]; then
  echo "missing ${COMPOSE} — run scripts/bootstrap.sh first" >&2
  exit 1
fi

echo "==> stopping Open WebUI (no writes during copy)"
docker compose -f "${COMPOSE}" --env-file "${ENVFILE}" stop open-webui || true

echo "==> rsync ${SRC} → ${DEST}/"
install -d -m 0755 "${DEST}"
rsync -aH --info=stats2 --partial "${SRC}" "${DEST}/"

echo "==> starting Open WebUI on migrated data"
docker compose -f "${COMPOSE}" --env-file "${ENVFILE}" up -d
echo "done. confirm chats/settings, then:"
echo "  audio STT/TTS base URL = http://127.0.0.1:8787/v1"
echo "  split on punctuation, Ara voice"
echo "  only https://api.x.ai/v1 enabled for models"
