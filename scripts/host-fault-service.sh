#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "${1:-}" in
  start|restart)
    sudo install -d -o "$(id -u)" -g 10001 -m 2770 "$root/runtime/host-control"
    mkdir -p "$root/runtime/host-fault-journal"
    chmod 700 "$root/runtime/host-fault-journal"
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/minicore-faults.service" <<UNIT
[Unit]
Description=Minicore fixed inventory fault executor
[Service]
Type=simple
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/scripts/host-fault-controller.py
Environment=PYTHONPATH=$root/vendor/umcp:$root/mcp-service/src
Environment=PATH=/usr/bin:/bin
KillMode=control-group
TimeoutStopSec=15
Restart=no
UMask=0007
UNIT
    systemctl --user daemon-reload
    systemctl --user "$1" minicore-faults.service
    ;;
  stop|status) systemctl --user "$1" minicore-faults.service ;;
  *) echo 'Use start|restart|stop|status' >&2; exit 2 ;;
esac
