#!/usr/bin/env bash
# Live-tail an nginx access log, showing only lines whose client IP is
# neither our own WAN address (v4 and v6, detected dynamically) nor
# loopback (127.0.0.1 / ::1).
#
# Usage: tail-external.sh [logfile]
set -euo pipefail

LOG="${1:-/var/log/nginx/milpbooklm-20001.access.log}"

if [[ ! -r "$LOG" ]]; then
    echo "error: cannot read log file: $LOG" >&2
    exit 1
fi

WAN_V4="$(curl -4 -s --max-time 10 https://api.ipify.org)" || WAN_V4=""
WAN_V6="$(curl -6 -s --max-time 10 https://api6.ipify.org)" || WAN_V6=""

if [[ -z "${WAN_V4:-}" && -z "${WAN_V6:-}" ]]; then
    echo "error: could not determine WAN IP (v4 and v6 both failed)" >&2
    exit 1
fi

echo "# filtering out own WAN: ${WAN_V4:-<no v4>} ${WAN_V6:-<no v6>} (and loopback)" >&2
echo "# log: $LOG -- press Ctrl-C to stop" >&2

tail -n +1 -F -- "$LOG" \
  | awk -v own="${WAN_V4:-} ${WAN_V6:-}" '
      BEGIN {
          n = split(own, a, " ")
          for (i = 1; i <= n; i++) if (a[i] != "") skip[a[i]] = 1
      }
      $1 != "127.0.0.1" && $1 != "::1" && !($1 in skip) { print; fflush() }
    '
