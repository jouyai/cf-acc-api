# get_apikey.py — ambil Account ID dan buat Workers AI API token

import time
import random
import logging
import re

log = logging.getLogger(__name__)

DASHBOARD_URL   = "https://dash.cloudflare.com"
USER_TOKENS_URL = "https://dash.cloudflare.com/profile/api-tokens"


def _d(min_s: float = 0.3, max_s: float = 0.7):
    time.sleep(random.uniform(min_s, max_s))


def _wait_visible(page, selector: str, timeout: int = 15000) -> bool:
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        return True
    except Exception:
        return False


# ── Ambil Account ID ─────────────────────────────────────────────────────────

def get_account_id(page) -> str | None:
    try:
        log.info("[apikey] Mengambil Account ID...")

        # Handle kasus landing di /login/google?oidcJwt=... setelah Google OAuth
        # Cloudflare perlu proses JWT ini sebelum redirect ke dashboard
        if "login/google" in page.url or "oidcJwt" in page.url:
            log.info("[apikey] Menunggu Cloudflare proses JWT redirect...")
            try:
                page.wait_for_url(
                    lambda url: "login/google" not in url and "oidcJwt" not in url,
                    timeout=30000,
                )
            except Exception:
                # Kalau tidak auto-redirect, coba navigate manual ke dashboard
                log.info("[apikey] JWT tidak auto-redirect, navigate manual ke dashboard...")
                page.goto("https://dash.cloudflare.com", wait_until="domcontentloaded")

        match = re.search(r"dash\.cloudflare\.com/([a-f0-9]{32})", page.url)
        if match:
            log.info(f"[apikey] Account ID dari URL saat ini: {match.group(1)}")
            return match.group(1)

        page.goto("https://dash.cloudflare.com", wait_until="domcontentloaded")

        # Tunggu URL berubah ke format /<account_id>/
        try:
            page.wait_for_url(
                lambda url: re.search(r"/[a-f0-9]{32}/", url) is not None,
                timeout=15000,
            )
        except Exception:
            pass

        match = re.search(r"dash\.cloudflare\.com/([a-f0-9]{32})", page.url)
        if match:
            log.info(f"[apikey] Account ID: {match.group(1)}")
            return match.group(1)

        log.warning("[apikey] Account ID tidak ditemukan.")
        return None

    except Exception as e:
        log.error(f"[apikey] Error Account ID: {e}")
        return None


# ── Fix Zone Resources ────────────────────────────────────────────────────────

def _fix_zone_resources(page):
    """Ubah Zone Resources dari 'Specific zone' ke 'All zones'."""
    try:
        controls = page.locator('.react-select__control')
        specific_ctrl = None
        for i in range(controls.count()):
            try:
                if "specific zone" in controls.nth(i).inner_text(timeout=800).strip().lower():
                    specific_ctrl = controls.nth(i)
                    break
            except Exception:
                pass

        if specific_ctrl is None:
            return

        log.info("[apikey] Klik dropdown 'Specific zone'...")
        specific_ctrl.click()
        _d(0.5, 0.8)

        # Cari menu yang terbuka dan klik "All zones"
        menu = page.locator('[class*="-menu"]:visible').last
        if menu.count() > 0:
            for item in menu.locator('div').all():
                try:
                    if item.inner_text(timeout=400).strip() == "All zones":
                        item.click()
                        _d(0.3, 0.5)
                        log.info("[apikey] Zone Resources → 'All zones'.")
                        return
                except Exception:
                    pass

            # Fallback
            all_opt = menu.locator(':has-text("All zones")').first
            if all_opt.count() > 0:
                all_opt.click()
                _d(0.3, 0.5)
                log.info("[apikey] Zone Resources → 'All zones' (fallback).")

    except Exception as e:
        log.warning(f"[apikey] _fix_zone_resources: {e}")


# ── Buat Workers AI API Token ─────────────────────────────────────────────────

def create_workers_ai_token(page, token_name: str = "workers-ai-auto") -> str | None:
    try:
        # 1. Buka halaman token list
        log.info("[apikey] Membuka halaman API tokens...")
        page.goto(USER_TOKENS_URL, wait_until="domcontentloaded")
        _wait_visible(page, 'button:has-text("Create Token")')

        # 2. Klik Create Token
        log.info("[apikey] Klik Create Token...")
        page.locator('button:has-text("Create Token")').first.click()

        # 3. Tunggu template list load
        log.info("[apikey] Menunggu template list...")
        _wait_visible(page, ':has-text("Use template"), :has-text("Workers AI")', timeout=15000)
        _d(0.5, 1.0)

        page.screenshot(path="results/debug_create_token.png", full_page=True)

        # 4. Scroll ke bawah dan klik template Workers AI
        log.info("[apikey] Mencari template Workers AI...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        _d(0.3, 0.5)

        wai_btn = page.locator(':has-text("Workers AI") >> button:has-text("Use template")').first
        if wai_btn.count() > 0 and wai_btn.is_visible():
            log.info("[apikey] Template Workers AI ditemukan.")
            wai_btn.scroll_into_view_if_needed()
            wai_btn.click()
        else:
            # Iterasi semua "Use template" button
            use_btns = page.locator('button:has-text("Use template")').all()
            log.info(f"[apikey] Iterasi {len(use_btns)} Use template button...")
            clicked = False
            for btn in use_btns:
                try:
                    card = btn.locator("xpath=ancestor::*[contains(@class,'card') or contains(@class,'row') or contains(@class,'item')][1]")
                    if "workers ai" in card.inner_text(timeout=1000).lower():
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        clicked = True
                        log.info("[apikey] Template Workers AI diklik via iterasi.")
                        break
                except Exception:
                    pass
            if not clicked:
                log.warning("[apikey] Template tidak ditemukan, fallback custom token...")
                _create_custom_token(page)

        # Tunggu form token muncul
        _wait_visible(page, '.react-select__control, input[id*="name"]', timeout=10000)
        _d(0.5, 1.0)

        # 5. Fix Zone Resources
        _fix_zone_resources(page)

        # 6. Isi nama token
        log.info("[apikey] Mengisi nama token...")
        name_field = page.locator(
            'input[name="name"], input[placeholder*="name"], '
            'input[placeholder*="Token Name"], input[id*="cf-form-input"]'
        ).first
        if name_field.count() > 0 and name_field.is_visible():
            name_field.click()
            name_field.press("Control+a")
            _d(0.2, 0.3)
            name_field.fill(token_name)
            _d(0.3, 0.5)

        # 7. Continue to summary — tunggu button visible dulu
        log.info("[apikey] Klik Continue to summary...")
        cont_btn = page.locator('button:has-text("Continue to summary")').first
        cont_btn.wait_for(state="visible", timeout=15000)
        cont_btn.click()

        # 8. Tunggu halaman summary — "Create Token" button muncul
        log.info("[apikey] Menunggu halaman summary...")
        _wait_visible(page, 'button:has-text("Create Token")', timeout=15000)
        _d(0.3, 0.5)

        # 9. Create Token final
        log.info("[apikey] Klik Create Token (konfirmasi)...")
        page.locator('button:has-text("Create Token")').first.click()

        # 10. Tunggu token muncul di halaman
        log.info("[apikey] Menunggu token result...")
        _wait_visible(page, 'code, pre', timeout=15000)
        _d(0.5, 1.0)

        page.screenshot(path="results/debug_token_result.png", full_page=True)
        return _extract_token(page)

    except Exception as e:
        log.error(f"[apikey] Error membuat token: {e}")
        try:
            page.screenshot(path="results/debug_token_error.png", full_page=True)
        except Exception:
            pass
        return None


def _create_custom_token(page):
    """Fallback custom token — dump state untuk debug."""
    try:
        custom_btn = page.locator(
            'button:has-text("Create Custom Token"), a:has-text("Create Custom Token")'
        ).first
        if custom_btn.count() > 0 and custom_btn.is_visible():
            custom_btn.click()
            _d(1.0, 1.5)
        page.screenshot(path="results/debug_custom_token.png", full_page=True)
    except Exception as e:
        log.error(f"[apikey] _create_custom_token: {e}")


def _extract_token(page) -> str | None:
    """Extract token Cloudflare format cfut_xxx dari halaman sukses."""
    try:
        body = page.inner_text("body")
        matches = re.findall(r'cfut_[A-Za-z0-9_\-]+', body)
        if matches:
            log.info(f"[apikey] Token diambil (panjang: {len(matches[0])})")
            return matches[0]
    except Exception:
        pass

    for sel in ["code", "pre"]:
        for el in page.locator(sel).all():
            try:
                m = re.search(r'cfut_[A-Za-z0-9_\-]+', el.inner_text(timeout=2000))
                if m:
                    log.info(f"[apikey] Token dari <{sel}>")
                    return m.group(0)
            except Exception:
                pass

    for el in page.locator("input[readonly]").all():
        try:
            val = (el.get_attribute("value") or "").strip()
            if val.startswith("cfut_") or re.match(r'^[A-Za-z0-9_\-]{40,}$', val):
                return val
        except Exception:
            pass

    log.warning("[apikey] Token tidak dapat diekstrak. Cek debug_token_result.png")
    return None
