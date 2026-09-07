"""
main.py — VM2 (API Orchestrator & NEF Gateway, mensimulasikan middleware ZTE/Operator Cloud)

Peran:
  - Middleware + firewall antara Edge AI (VM1) dan Core Network Emulator (VM3).
  - Autentikasi sederhana ala Zero-Trust: whitelist device_id (mensimulasikan
    USIM-based auth) + Bearer token (mensimulasikan OAuth 2.0 client-credentials).
  - Mengadopsi bentuk request CAMARA QoD (Quality on Demand) API.
  - Meneruskan perintah teknis (setara Nnef_TrafficInfluence -> PCF -> SMF/UPF)
    ke VM3 lewat HTTP call ke network-agent.

Jalankan:
  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
import time
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

app = FastAPI(title="NEF Gateway PoC", version="0.1.0")

# --- Konfigurasi PoC (ganti sesuai IP VM3 kamu) ---
VM3_AGENT_URL = os.getenv("VM3_AGENT_URL", "http://10.0.0.2:9000")
API_TOKEN = os.getenv("API_TOKEN", "poc-demo-token-12345")  # simulasi OAuth2 bearer token

# --- Zero-Trust: whitelist device (simulasi USIM-based auth) ---
ALLOWED_DEVICES = {"ZTE-MC801A-9982X"}

# in-memory store sesi aktif (untuk demo; production pakai Redis/DB)
active_sessions: dict[str, dict] = {}


class QoSBoostRequest(BaseModel):
    device_id: str = Field(..., examples=["ZTE-MC801A-9982X"])
    intent: Literal["live_stream_boost"]
    qos_profile: Literal["PREMIUM_UPLINK", "STANDARD"]
    target_ip: str
    duration_seconds: int = Field(gt=0, le=14400)


def verify_auth(authorization: str | None):
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized: token tidak valid")


def verify_device(device_id: str):
    if device_id not in ALLOWED_DEVICES:
        raise HTTPException(status_code=403, detail="Forbidden: device tidak terdaftar (Zero-Trust)")


@app.post("/api/v1/qos/boost")
def qos_boost(req: QoSBoostRequest, authorization: str | None = Header(default=None)):
    """Endpoint utama — setara CAMARA QoD `POST /sessions` yang disederhanakan."""
    verify_auth(authorization)
    verify_device(req.device_id)

    # Teruskan ke VM3 (Core Network Emulator): trigger tc HTB boost untuk target_ip
    try:
        r = requests.post(
            f"{VM3_AGENT_URL}/boost",
            json={"target_ip": req.target_ip, "profile": req.qos_profile},
            timeout=5,
        )
        r.raise_for_status()
        vm3_result = r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi Core Network Emulator (VM3): {e}")

    session_id = f"sess-{int(time.time())}-{req.target_ip.replace('.', '')}"
    active_sessions[session_id] = {
        "device_id": req.device_id,
        "target_ip": req.target_ip,
        "qos_profile": req.qos_profile,
        "expires_at": time.time() + req.duration_seconds,
    }

    return {
        "status": "ACTIVE",
        "session_id": session_id,
        "qos_profile": req.qos_profile,
        "target_ip": req.target_ip,
        "duration_seconds": req.duration_seconds,
        "vm3_result": vm3_result,
    }


@app.delete("/api/v1/qos/boost/{session_id}")
def qos_release(session_id: str, authorization: str | None = Header(default=None)):
    """Hentikan boost lebih awal (setara CAMARA QoD `DELETE /sessions/{id}`)."""
    verify_auth(authorization)
    session = active_sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan")

    try:
        r = requests.post(
            f"{VM3_AGENT_URL}/reset",
            json={"target_ip": session["target_ip"]},
            timeout=5,
        )
        r.raise_for_status()
        vm3_result = r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Gagal menghubungi VM3: {e}")

    return {"status": "RELEASED", "session_id": session_id, "vm3_result": vm3_result}


@app.get("/api/v1/qos/sessions")
def list_sessions(authorization: str | None = Header(default=None)):
    verify_auth(authorization)
    return {"active_sessions": active_sessions}


@app.get("/health")
def health():
    return {"status": "ok", "vm3_agent": VM3_AGENT_URL}
