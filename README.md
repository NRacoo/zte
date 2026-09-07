# PoC — AI-Driven QoS Boost for Live Streaming (5G Core, CAMARA QoD-style)

Proof of Concept 3-node yang mensimulasikan alur end-to-end:

```
[VM1] Edge AI Sensing  --HTTP POST-->  [VM2] API Orchestrator/NEF  --HTTP-->  [VM3] Core Network Exec
 (deteksi live stream)                  (auth + validasi + routing)           (tc HTB = PCF/UPF nyata)
```

Ini **sudah teruji berjalan** (model AI dilatih & diklasifikasi dengan benar, request API
melewati auth Zero-Trust, dan perintah diteruskan ke node eksekusi) — lihat bagian
[Hasil Pengujian](#hasil-pengujian-yang-sudah-dilakukan) di bawah.

---

## 1. Arsitektur

| Node | Peran | Tech Stack | Port |
|---|---|---|---|
| **VM1 — AI Sensing** | Simulasi agen di firmware ZTE CPE. Ekstrak flow statistics (Zero-DPI) dari 100 paket pertama, klasifikasi live-stream vs normal pakai RandomForest, lalu kirim request boost. | Python, scikit-learn, scapy, requests | — |
| **VM2 — API Gateway / NEF** | Middleware + firewall. Autentikasi Bearer token (simulasi OAuth2) + whitelist `device_id` (simulasi USIM-based auth / Zero-Trust). Menerima payload gaya **CAMARA QoD API**, meneruskan ke VM3. | Python, FastAPI, Uvicorn | 8000 |
| **VM3 — Core Network Exec** | Simulasi PCF (keputusan kebijakan) + UPF/gNodeB (eksekusi). Menjalankan perintah `tc` (Linux Traffic Control, HTB) nyata untuk memprioritaskan trafik live-stream di atas trafik lain. | Python, FastAPI, Linux `tc`, `iperf3` | 9000 (agent), 5201/5202 (iperf3) |

Payload API (sesuai desain, format CAMARA QoD yang disederhanakan):

```json
{
  "device_id": "ZTE-MC801A-9982X",
  "intent": "live_stream_boost",
  "qos_profile": "PREMIUM_UPLINK",
  "target_ip": "10.0.0.5",
  "duration_seconds": 3600
}
```

---

## 2. Struktur Folder

```
poc-qos-boost/
├── vm1-ai-sensing/
│   ├── train_model.py     # generate dataset sintetis + latih RandomForest
│   ├── sensor.py          # sniff/simulate -> extract features -> klasifikasi -> POST ke VM2
│   └── requirements.txt
├── vm2-api-gateway/
│   ├── main.py             # FastAPI: /api/v1/qos/boost (POST/DELETE), auth, forward ke VM3
│   └── requirements.txt
├── vm3-network-exec/
│   ├── agent.py            # FastAPI: /boost /reset -> menjalankan script tc
│   ├── setup_tc.sh         # baseline HTB qdisc (kelas prioritas vs default)
│   ├── boost_qos.sh        # naikkan rate/ceil kelas live-streaming
│   ├── reset_qos.sh        # kembalikan ke baseline
│   ├── start_iperf.sh      # server iperf3 TCP (5201) & UDP (5202) untuk demo trafik
│   └── requirements.txt
└── README.md
```

---

## 3. Cara Menjalankan — Mode Cepat (1 mesin, tanpa VM, tanpa root)

Cocok untuk demo cepat / development, tanpa perlu provisioning 3 VM dan tanpa perlu izin `tc`.
VM3 dijalankan dengan `DRY_RUN=1` sehingga perintah `tc` hanya dicetak ke log, tidak benar-benar
mengubah jaringan — fokusnya membuktikan alur AI -> API -> eksekusi berjalan benar.

```bash
# Terminal 1 — VM3 (Core Network Exec, dry-run)
cd vm3-network-exec
pip install -r requirements.txt
DRY_RUN=1 QOS_IFACE=eth0 uvicorn agent:app --host 127.0.0.1 --port 9000

# Terminal 2 — VM2 (API Gateway)
cd vm2-api-gateway
pip install -r requirements.txt
VM3_AGENT_URL=http://127.0.0.1:9000 API_TOKEN=poc-demo-token-12345 \
  uvicorn main:app --host 127.0.0.1 --port 8000

# Terminal 3 — VM1 (AI Sensing)
cd vm1-ai-sensing
pip install -r requirements.txt
python train_model.py            # sekali saja, hasilkan model.joblib
python sensor.py --simulate streaming   # simulasikan flow live-stream -> trigger boost
python sensor.py --simulate normal      # simulasikan flow normal -> tidak ada aksi
```

> Catatan: `sensor.py` memakai URL VM2 hardcoded `http://10.0.0.1:8000`. Untuk demo 1-mesin
> ini, edit `VM2_GATEWAY_URL` di `sensor.py` menjadi `http://127.0.0.1:8000`, atau uji
> langsung endpoint VM2 dengan `curl` (lihat bagian 5).

---

## 4. Cara Menjalankan — Mode Penuh (3 VM, demo nyata ke juri)

1. Siapkan 3 VM Linux (VirtualBox/VMware/Proxmox), **networking mode: Bridged/Internal Network**
   agar saling terhubung, dengan IP sesuai desain:
   - VM1 (AI Sensing): `192.168.1.100`
   - VM2 (API Gateway): `10.0.0.1`
   - VM3 (Core Network Exec): `10.0.0.2`
2. Install dependensi di tiap VM (`pip install -r requirements.txt`), plus di VM3:
   `sudo apt install iperf3 iproute2`.
3. Di **VM3**, jalankan setup tc & iperf3 (butuh root):
   ```bash
   sudo ./setup_tc.sh eth0
   sudo ./start_iperf.sh
   sudo python3 -m uvicorn agent:app --host 0.0.0.0 --port 9000   # tanpa DRY_RUN
   ```
4. Di **VM2**:
   ```bash
   VM3_AGENT_URL=http://10.0.0.2:9000 API_TOKEN=poc-demo-token-12345 \
     uvicorn main:app --host 0.0.0.0 --port 8000
   ```
5. Di **VM1**:
   ```bash
   python train_model.py
   sudo python3 sensor.py --iface eth0 --target-ip 10.0.0.5   # capture nyata via scapy
   ```
6. Generate trafik latar (dari mesin lain / VM4 sebagai "audiens"):
   ```bash
   iperf3 -c 10.0.0.2 -p 5201 -t 120                # trafik TCP download (pesaing bandwidth)
   iperf3 -c 10.0.0.2 -p 5202 -u -b 8M -t 120        # trafik UDP live-stream
   ```

---

## 5. Skenario Demo untuk Juri (sesuai desain PoC)

**Langkah 1 — Kondisi Normal (Congested).**
Jalankan kedua iperf3 client bersamaan tanpa boost aktif. Tunjukkan `watch -n1 "tc -s class show dev eth0"`
di VM3 — trafik UDP (live stream) berebut bandwidth dengan TCP (download), packet loss/jitter tinggi.

**Langkah 2 — AI Trigger.**
Jalankan `sensor.py` di VM1 (mode `--simulate streaming` atau capture nyata). Tunjukkan log terminal:
fitur flow yang diekstrak, hasil klasifikasi RandomForest beserta confidence, dan payload POST yang
dikirim ke VM2.

**Langkah 3 — Kondisi Teroptimasi (Boosted).**
Tunjukkan log VM2 (auth sukses, session dibuat) dan VM3 (`tc class change` diterapkan). Tunjukkan
`tc -s class show dev eth0` lagi — kelas `1:10` (live stream) sekarang mendapat rate/ceil jauh
lebih besar. Jika memungkinkan, tunjukkan grafik iperf3 real-time: packet loss UDP turun ke ~0%.

**Langkah 4 (opsional) — Release.**
```bash
curl -X DELETE http://10.0.0.1:8000/api/v1/qos/boost/<session_id> \
  -H "Authorization: Bearer poc-demo-token-12345"
```
Tunjukkan QoS kembali ke baseline.

---

## 6. Uji Cepat API dengan `curl`

```bash
# Request boost
curl -X POST http://<VM2_IP>:8000/api/v1/qos/boost \
  -H "Authorization: Bearer poc-demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "ZTE-MC801A-9982X",
    "intent": "live_stream_boost",
    "qos_profile": "PREMIUM_UPLINK",
    "target_ip": "10.0.0.5",
    "duration_seconds": 3600
  }'

# Lihat sesi aktif
curl http://<VM2_IP>:8000/api/v1/qos/sessions -H "Authorization: Bearer poc-demo-token-12345"

# Sudahi sesi lebih awal
curl -X DELETE http://<VM2_IP>:8000/api/v1/qos/boost/<session_id> \
  -H "Authorization: Bearer poc-demo-token-12345"
```

Coba juga dengan `device_id` yang tidak terdaftar untuk menunjukkan proteksi Zero-Trust (harus `403`).

---

## 7. Hasil Pengujian yang Sudah Dilakukan

Sudah diverifikasi jalan di lingkungan sandbox (mode dry-run, tanpa `tc` root nyata):

- ✅ `train_model.py` — dataset sintetis 4000 sampel, RandomForest, akurasi 100% pada data
  sintetis (fitur streaming vs normal memang didesain terpisah jelas — di data nyata akurasi
  akan lebih rendah, siapkan narasi ini untuk juri).
- ✅ `sensor.py --simulate streaming` — fitur terekstrak (`uplink_ratio=0.85`), diklasifikasi
  benar sebagai `LIVE STREAMING` (confidence 78%), payload boost terbentuk benar.
- ✅ `sensor.py --simulate normal` — diklasifikasi benar sebagai `NORMAL`, tidak ada aksi diambil.
- ✅ VM2 `/api/v1/qos/boost` — menerima request valid, auth Bearer token lolos, device
  whitelist lolos, meneruskan ke VM3, mengembalikan `session_id` dan status `ACTIVE` (HTTP 200).
- ✅ VM2 menolak `device_id` tak terdaftar dengan `403 Forbidden` (Zero-Trust bekerja).
- ✅ VM3 `/boost` menerima perintah dan memanggil `boost_qos.sh` (di sandbox: dry-run,
  di VM Linux nyata dengan root: benar-benar mengeksekusi `tc class change`).

Yang **belum** diuji di sandbox ini (perlu lingkungan VM/Linux nyata dengan akses root +
interface jaringan): eksekusi `tc` sungguhan, capture paket nyata dengan `scapy`, dan
throughput/packet-loss aktual dari `iperf3`. Semua script sudah disiapkan dan siap dijalankan
begitu tersedia mesin dengan hak akses tersebut — ikuti bagian 4.

---

## 8. Keterbatasan & Catatan Jujur

- **RandomForest di atas hanya dilatih dari data sintetis**, bukan trafik nyata. Untuk PoC/demo
  ini cukup, tapi sebutkan ke juri bahwa fase produksi butuh dataset trafik nyata dan mungkin
  fine-tuning fitur tambahan (mis. burstiness, jitter).
- **Autentikasi VM2 disederhanakan** (whitelist statis + token statis) untuk kebutuhan PoC.
  Produksi butuh integrasi OAuth2 client-credentials sungguhan dan validasi USIM via HSS/UDM.
- **`tc` HTB filtering** di `setup_tc.sh` memakai port iperf3 (5201/5202) sebagai pembeda
  trafik untuk kesederhanaan demo. Di skenario nyata, pembedaan trafik per-`target_ip`/per-subscriber
  dilakukan PCF melalui PCC rules (5-tuple + 5QI), bukan port statis — ini yang direpresentasikan
  oleh parameter `target_ip` di payload API.
- **NEF nyata (3GPP TS 29.522 AsSessionWithQoS)** tidak diimplementasikan penuh — VM2 di sini
  adalah *NEF-style gateway* yang disederhanakan agar bisa didemokan tanpa Core 5G fisik/Open5GS.
  Untuk audiensi yang familiar Open5GS: jelaskan bahwa desain ini kompatibel-konsep dengan
  cara AF memanggil `Npcf_PolicyAuthorization` di PCF Open5GS.
