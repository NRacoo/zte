#!/usr/bin/env bash
# setup_tc.sh — VM3 (Network Execution Node)
#
# Membuat baseline HTB (Hierarchical Token Bucket) qdisc yang mensimulasikan
# alokasi Guaranteed Bitrate (GBR) Resource Block ala gNodeB/UPF.
#
# Struktur kelas:
#   1:1   (root, total 100mbit)
#     1:10  -> kelas PRIORITAS (live streaming / uplink kreator) - default kecil,
#               akan dinaikkan saat menerima perintah /boost dari VM2.
#     1:30  -> kelas DEFAULT (trafik lain / bulk download TCP)
#
# Jalankan sebagai root: sudo ./setup_tc.sh <interface>

set -euo pipefail
IFACE="${1:-eth0}"

echo "[VM3] Membersihkan qdisc lama di ${IFACE} (jika ada)..."
tc qdisc del dev "${IFACE}" root 2>/dev/null || true

echo "[VM3] Membuat root qdisc HTB di ${IFACE}..."
tc qdisc add dev "${IFACE}" root handle 1: htb default 30

tc class add dev "${IFACE}" parent 1: classid 1:1 htb rate 100mbit

# Kelas prioritas untuk live streaming (baseline rendah, fair share)
tc class add dev "${IFACE}" parent 1:1 classid 1:10 htb rate 10mbit ceil 20mbit prio 1

# Kelas default untuk trafik lain (mis. bulk download TCP)
tc class add dev "${IFACE}" parent 1:1 classid 1:30 htb rate 80mbit ceil 100mbit prio 3

echo "[VM3] Menambahkan qdisc SFQ per-kelas (anti starvation antar flow)..."
tc qdisc add dev "${IFACE}" parent 1:10 handle 10: sfq perturb 10
tc qdisc add dev "${IFACE}" parent 1:30 handle 30: sfq perturb 10

echo "[VM3] Menambahkan filter: trafik UDP (port iperf3 5202, live stream) -> kelas 1:10"
tc filter add dev "${IFACE}" protocol ip parent 1: prio 1 u32 \
  match ip protocol 17 0xff \
  match ip dport 5202 0xffff \
  flowid 1:10

echo "[VM3] Menambahkan filter default: TCP (port iperf3 5201, bulk download) -> kelas 1:30"
tc filter add dev "${IFACE}" protocol ip parent 1: prio 3 u32 \
  match ip protocol 6 0xff \
  match ip dport 5201 0xffff \
  flowid 1:30

echo "[VM3] Setup selesai. Status kelas saat ini:"
tc -s class show dev "${IFACE}"
