# captcha_solver.py — solve Cloudflare Turnstile via CapSolver API
#
# Dokumentasi: https://docs.capsolver.com/guide/captcha/Turnstile.html
# Daftar di https://capsolver.com untuk dapat API key

import time
import logging
import requests

log = logging.getLogger(__name__)

CAPSOLVER_API = "https://api.capsolver.com"

# Cloudflare sign-up Turnstile site key (tetap sama untuk semua user)
CF_SIGNUP_URL     = "https://dash.cloudflare.com/sign-up"
CF_TURNSTILE_KEY  = "0x4AAAAAAA-3X2SmBEn7SZiS"  # site key Cloudflare sign-up


def solve_turnstile(api_key: str, url: str = CF_SIGNUP_URL, site_key: str = CF_TURNSTILE_KEY) -> str | None:
    """
    Solve Cloudflare Turnstile via CapSolver.
    Returns token string atau None kalau gagal.
    """
    try:
        # 1. Buat task
        log.info("[capsolver] Membuat Turnstile task...")
        resp = requests.post(
            f"{CAPSOLVER_API}/createTask",
            json={
                "clientKey": api_key,
                "task": {
                    "type":    "AntiTurnstileTaskProxyLess",
                    "websiteURL": url,
                    "websiteKey": site_key,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("errorId") != 0:
            log.error(f"[capsolver] Create task error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        log.info(f"[capsolver] Task ID: {task_id}")

        # 2. Poll hasil task
        for _ in range(30):  # max 30 * 3s = 90 detik
            time.sleep(3)
            result_resp = requests.post(
                f"{CAPSOLVER_API}/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=30,
            )
            result_resp.raise_for_status()
            result = result_resp.json()

            status = result.get("status")
            if status == "ready":
                token = result.get("solution", {}).get("token")
                log.info(f"[capsolver] ✓ Turnstile solved: {token[:20]}...")
                return token
            elif status == "failed":
                log.error(f"[capsolver] Task failed: {result.get('errorDescription')}")
                return None
            # status == "processing" → lanjut polling

        log.error("[capsolver] Timeout menunggu solve result")
        return None

    except Exception as e:
        log.error(f"[capsolver] Exception: {e}")
        return None


def get_balance(api_key: str) -> float | None:
    """Cek saldo CapSolver."""
    try:
        resp = requests.post(
            f"{CAPSOLVER_API}/getBalance",
            json={"clientKey": api_key},
            timeout=10,
        )
        data = resp.json()
        if data.get("errorId") == 0:
            balance = data.get("balance", 0)
            log.info(f"[capsolver] Balance: ${balance}")
            return float(balance)
        return None
    except Exception:
        return None
