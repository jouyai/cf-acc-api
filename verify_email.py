# verify_email.py — handle verifikasi email Cloudflare
#
# Dua mode:
#   "file"     → tunggu user klik link sendiri, poll URL hingga redirect ke dashboard
#   "tempmail" → poll mail.tm inbox, extract link, buka di browser otomatis

import time
import logging

import config
from email_providers import tempmail_provider

log = logging.getLogger(__name__)

DASHBOARD_URL = "https://dash.cloudflare.com"


def _is_verified(page) -> bool:
    """Cek apakah sudah masuk ke dashboard (berarti verifikasi sukses)."""
    url = page.url
    return (
        DASHBOARD_URL in url
        and "sign-up" not in url
        and "verify" not in url
        and "email" not in url
    )


# ── Mode: file (email milik sendiri) ─────────────────────────────────────────

def wait_verified_manual(page, timeout: int = 300) -> bool:
    """
    Tunggu user klik link verifikasi di inbox mereka sendiri.
    Script akan poll URL browser setiap beberapa detik.

    Returns True kalau terdeteksi masuk dashboard dalam `timeout` detik.
    """
    log.info("[verify] Mode manual — menunggu user klik link verifikasi di inbox...")
    print("\n⏳  Silakan buka inbox email Anda dan klik link verifikasi dari Cloudflare.")
    print(f"    Menunggu hingga {timeout} detik...\n")

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _is_verified(page):
                log.info("[verify] Verifikasi berhasil (terdeteksi dari URL).")
                return True
            # Cloudflare kadang redirect otomatis setelah klik link di tab lain,
            # coba refresh halaman untuk trigger redirect
            current = page.url
            if "verify" in current or "email" in current:
                time.sleep(5)
                page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
        time.sleep(5)

    log.warning("[verify] Timeout menunggu verifikasi manual.")
    return False


# ── Mode: tempmail (otomatis via mail.tm) ────────────────────────────────────

def wait_verified_tempmail(page, tm_token: str) -> bool:
    """
    Poll inbox mail.tm, extract link verifikasi, buka di browser.

    Args:
        page: Playwright page object
        tm_token: Bearer token akun mail.tm

    Returns True kalau verifikasi berhasil.
    """
    log.info("[verify] Mode tempmail — polling inbox mail.tm...")

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
        log.error("[verify] Gagal extract link verifikasi dari email.")
        return False

    log.info(f"[verify] Membuka link verifikasi: {link}")
    try:
        page.goto(link, wait_until="domcontentloaded")
        # Tunggu redirect ke dashboard
        page.wait_for_url(
            lambda url: DASHBOARD_URL in url and "sign-up" not in url,
            timeout=30000,
        )
        log.info("[verify] Verifikasi berhasil via tempmail.")
        return True
    except Exception as e:
        log.error(f"[verify] Gagal membuka link verifikasi: {e}")
        return False


# ── Entry point ──────────────────────────────────────────────────────────────

def verify_email(page, email_mode: str, tm_token: str | None = None) -> bool:
    """
    Dispatch ke handler yang sesuai berdasarkan email_mode.

    Args:
        page: Playwright page object
        email_mode: "file" atau "tempmail"
        tm_token: token mail.tm (wajib kalau mode tempmail)

    Returns True kalau verifikasi sukses.
    """
    if email_mode == "tempmail":
        if not tm_token:
            raise ValueError("tm_token wajib diisi untuk mode tempmail")
        return wait_verified_tempmail(page, tm_token)
    else:
        return wait_verified_manual(page, timeout=300)
