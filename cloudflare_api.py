# cloudflare_api.py — operasi Cloudflare via internal dashboard API
#
# Cloudflare dashboard pakai endpoint https://dash.cloudflare.com/api/v4/
# dengan header x-cross-site-security: dash dan auth via cookies browser.

import logging
import requests
import re

log = logging.getLogger(__name__)

DASH_API = "https://dash.cloudflare.com/api/v4"

HEADERS = {
    "User-Agent":            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept":                "application/json",
    "Accept-Language":       "en-US,en;q=0.9",
    "x-cross-site-security": "dash",
    "Origin":                "https://dash.cloudflare.com",
    "Referer":               "https://dash.cloudflare.com/",
}

# Permission group IDs untuk Workers AI (verified dari debug_api3.py)
WORKERS_AI_READ_ID  = "a92d2450e05d4e7bb7d0a64968f83d11"
WORKERS_AI_WRITE_ID = "bacc64e0f6c34fc0883a1223f938a104"


def extract_cookies_from_browser(page) -> dict:
    """Extract cookies dari Playwright page setelah login."""
    try:
        cookies = page.context.cookies()
        # Filter hanya cookies Cloudflare (bukan Google)
        cf_cookies = {
            c["name"]: c["value"] for c in cookies
            if "cloudflare.com" in c.get("domain", "")
        }
        log.info(f"[cf_api] Extracted {len(cf_cookies)} Cloudflare cookies")
        return cf_cookies
    except Exception as e:
        log.error(f"[cf_api] Gagal extract cookies: {e}")
        return {}


def make_session(cookies: dict) -> requests.Session:
    """Buat requests.Session dengan cookies dan headers Cloudflare."""
    session = requests.Session()
    session.headers.update(HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".cloudflare.com")
    return session


def get_account_id(session: requests.Session) -> str | None:
    """Ambil Account ID via Cloudflare dashboard API."""
    try:
        resp = session.get(f"{DASH_API}/accounts", timeout=15)
        data = resp.json()
        if data.get("success") and data.get("result"):
            account_id = data["result"][0]["id"]
            log.info(f"[cf_api] Account ID: {account_id}")
            return account_id
        log.warning(f"[cf_api] get_account_id gagal: {data.get('errors')}")
        return None
    except Exception as e:
        log.error(f"[cf_api] get_account_id exception: {e}")
        return None


def create_workers_ai_token(
    session: requests.Session,
    account_id: str,
    token_name: str = "workers-ai-auto",
) -> str | None:
    """
    Buat Workers AI API token via Cloudflare dashboard API.
    Menggunakan permission groups Workers AI Read + Write.
    """
    try:
        if not account_id:
            log.warning("[cf_api] account_id kosong, skip create token")
            return None

        payload = {
            "name": token_name,
            "policies": [
                {
                    "effect": "allow",
                    "resources": {
                        f"com.cloudflare.api.account.{account_id}": "*"
                    },
                    "permission_groups": [
                        {"id": WORKERS_AI_READ_ID,  "name": "Workers AI Read"},
                        {"id": WORKERS_AI_WRITE_ID, "name": "Workers AI Write"},
                    ],
                }
            ],
        }

        resp = session.post(
            f"{DASH_API}/user/tokens",
            json=payload,
            timeout=15,
        )
        data = resp.json()

        if data.get("success") and data.get("result"):
            token = data["result"].get("value")
            log.info(f"[cf_api] ✓ Token dibuat via API: {token[:10]}...")
            return token

        log.warning(f"[cf_api] create_token gagal: {data.get('errors')}")
        return None

    except Exception as e:
        log.error(f"[cf_api] create_token exception: {e}")
        return None


def wait_for_dashboard_session(page, timeout: int = 60000) -> bool:
    """
    Tunggu Cloudflare dashboard fully loaded dan session aktif.
    Handle kasus landing di /login/google?oidcJwt=... atau /login setelah OAuth.
    """
    import time
    try:
        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            try:
                url = page.url
            except Exception:
                return False

            # Sudah di dashboard — selesai
            if (
                "dash.cloudflare.com" in url
                and "login" not in url
                and "sign-up" not in url
            ):
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                log.info(f"[cf_api] Dashboard session aktif: {url[:80]}")
                return True

            # Masih di /login/google?oidcJwt=... — tunggu auto-redirect
            if "login/google" in url or "oidcJwt" in url:
                log.info("[cf_api] Menunggu JWT redirect ke dashboard...")
                try:
                    page.wait_for_url(
                        lambda u: "dash.cloudflare.com" in u and "login" not in u,
                        timeout=15000,
                    )
                    continue
                except Exception:
                    # Kalau timeout, navigate manual
                    log.info("[cf_api] JWT tidak auto-redirect, navigate manual...")
                    try:
                        page.goto("https://dash.cloudflare.com", wait_until="domcontentloaded")
                    except Exception:
                        pass

            # Di /login tapi bukan /login/google — mungkin perlu klik tombol
            elif url.rstrip("/").endswith("/login") or "/login?" in url:
                log.info("[cf_api] Masih di halaman login, tunggu redirect...")
                try:
                    page.wait_for_url(
                        lambda u: "login" not in u.split("cloudflare.com")[-1].split("?")[0],
                        timeout=10000,
                    )
                    continue
                except Exception:
                    try:
                        page.goto("https://dash.cloudflare.com", wait_until="domcontentloaded")
                    except Exception:
                        pass

            time.sleep(0.8)

        log.warning(f"[cf_api] Timeout menunggu dashboard. URL terakhir: {page.url[:80]}")
        return False

    except Exception as e:
        log.error(f"[cf_api] wait_for_dashboard_session: {e}")
        return False
