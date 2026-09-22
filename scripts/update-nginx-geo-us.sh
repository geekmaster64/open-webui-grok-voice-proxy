#!/usr/bin/env bash
# Refresh US CIDR lists for nginx geo $is_us. RFC1918/VPN stays in geo-us.conf.
set -euo pipefail

DEST=/etc/nginx/geoip
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsSL --max-time 60 \
  -o "$TMP/us4.txt" \
  https://www.ipdeny.com/ipblocks/data/aggregated/us-aggregated.zone
curl -fsSL --max-time 60 \
  -o "$TMP/us6.txt" \
  https://www.ipdeny.com/ipv6/ipaddresses/aggregated/us-aggregated.zone

# nginx geo include: "1.2.3.0/24 1;"
{
  echo "# generated $(date -u +%Y-%m-%dT%H:%M:%SZ) from ipdeny.com aggregated US"
  awk 'NF && $1 !~ /^#/ { print $1, "1;" }' "$TMP/us4.txt" "$TMP/us6.txt"
} > "$TMP/us.conf"

test -s "$TMP/us.conf"
install -d -m 0755 "$DEST"
install -m 0644 "$TMP/us.conf" "$DEST/us.conf"

if nginx -t >/dev/null 2>&1; then
  systemctl reload nginx
else
  echo "nginx -t failed after geo update; not reloading" >&2
  nginx -t
  exit 1
fi
echo "updated $DEST/us.conf ($(wc -l < "$DEST/us.conf") prefixes)"
