"""
sensor.py — VM1 (Edge AI Sensing Node, mensimulasikan agen di firmware ZTE CPE)

Alur:
  1. Ambil 100 paket pertama dari sebuah flow (real via scapy sniff, atau
     --simulate untuk demo tanpa root/interface).
  2. Hitung flow statistics (Zero-DPI, tidak membuka payload):
       - avg/std packet size
       - avg inter-arrival time
       - uplink/downlink ratio
  3. Klasifikasi dengan model RandomForest (model.joblib dari train_model.py).
  4. Jika terdeteksi live streaming -> kirim HTTP POST ke VM2 (API Orchestrator)
     sesuai payload CAMARA-style QoD API di dokumen desain.

Jalankan:
  Mode simulasi (tanpa root, tanpa scapy sniff nyata):
    python sensor.py --simulate streaming
    python sensor.py --simulate normal

  Mode real capture (butuh root & scapy):
    sudo python sensor.py --iface eth0 --target-ip 10.0.0.5
"""

import argparse
import time
import statistics
import numpy as np
import joblib
import requests

VM2_GATEWAY_URL = "http://10.0.0.1:8000/api/v1/qos/boost"  # sesuaikan IP VM2
DEVICE_ID = "ZTE-MC801A-9982X"
SAMPLE_SIZE = 100


def load_model(path="model.joblib"):
    try:
        return joblib.load(path)
    except FileNotFoundError:
        raise SystemExit(
            "model.joblib tidak ditemukan. Jalankan `python train_model.py` dahulu."
        )


def extract_features(sizes, timestamps, uplink_bytes, downlink_bytes):
    """Hitung flow statistics dari 100 paket pertama (Zero-DPI)."""
    avg_packet_size = statistics.fmean(sizes)
    std_packet_size = statistics.pstdev(sizes) if len(sizes) > 1 else 0.0

    inter_arrivals = [
        (t2 - t1) * 1000.0 for t1, t2 in zip(timestamps, timestamps[1:])
    ]
    avg_inter_arrival_ms = statistics.fmean(inter_arrivals) if inter_arrivals else 0.0

    total = uplink_bytes + downlink_bytes
    uplink_ratio = uplink_bytes / total if total > 0 else 0.0

    return np.array([[avg_packet_size, std_packet_size, avg_inter_arrival_ms, uplink_ratio]])


def simulate_flow(kind: str):
    """Simulasikan 100 paket untuk demo tanpa perlu sniff jaringan nyata."""
    rng = np.random.default_rng()
    if kind == "streaming":
        sizes = rng.normal(750, 120, SAMPLE_SIZE).clip(64, 1500)
        gaps = rng.normal(8.0, 2.0, SAMPLE_SIZE - 1).clip(0.5, None) / 1000.0
        uplink_bytes = int(sizes.sum() * 0.85)
        downlink_bytes = int(sizes.sum() * 0.15)
    else:
        sizes = rng.normal(1200, 150, SAMPLE_SIZE).clip(64, 1500)
        gaps = rng.exponential(3.0, SAMPLE_SIZE - 1).clip(0.1, None) / 1000.0
        uplink_bytes = int(sizes.sum() * 0.15)
        downlink_bytes = int(sizes.sum() * 0.85)

    timestamps = [0.0]
    for g in gaps:
        timestamps.append(timestamps[-1] + g)

    return sizes.tolist(), timestamps, uplink_bytes, downlink_bytes


def capture_flow_scapy(iface: str, count: int = SAMPLE_SIZE):
    """Capture 100 paket pertama secara real menggunakan scapy (butuh root)."""
    from scapy.all import sniff, IP

    pkts = sniff(iface=iface, count=count, timeout=30)
    sizes, timestamps = [], []
    uplink_bytes = downlink_bytes = 0

    local_prefixes = ("192.168.", "10.")  # sederhana: anggap ini LAN sisi CPE
    for pkt in pkts:
        sizes.append(len(pkt))
        timestamps.append(float(pkt.time))
        if IP in pkt:
            if pkt[IP].src.startswith(local_prefixes):
                uplink_bytes += len(pkt)
            else:
                downlink_bytes += len(pkt)

    return sizes, timestamps, uplink_bytes, downlink_bytes


def send_boost_request(target_ip: str, duration_seconds: int = 3600):
    payload = {
        "device_id": DEVICE_ID,
        "intent": "live_stream_boost",
        "qos_profile": "PREMIUM_UPLINK",
        "target_ip": target_ip,
        "duration_seconds": duration_seconds,
    }
    print(f"[VM1] Trafik live streaming terdeteksi -> mengirim POST ke VM2: {payload}")
    try:
        resp = requests.post(VM2_GATEWAY_URL, json=payload, timeout=5)
        print(f"[VM1] Respons VM2 ({resp.status_code}): {resp.json()}")
    except requests.RequestException as e:
        print(f"[VM1] Gagal menghubungi VM2 gateway: {e}")


def main():
    parser = argparse.ArgumentParser(description="Edge AI Sensing Agent (VM1)")
    parser.add_argument("--simulate", choices=["normal", "streaming"], default=None,
                         help="Jalankan mode simulasi tanpa capture jaringan nyata")
    parser.add_argument("--iface", default="eth0", help="Interface untuk sniff nyata (butuh root)")
    parser.add_argument("--target-ip", default="10.0.0.5", help="IP tujuan yang diminta boost")
    parser.add_argument("--model", default="model.joblib")
    args = parser.parse_args()

    clf = load_model(args.model)

    if args.simulate:
        print(f"[VM1] Mode simulasi: {args.simulate}")
        sizes, timestamps, up_b, down_b = simulate_flow(args.simulate)
    else:
        print(f"[VM1] Menangkap {SAMPLE_SIZE} paket pertama di interface {args.iface} ...")
        sizes, timestamps, up_b, down_b = capture_flow_scapy(args.iface, SAMPLE_SIZE)

    X = extract_features(sizes, timestamps, up_b, down_b)
    pred = clf.predict(X)[0]
    proba = clf.predict_proba(X)[0][1]

    print(f"[VM1] Fitur flow: avg_size={X[0][0]:.1f}B std={X[0][1]:.1f} "
          f"inter_arrival={X[0][2]:.2f}ms uplink_ratio={X[0][3]:.2f}")
    print(f"[VM1] Prediksi: {'LIVE STREAMING' if pred == 1 else 'NORMAL'} "
          f"(confidence={proba:.2%})")

    if pred == 1:
        send_boost_request(args.target_ip)
    else:
        print("[VM1] Tidak ada tindakan diambil.")


if __name__ == "__main__":
    main()
