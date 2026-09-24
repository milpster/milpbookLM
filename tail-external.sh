#!/usr/bin/env bash
# Live-tail an nginx access log, showing only lines whose client IP is
# neither our own WAN IP nor loopback (127.0.0.1 / ::1).
#
# Usage: tail-external.sh [logfile]
set -euo pipefail

LOG="${1:-/var/log/nginx/milpbooklm-20001.access.log}"

if [[ ! -r "$LOG" ]]; then
    echo "error: cannot read log file: $LOG" >&2
    exit 1
fi

WAN_IP="$(curl -s --max-time 10 https://api.ipify.org)"
if [[ -z "$WAN_IP" || "$WAN_IP" == *":"* ]]; then
    echo "error: could not determine WAN IP from api.ipify.org" >&2
    exit 1
fi

echo "# filtering out own WAN IP: $WAN_IP (and loopback) -- log: $LOG" >&2
echo "# press Ctrl-C to stop" >&2

tail -n +1 -F -- "$LOG" \
  | awk -v wan="$WAN_IP" '
      $1 != wan && $1 != "127.0.0.1" && $1 != "::1" { print; fflush() }
    '
