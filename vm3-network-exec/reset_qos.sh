#!/usr/bin/env bash
# reset_qos.sh — VM3
# Mengembalikan kelas 1:10 dan 1:30 ke baseline (lihat setup_tc.sh).
# Dipanggil oleh agent.py saat sesi boost berakhir / dibatalkan (DELETE session).
#
# Pemakaian: sudo ./reset_qos.sh <interface>

set -euo pipefail
IFACE="${1:-eth0}"

echo "[VM3] Mengembalikan QoS ke baseline di ${IFACE}..."
tc class change dev "${IFACE}" parent 1:1 classid 1:10 htb rate 10mbit ceil 20mbit prio 1
tc class change dev "${IFACE}" parent 1:1 classid 1:30 htb rate 80mbit ceil 100mbit prio 3

echo "[VM3] Status kelas setelah reset:"
tc -s class show dev "${IFACE}"
