#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "${1:-}" in
 start|restart)
  if systemctl is-active --quiet minicore-observer-capture.service; then
    echo 'Stop IGMP capture before starting counters' >&2
    exit 1
  fi
  sudo install -d -o "$(id -u)" -g 10001 -m 2770 "$root/runtime/observer-socket"
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/minicore-observer.service" <<UNIT
[Unit]
Description=Minicore memory-only routing observer counters
[Service]
Type=simple
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/scripts/observer-host.py
Environment=PYTHONPATH=$root/vendor/umcp:$root/mcp-service/src
Environment=PATH=/usr/bin:/bin
LimitCORE=0
MemoryMax=128M
MemorySwapMax=0
TasksMax=32
NoNewPrivileges=yes
UMask=0007
KillMode=control-group
TimeoutStopSec=15
Restart=no
UNIT
  systemctl --user daemon-reload
  systemctl --user "$1" minicore-observer.service
  ;;
 stop|status) systemctl --user "$1" minicore-observer.service ;;
 *) echo 'Use start|restart|stop|status' >&2; exit 2 ;;
esac
