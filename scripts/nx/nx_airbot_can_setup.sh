#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-robot@192.168.234.234}"
TTY_ID="/dev/serial/by-id/usb-DISCOVER_Robotics_DISCOVER_Robotics_USB_to_CAN_adapter_205E31544E46-if00"
ESCAPED_DEVICE="dev-serial-by\\x2did-usb\\x2dDISCOVER_Robotics_DISCOVER_Robotics_USB_to_CAN_adapter_205E31544E46\\x2dif00.device"

ssh "$HOST" 'sudo -n true'

ssh "$HOST" "sudo -n install -m 0755 /dev/null /usr/local/sbin/airbot-can1-up"
ssh "$HOST" "sudo -n tee /usr/local/sbin/airbot-can1-up >/dev/null" <<'EOF'
#!/bin/sh
set -eu

TTY="/dev/serial/by-id/usb-DISCOVER_Robotics_DISCOVER_Robotics_USB_to_CAN_adapter_205E31544E46-if00"

test -e "$TTY" || {
    echo "DISCOVER USB-CAN adapter is not present: $TTY" >&2
    exit 1
}

if ip link show can1 >/dev/null 2>&1; then
    ip link delete can1
fi

slcand -o -c -f -s8 "$TTY" can1

i=0
while [ "$i" -lt 30 ]; do
    if ip link show can1 >/dev/null 2>&1; then
        ip link set can1 up
        exit 0
    fi
    i=$((i + 1))
    sleep 0.1
done

echo "Timed out waiting for can1" >&2
exit 1
EOF
ssh "$HOST" "sudo -n chmod 0755 /usr/local/sbin/airbot-can1-up"

ssh "$HOST" "sudo -n tee /etc/systemd/system/airbot-can1.service >/dev/null" <<EOF
[Unit]
Description=AIRBOT DISCOVER USB-CAN as SocketCAN can1
BindsTo=$ESCAPED_DEVICE
After=$ESCAPED_DEVICE systemd-modules-load.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/sbin/modprobe slcan
ExecStart=/usr/local/sbin/airbot-can1-up
ExecStop=/bin/sh -c 'test ! -e /sys/class/net/can1 || ip link delete can1'
Restart=on-failure
RestartSec=2s
TimeoutStartSec=15s

[Install]
WantedBy=multi-user.target
EOF

ssh "$HOST" "sudo -n tee /etc/udev/rules.d/80-airbot-discover-can.rules >/dev/null" <<'EOF'
ACTION=="add", SUBSYSTEM=="tty", ENV{ID_SERIAL_SHORT}=="205E31544E46", TAG+="systemd", ENV{SYSTEMD_WANTS}+="airbot-can1.service"
EOF

ssh "$HOST" '
set -e
sudo -n systemctl daemon-reload
sudo -n systemctl reset-failed airbot-can1.service || true
sudo -n systemctl enable airbot-can1.service
sudo -n systemctl restart airbot-can1.service
sleep 1
systemctl is-active airbot-can1.service
ip -brief link show can1
'
