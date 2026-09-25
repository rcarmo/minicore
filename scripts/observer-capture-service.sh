#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "${1:-}" in
 start|restart)
  # Same socket, never run both services concurrently.
  if systemctl --user cat minicore-observer.service >/dev/null 2>&1; then
    systemctl --user stop minicore-observer.service
  fi
  sudo install -d -o "$(id -u)" -g 10001 -m 2770 "$root/runtime/observer-socket"
  file=$(mktemp)
  trap 'rm -f "$file"' EXIT
  cat > "$file" <<UNIT
[Unit]
Description=Minicore memory-only counters and filtered IGMP observer
After=docker.service
[Service]
Type=simple
User=$(id -un)
Group=$(id -gn)
SupplementaryGroups=docker
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/scripts/observer-host.py
Environment=PYTHONPATH=$root/vendor/umcp:$root/mcp-service/src
Environment=PATH=/usr/bin:/bin
Environment=MINICORE_IGMP_CAPTURE=1
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
NoNewPrivileges=yes
LimitCORE=0
MemoryMax=128M
MemorySwapMax=0
TasksMax=32
UMask=0007
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$root/runtime/observer-socket
RestrictAddressFamilies=AF_UNIX AF_NETLINK AF_PACKET AF_INET AF_INET6
StandardOutput=null
StandardError=journal
KillMode=control-group
TimeoutStopSec=15
Restart=no
UNIT
  sudo install -m 644 "$file" /etc/systemd/system/minicore-observer-capture.service
  sudo systemctl daemon-reload
  sudo systemctl "$1" minicore-observer-capture.service
  ;;
 stop|status) sudo systemctl "$1" minicore-observer-capture.service ;;
 *) echo 'Use start|restart|stop|status' >&2; exit 2 ;;
esac
