# verify_email.py — handle verifikasi email Cloudflare
#
# Dua mode:
#   "google"   → tidak perlu verifikasi (Google OAuth sudah verified)
#   "tempmail" → poll inbox (mail.tm atau mailsac) untuk link verifikasi

import time
import logging
import re

import config
from email_providers import tempmail_provider
from email_providers import mailsac_provider

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


def _open_verification_link(page, link: str) -> bool:
    """Buka link verifikasi di browser dan tunggu redirect ke dashboard."""
    log.info(f"[verify] Membuka link verifikasi...")
    try:
        page.goto(link, wait_until="domcontentloaded")
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


def wait_verified_mailsac(page, email: str) -> bool:
    """Verifikasi via Mailsac API."""
    if not config.MAILSAC_API_KEY:
        log.error("[verify] MAILSAC_API_KEY tidak di-set di config/.env")
        return False

    log.info(f"[verify] Polling inbox Mailsac untuk {email}...")
    message = mailsac_provider.wait_for_email(
        email=email,
        api_key=config.MAILSAC_API_KEY,
        subject_contains="Cloudflare",
        timeout=config.EMAIL_POLL_TIMEOUT,
        interval=config.EMAIL_POLL_INTERVAL,
    )

    if message is None:
        log.warning("[verify] Email verifikasi tidak diterima (Mailsac).")
        return False

    link = mailsac_provider.extract_verification_link(message)
    if not link:
        log.error("[verify] Gagal extract link verifikasi dari email Mailsac.")
        return False

    return _open_verification_link(page, link)


def wait_verified_mailtm(page, tm_token: str) -> bool:
    """Verifikasi via mail.tm API."""
    log.info("[verify] Polling inbox mail.tm...")
    message = tempmail_provider.wait_for_email(
        token=tm_token,
        subject_contains="Cloudflare",
        timeout=config.EMAIL_POLL_TIMEOUT,
        interval=config.EMAIL_POLL_INTERVAL,
    )

    if message is None:
        log.warning("[verify] Email verifikasi tidak diterima (mail.tm).")
        return False

    link = tempmail_provider.extract_verification_link(message)
    if not link:
        body = message.get("html", "") or message.get("text", "")
        if isinstance(body, list):
            body = " ".join(body)
        matches = re.findall(r'https://[^\s"\'<>]+cloudflare[^\s"\'<>]*', body, re.IGNORECASE)
        if matches:
            link = matches[0]

    if not link:
        log.error("[verify] Gagal extract link verifikasi dari email mail.tm.")
        return False

    return _open_verification_link(page, link)


def verify_email(page, email_mode: str, tm_token: str | None = None, email: str | None = None) -> bool:
    """
    Dispatch ke handler yang sesuai.

    Args:
        page       : Playwright page object
        email_mode : "google", "tempmail"
        tm_token   : token mail.tm (untuk provider mailtm)
        email      : alamat email (untuk provider mailsac)
    """
    if email_mode == "google":
        return True

    if email_mode == "tempmail":
        provider = config.TEMPMAIL_PROVIDER
        if provider == "mailsac":
            if not email:
                raise ValueError("email wajib untuk provider mailsac")
            return wait_verified_mailsac(page, email)
        else:
            # Default: mail.tm
            if not tm_token:
                raise ValueError("tm_token wajib untuk provider mailtm")
            return wait_verified_mailtm(page, tm_token)

    raise ValueError(f"email_mode tidak dikenal: {email_mode}")
