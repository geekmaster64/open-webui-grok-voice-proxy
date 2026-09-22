#!/usr/bin/env bash
# Local smoke checks. Does not hit ai.hexxus.net (that is still the Studio until cutover).
set -euo pipefail

fail=0
check() {
  local name="$1" cmd="$2"
  if eval "${cmd}" >/dev/null 2>&1; then
    echo "ok  ${name}"
  else
    echo "FAIL ${name}"
    fail=1
  fi
}

echo "==> listeners (must be loopback, not 0.0.0.0)"
ss -tlnp 2>/dev/null | grep -E ':8080|:8787|:80 |:443 ' || true

check "proxy /health" "curl -sf --max-time 5 http://127.0.0.1:8787/health"
check "proxy not on all interfaces" "! ss -tln | grep -q '0.0.0.0:8787'"
check "open-webui /health" "curl -sf --max-time 5 http://127.0.0.1:8080/health"
check "open-webui not on all interfaces" "! ss -tln | grep -q '0.0.0.0:8080'"
check "nginx http" "curl -sf --max-time 5 -o /dev/null -H 'Host: ai.hexxus.net' http://127.0.0.1/"
check "xai-audio-proxy unit" "systemctl is-active --quiet xai-audio-proxy"
check "docker open-webui" "docker inspect -f '{{.State.Running}}' open-webui 2>/dev/null | grep -q true || sg docker -c \"docker inspect -f '{{.State.Running}}' open-webui\" | grep -q true"
check "no ollama container" "! docker ps -a --format '{{.Names}}' | grep -qi ollama"

echo
if [[ "${fail}" -eq 0 ]]; then
  echo "all checks passed"
else
  echo "some checks failed"
fi
exit "${fail}"
