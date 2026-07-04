# email_providers/mailsac_provider.py — generate dan baca inbox via Mailsac API
#
# Dokumentasi: https://mailsac.com/docs/api
# Butuh API key dari mailsac.com (ada free tier)

import random
import string
import time
import re
import requests
import logging

log = logging.getLogger(__name__)

BASE_URL = "https://mailsac.com/api"


def _random_string(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _generate_password(length: int = 14) -> str:
    """Generate password yang memenuhi syarat Cloudflare."""
    chars = string.ascii_letters + string.digits + "!@#$%&"
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("!@#$%&"),
    ]
    pwd += random.choices(chars, k=length - 4)
    random.shuffle(pwd)
    return "".join(pwd)


def create_account(api_key: str) -> dict:
    """
    Buat alamat email random di mailsac.com.
    Mailsac pakai format: <random>@mailsac.com
    Tidak perlu register — semua address @mailsac.com otomatis bisa terima email.

    Return: {"email": "...", "password": "..."}
    """
    username = _random_string(12)
    email    = f"{username}@mailsac.com"
    password = _generate_password()
    return {"email": email, "password": password, "api_key": api_key}


def wait_for_email(
    email: str,
    api_key: str,
    subject_contains: str = "Cloudflare",
    timeout: int = 120,
    interval: int = 5,
) -> dict | None:
    """
    Poll inbox Mailsac sampai ada email dari Cloudflare.
    Return message dict atau None kalau timeout.
    """
    headers = {
        "Mailsac-Key": api_key,
        "Accept": "application/json",
    }
    username = email.split("@")[0]
    deadline = time.time() + timeout
    seen_ids = set()

    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{BASE_URL}/addresses/{email}/messages",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            messages = resp.json()

            log.debug(f"[mailsac] Inbox {email}: {len(messages)} pesan")

            for msg in messages:
                msg_id  = msg.get("_id") or msg.get("id")
                subject = msg.get("subject", "")
                from_addr = str(msg.get("from", [{}])[0].get("address", "") if isinstance(msg.get("from"), list) else msg.get("from", ""))

                # Cari email Cloudflare
                is_cloudflare = (
                    subject_contains.lower() in subject.lower()
                    or "cloudflare" in from_addr.lower()
                )

                if is_cloudflare and msg_id not in seen_ids:
                    seen_ids.add(msg_id)
                    # Ambil body text email
                    body_resp = requests.get(
                        f"{BASE_URL}/text/{email}/{msg_id}",
                        headers=headers,
                        timeout=15,
                    )
                    body_resp.raise_for_status()
                    body_text = body_resp.text

                    log.info(f"[mailsac] Email Cloudflare ditemukan: {subject}")
                    return {
                        "subject": subject,
                        "from":    from_addr,
                        "text":    body_text,
                        "html":    body_text,
                    }

                seen_ids.add(msg_id)

        except Exception as e:
            log.warning(f"[mailsac] Error polling: {e}")

        time.sleep(interval)

    return None


def extract_verification_link(message: dict) -> str | None:
    """Cari link verifikasi Cloudflare dari body email."""
    body = message.get("html", "") or message.get("text", "")
    if isinstance(body, list):
        body = " ".join(body)

    # Cari link verifikasi Cloudflare
    patterns = [
        r'https://[^\s"\'<>]+(?:verify|confirm|activate)[^\s"\'<>]*',
        r'https://dash\.cloudflare\.com[^\s"\'<>]*',
        r'https://[^\s"\'<>]*cloudflare[^\s"\'<>]*(?:verify|confirm)[^\s"\'<>]*',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, body, re.IGNORECASE)
        if matches:
            return matches[0]
    return None
