#!/usr/bin/env bash
# boost_qos.sh — VM3
# Menaikkan rate/ceil kelas prioritas (1:10, live streaming) dan sedikit
# menurunkan kelas default (1:30) agar UDP live stream mendapat GBR lebih besar.
#
# Dipanggil oleh agent.py saat menerima POST /boost dari VM2.
#
# Pemakaian: sudo ./boost_qos.sh <interface> [profile]
#   profile: PREMIUM_UPLINK (default) | STANDARD

set -euo pipefail
IFACE="${1:-eth0}"
PROFILE="${2:-PREMIUM_UPLINK}"

if [ "${PROFILE}" = "PREMIUM_UPLINK" ]; then
  PRIORITY_RATE="60mbit"
  PRIORITY_CEIL="80mbit"
  DEFAULT_RATE="30mbit"
  DEFAULT_CEIL="40mbit"
else
  PRIORITY_RATE="30mbit"
  PRIORITY_CEIL="50mbit"
  DEFAULT_RATE="50mbit"
  DEFAULT_CEIL="70mbit"
fi

echo "[VM3] BOOST diaktifkan (${PROFILE}) di ${IFACE}: kelas 1:10 -> rate=${PRIORITY_RATE} ceil=${PRIORITY_CEIL}"
tc class change dev "${IFACE}" parent 1:1 classid 1:10 htb rate "${PRIORITY_RATE}" ceil "${PRIORITY_CEIL}" prio 1
tc class change dev "${IFACE}" parent 1:1 classid 1:30 htb rate "${DEFAULT_RATE}" ceil "${DEFAULT_CEIL}" prio 3

echo "[VM3] Status kelas setelah boost:"
tc -s class show dev "${IFACE}"
