# verify_email.py — handle verifikasi email Cloudflare
#
# Dua mode:
#   "google"   → tidak perlu verifikasi (Google OAuth sudah verified)
#   "tempmail" → poll mail.tm inbox, extract link, buka di browser otomatis

import time
import logging
import re

import config
from email_providers import tempmail_provider

log = logging.getLogger(__name__)

DASHBOARD_URL = "https://dash.cloudflare.com"


def _is_verified(page) -> bool:
    """Cek apakah sudah masuk ke dashboard."""
    try:
        url = page.url
        return (
            DASHBOARD_URL in url
            and "sign-up" not in url
            and "verify" not in url
            and "email" not in url
        )
    except Exception:
        return False


def wait_verified_tempmail(page, tm_token: str) -> bool:
    """
    Poll inbox mail.tm, extract link verifikasi, buka di browser.
    Returns True kalau verifikasi berhasil.
    """
    log.info("[verify] Polling inbox mail.tm...")

    message = tempmail_provider.wait_for_email(
        token=tm_token,
        subject_contains="Cloudflare",
        timeout=config.EMAIL_POLL_TIMEOUT,
        interval=config.EMAIL_POLL_INTERVAL,
    )

    if message is None:
        log.warning("[verify] Email verifikasi tidak diterima dalam batas waktu.")
        return False

    log.info(f"[verify] Email diterima: {message.get('subject', '(no subject)')}")

    link = tempmail_provider.extract_verification_link(message)
    if not link:
        # Coba cari link apapun dari Cloudflare di body
        body = message.get("html", "") or message.get("text", "")
        if isinstance(body, list):
            body = " ".join(body)
        matches = re.findall(r'https://[^\s"\'<>]+cloudflare[^\s"\'<>]*', body, re.IGNORECASE)
        if matches:
            link = matches[0]

    if not link:
        log.error("[verify] Gagal extract link verifikasi dari email.")
        return False

    log.info(f"[verify] Membuka link verifikasi...")
    try:
        page.goto(link, wait_until="domcontentloaded")
        # Tunggu redirect ke dashboard
        deadline = time.time() + 30
        while time.time() < deadline:
            if _is_verified(page):
                log.info("[verify] ✓ Verifikasi berhasil.")
                return True
            time.sleep(1)
        log.warning(f"[verify] Tidak redirect ke dashboard. URL: {page.url}")
        return False
    except Exception as e:
        log.error(f"[verify] Gagal buka link verifikasi: {e}")
        return False


def verify_email(page, email_mode: str, tm_token: str | None = None) -> bool:
    """
    Dispatch ke handler yang sesuai berdasarkan email_mode.

    Args:
        page       : Playwright page object
        email_mode : "google" atau "tempmail"
        tm_token   : token mail.tm (wajib kalau mode tempmail)

    Returns True kalau verifikasi sukses (atau tidak diperlukan).
    """
    if email_mode == "google":
        # Google OAuth sudah verified — tidak perlu langkah tambahan
        return True
    elif email_mode == "tempmail":
        if not tm_token:
            raise ValueError("tm_token wajib diisi untuk mode tempmail")
        return wait_verified_tempmail(page, tm_token)
    else:
        raise ValueError(f"email_mode tidak dikenal: {email_mode}")
