"""
agent.py — VM3 (Core Network Execution Node, mensimulasikan PCF/UPF/gNodeB)

Menerima perintah teknis dari VM2 (API Orchestrator / NEF Gateway) dan
mengeksekusinya sebagai perubahan `tc` (Linux Traffic Control) nyata di
data plane — analog dengan PCF mengubah aturan QoS lalu UPF/gNodeB
mengalokasikan Guaranteed Bitrate (GBR) Resource Block.

Endpoint:
  POST /boost  {"target_ip": "...", "profile": "PREMIUM_UPLINK"}
  POST /reset  {"target_ip": "..."}

Jalankan:
  sudo -E $(which python3) -m uvicorn agent:app --host 0.0.0.0 --port 9000

Catatan:
  - Butuh root untuk menjalankan `tc`.
  - Jalankan setup_tc.sh sekali dahulu sebelum agent ini dipakai.
  - Set DRY_RUN=1 untuk demo tanpa hak akses root / interface nyata
    (perintah tc hanya dicetak ke log, tidak dieksekusi) — berguna untuk
    presentasi cepat tanpa provisioning VM penuh.
"""

import os
import subprocess

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Core Network Execution Agent PoC", version="0.1.0")

IFACE = os.getenv("QOS_IFACE", "eth0")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class BoostRequest(BaseModel):
    target_ip: str
    profile: str = "PREMIUM_UPLINK"


class ResetRequest(BaseModel):
    target_ip: str


def run_script(script_name: str, *args: str) -> str:
    cmd = ["bash", os.path.join(SCRIPT_DIR, script_name), *args]
    if DRY_RUN:
        log = f"[DRY_RUN] Perintah tidak dieksekusi: {' '.join(cmd)}"
        print(log)
        return log

    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menjalankan {script_name}: {e.stderr or e}",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=f"Script {script_name} tidak ditemukan / `tc` tidak tersedia di sistem ini.",
        )


@app.post("/boost")
def boost(req: BoostRequest):
    print(f"[VM3] Menerima perintah BOOST untuk target_ip={req.target_ip} profile={req.profile}")
    output = run_script("boost_qos.sh", IFACE, req.profile)
    return {"action": "boost", "target_ip": req.target_ip, "profile": req.profile,
            "iface": IFACE, "dry_run": DRY_RUN, "tc_output": output}


@app.post("/reset")
def reset(req: ResetRequest):
    print(f"[VM3] Menerima perintah RESET untuk target_ip={req.target_ip}")
    output = run_script("reset_qos.sh", IFACE)
    return {"action": "reset", "target_ip": req.target_ip,
            "iface": IFACE, "dry_run": DRY_RUN, "tc_output": output}


@app.get("/health")
def health():
    return {"status": "ok", "iface": IFACE, "dry_run": DRY_RUN}
