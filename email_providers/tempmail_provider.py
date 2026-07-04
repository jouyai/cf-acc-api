# email_providers/tempmail_provider.py — generate dan baca inbox via mail.tm API
#
# Dokumentasi mail.tm: https://docs.mail.tm
# Gratis, tidak perlu API key eksternal.

import random
import string
import time
import requests

BASE_URL = "https://api.mail.tm"
HEADERS  = {"Content-Type": "application/json", "Accept": "application/json"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _get_domains() -> list[str]:
    """Ambil daftar domain aktif dari mail.tm."""
    resp = requests.get(f"{BASE_URL}/domains", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # response bisa berupa {"hydra:member": [...]} atau list langsung
    members = data.get("hydra:member", data) if isinstance(data, dict) else data
    return [d["domain"] for d in members if d.get("isActive")]


def _random_string(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ── public API ───────────────────────────────────────────────────────────────

def create_account() -> dict:
    """
    Buat akun mail.tm baru.
    Return: {"email": "...", "password": "...", "token": "..."}
    """
    domains = _get_domains()
    if not domains:
        raise RuntimeError("Tidak ada domain aktif di mail.tm")

    domain   = random.choice(domains)
    address  = f"{_random_string()}@{domain}"
    password = _random_string(16)

    # buat akun
    resp = requests.post(
        f"{BASE_URL}/accounts",
        json={"address": address, "password": password},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()

    # ambil token autentikasi
    token_resp = requests.post(
        f"{BASE_URL}/token",
        json={"address": address, "password": password},
        headers=HEADERS,
        timeout=15,
    )
    token_resp.raise_for_status()
    token = token_resp.json()["token"]

    return {"email": address, "password": password, "token": token}


def wait_for_email(
    token: str,
    subject_contains: str = "Cloudflare",
    timeout: int = 120,
    interval: int = 5,
) -> dict | None:
    """
    Poll inbox sampai ada email dengan subject tertentu.
    Return message dict atau None kalau timeout.
    """
    auth_headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout

    while time.time() < deadline:
        resp = requests.get(f"{BASE_URL}/messages", headers=auth_headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("hydra:member", data) if isinstance(data, dict) else data

        for msg in messages:
            if subject_contains.lower() in msg.get("subject", "").lower():
                # ambil detail lengkap pesan (termasuk body)
                detail_resp = requests.get(
                    f"{BASE_URL}/messages/{msg['id']}",
                    headers=auth_headers,
                    timeout=15,
                )
                detail_resp.raise_for_status()
                return detail_resp.json()

        time.sleep(interval)

    return None


def extract_verification_link(message: dict) -> str | None:
    """
    Cari link verifikasi Cloudflare dari body email.
    Cek HTML body dulu, fallback ke text body.
    """
    import re

    body = message.get("html", "") or message.get("text", "")
    if isinstance(body, list):
        body = " ".join(body)

    # Cloudflare verification link biasanya mengandung 'verify' atau 'confirm'
    pattern = r'https://[^\s"\'<>]+(?:verify|confirm|activate)[^\s"\'<>]*'
    matches = re.findall(pattern, body, re.IGNORECASE)
    return matches[0] if matches else None
