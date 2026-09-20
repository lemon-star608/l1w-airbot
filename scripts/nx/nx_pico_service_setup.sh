#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-robot@192.168.234.234}"

ssh "$HOST" 'sudo -n true'

ssh "$HOST" 'test -x /opt/apps/roboticsservice/RoboticsServiceProcess'

ssh "$HOST" "sudo -n tee /etc/systemd/system/xrobo-pc-service.service >/dev/null" <<'EOF'
[Unit]
Description=XRoboToolkit PC-Service for PICO input
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/apps/roboticsservice
Environment=LD_LIBRARY_PATH=/opt/apps/roboticsservice:/opt/apps/roboticsservice/lib:/opt/apps/roboticsservice/SDK/arm64
Environment=QT_PLUGIN_PATH=/opt/apps/roboticsservice/plugins
Environment=QT_QML_PATH=/opt/apps/roboticsservice/qml
Environment=HOME=/opt/apps/roboticsservice
ExecStart=/opt/apps/roboticsservice/RoboticsServiceProcess
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=multi-user.target
EOF

ssh "$HOST" '
set -e
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now xrobo-pc-service.service
sleep 2
systemctl --no-pager --full status xrobo-pc-service.service | sed -n "1,18p"
pgrep -af RoboticsServiceProcess
ss -lntp | grep -E ":(63901|60061)\\b" || true
'
