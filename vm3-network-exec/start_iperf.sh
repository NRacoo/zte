#!/usr/bin/env bash
# start_iperf.sh — VM3 (Network Execution Node)
#
# Menjalankan dua iperf3 server secara bersamaan:
#   - Port 5201 (TCP) : mewakili trafik "bulk download" yang berebut bandwidth.
#   - Port 5202 (UDP) : mewakili trafik "live stream" milik kreator.
#
# Di sisi client (VM1 atau mesin lain), jalankan salah satu:
#   iperf3 -c <VM3_IP> -p 5201 -t 60                       # generate trafik TCP download
#   iperf3 -c <VM3_IP> -p 5202 -u -b 8M -t 60               # generate trafik UDP live stream
#
# Pantau hasilnya real-time dengan: watch -n1 "tc -s class show dev eth0"

set -euo pipefail

echo "[VM3] Menjalankan iperf3 server TCP di port 5201 (bulk download)..."
iperf3 -s -p 5201 -D --logfile /tmp/iperf_tcp_5201.log

echo "[VM3] Menjalankan iperf3 server UDP di port 5202 (live streaming)..."
iperf3 -s -p 5202 -D --logfile /tmp/iperf_udp_5202.log

echo "[VM3] Kedua server berjalan di background. Log: /tmp/iperf_tcp_5201.log , /tmp/iperf_udp_5202.log"
echo "[VM3] Hentikan dengan: pkill -f 'iperf3 -s'"
