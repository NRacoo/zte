"""
train_model.py — VM1 (AI Sensing Node)

Membuat dataset sintetis untuk 2 kelas trafik:
  0 = normal / bulk download (TCP-heavy, paket besar, inter-arrival kecil, downlink dominan)
  1 = live streaming upload (UDP/QUIC-heavy, paket sedang-kecil tapi konsisten,
      uplink persisten tinggi -> ciri khas live streaming dari sisi kreator)

Fitur (Zero-DPI, hanya flow statistics — TIDAK membuka payload):
  - avg_packet_size      : rata-rata ukuran paket (byte)
  - std_packet_size      : deviasi ukuran paket
  - avg_inter_arrival_ms : rata-rata jeda antar paket (ms)
  - uplink_ratio         : rasio byte uplink / (uplink + downlink)

Model: RandomForestClassifier (ringan, cocok untuk edge device / router firmware).
Output: model.joblib (dipakai oleh sensor.py)
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

RNG = np.random.default_rng(42)
N_PER_CLASS = 2000


def make_normal_traffic(n):
    # Bulk download / browsing: paket besar (MTU-ish), inter-arrival kecil & variatif,
    # didominasi downlink (uplink_ratio rendah).
    avg_packet_size = RNG.normal(1200, 150, n).clip(64, 1500)
    std_packet_size = RNG.normal(180, 40, n).clip(5, None)
    avg_inter_arrival_ms = RNG.exponential(3.0, n).clip(0.1, None)
    uplink_ratio = RNG.beta(2, 8, n)  # condong rendah (banyak download, sedikit upload/ACK)
    return np.column_stack([avg_packet_size, std_packet_size, avg_inter_arrival_ms, uplink_ratio])


def make_streaming_traffic(n):
    # Live streaming upload: paket sedang-konsisten, inter-arrival stabil (isochronous-ish),
    # uplink_ratio tinggi & persisten (kreator mengirim video ke server).
    avg_packet_size = RNG.normal(750, 120, n).clip(64, 1500)
    std_packet_size = RNG.normal(60, 20, n).clip(5, None)
    avg_inter_arrival_ms = RNG.normal(8.0, 2.0, n).clip(0.5, None)
    uplink_ratio = RNG.beta(8, 2, n)  # condong tinggi & stabil
    return np.column_stack([avg_packet_size, std_packet_size, avg_inter_arrival_ms, uplink_ratio])


def main():
    X0 = make_normal_traffic(N_PER_CLASS)
    X1 = make_streaming_traffic(N_PER_CLASS)
    X = np.vstack([X0, X1])
    y = np.concatenate([np.zeros(N_PER_CLASS), np.ones(N_PER_CLASS)])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=100, max_depth=8, random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print("=== Evaluasi Model (data sintetis) ===")
    print(classification_report(
        y_test, y_pred, target_names=["normal", "live_streaming"]
    ))

    joblib.dump(clf, "model.joblib")
    print("Model tersimpan -> model.joblib")


if __name__ == "__main__":
    main()
