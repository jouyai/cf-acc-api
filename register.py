# register.py — otomatis login ke Cloudflare via Google OAuth
#
# Flow cepat:
#   1. Hit Cloudflare SSO init endpoint langsung (skip load halaman Cloudflare)
#   2. Buka Google OAuth URL langsung di browser
#   3. Isi email + password → submit
#   4. Handle intermediate pages → tunggu cookies Cloudflare ter-set

import time
import random
import logging
import requests

log = logging.getLogger(__name__)

DASHBOARD_URL = "https://dash.cloudflare.com"
GOOGLE_AUTH   = "accounts.google.com"

# Cloudflare SSO init endpoint — langsung dapat Google OAuth URL
CF_SSO_INIT = "https://oidc.iam.cfapi.net/api/v1/sso/init?client=google&env=production&prompt=select_account"


def _d(min_s: float = 0.1, max_s: float = 0.3):
    time.sleep(random.uniform(min_s, max_s))


def _type_fast(locator, text: str):
    """Ketik teks dengan delay minimal tapi masih terlihat human."""
    locator.click()
    _d(0.1, 0.2)
    locator.press_sequentially(text, delay=random.randint(20, 45))


def _wait_visible(page, selector: str, timeout: int = 15000) -> bool:
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        return True
    except Exception:
        return False


def _is_cloudflare_url(url: str) -> bool:
    return "dash.cloudflare.com" in url


def _get_google_oauth_url() -> str | None:
    """
    Hit Cloudflare SSO init endpoint untuk dapat Google OAuth URL.
    Ini skip load halaman Cloudflare sama sekali.
    """
    try:
        resp = requests.get(
            CF_SSO_INIT,
            allow_redirects=False,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        # Cloudflare redirect ke Google OAuth URL
        if resp.status_code in (301, 302, 303, 307, 308):
            url = resp.headers.get("Location", "")
            if GOOGLE_AUTH in url or "accounts.google" in url:
                log.info(f"[register] OAuth URL didapat via SSO init")
                return url
    except Exception as e:
        log.warning(f"[register] SSO init gagal: {e}")
    return None


def _fill_google_email(page, email: str) -> bool:
    log.info("[register] Mengisi email Google...")
    try:
        field = page.locator('#identifierId').first
        field.wait_for(state="visible", timeout=15000)
        _type_fast(field, email)
        _d(0.2, 0.4)

        next_btn = page.locator('#identifierNext').first
        next_btn.wait_for(state="visible", timeout=10000)
        next_btn.click()

        _wait_visible(page, 'input[type="password"]', timeout=15000)
        return True
    except Exception as e:
        log.error(f"[register] Gagal isi email: {e}")
        return False


def _fill_google_password(page, password: str) -> bool:
    log.info("[register] Mengisi password Google...")
    try:
        field = page.locator('input[type="password"]:visible').first
        field.wait_for(state="visible", timeout=15000)
        _d(0.1, 0.2)
        _type_fast(field, password)
        _d(0.2, 0.3)

        next_btn = page.locator('#passwordNext').first
        next_btn.wait_for(state="visible", timeout=10000)
        next_btn.click()
        return True
    except Exception as e:
        log.error(f"[register] Gagal isi password: {e}")
        return False


def _check_google_error(page) -> str | None:
    ERROR_KEYWORDS = [
        "wrong password", "incorrect password", "couldn't find",
        "couldn't sign", "account doesn't exist", "too many attempts",
        "unusual activity", "not recognized",
        "password yang salah", "tidak dapat menemukan",
    ]
    for sel in ['[jsname="B34EJ"]', 'div[aria-live="assertive"]']:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                txt = el.inner_text(timeout=1500).strip().lower()
                if txt and any(k in txt for k in ERROR_KEYWORDS):
                    return txt
        except Exception:
            pass
    return None


def _handle_google_intermediate_pages(page, timeout: int = 8000):
    """
    Handle halaman intermediate Google OAuth:
    consent, allow, account picker, Workspace ToS speedbump.
    """
    for _ in range(8):
        try:
            url = page.url
        except Exception:
            return

        if _is_cloudflare_url(url):
            return

        # Workspace Terms of Service
        if "speedbump" in url or "workspacetermsofservice" in url or "termsofservice" in url:
            log.info("[register] Handle Workspace ToS...")
            for sel in [
                '[jsname="j6LnAe"]',
                'button:has-text("Accept")',
                'button:has-text("I accept")',
                'button:has-text("Agree")',
                'button:has-text("Continue")',
                'input[type="submit"]',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        log.info(f"[register] ToS diklik: {sel}")
                        _d(1.0, 1.5)
                        break
                except Exception:
                    pass

        # OAuth consent
        elif "signin/oauth" in url or "consent" in url:
            for sel in [
                'button:has-text("Allow")',
                'button:has-text("Continue")',
                'button:has-text("Yes")',
                'button:has-text("Accept")',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        _d(0.5, 1.0)
                        break
                except Exception:
                    pass

        # Account picker
        elif "selectaccount" in url or "AccountChooser" in url:
            try:
                acct = page.locator('[data-email], [data-identifier]').first
                if acct.count() > 0:
                    acct.click()
                    _d(0.5, 1.0)
            except Exception:
                pass

        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        _d(0.3, 0.6)


def _wait_back_to_cloudflare(page, timeout: int = 60000) -> bool:
    try:
        if _is_cloudflare_url(page.url):
            log.info(f"[register] ✓ Sudah di Cloudflare: {page.url[:80]}")
            return True

        deadline = time.time() + (timeout / 1000)
        while time.time() < deadline:
            try:
                url = page.url
                if _is_cloudflare_url(url):
                    log.info(f"[register] ✓ Redirect ke Cloudflare: {url[:80]}")
                    return True
                if "signin/oauth" in url or "consent" in url or "speedbump" in url:
                    _handle_google_intermediate_pages(page, timeout=3000)
                time.sleep(0.4)
            except Exception:
                break

        log.error(f"[register] Timeout. URL terakhir: {page.url[:100]}")
        return False
    except Exception as e:
        log.error(f"[register] Exception wait_back: {e}")
        return False


def _do_google_login(page, email: str, password: str) -> bool:
    """Core Google login flow setelah browser ada di halaman Google."""
    if not _wait_visible(page, '#identifierId', timeout=15000):
        log.error("[register] Halaman Google tidak load")
        return False

    if not _fill_google_email(page, email):
        return False
    if not _fill_google_password(page, password):
        return False

    err = _check_google_error(page)
    if err:
        log.error(f"[register] Error Google: {err}")
        return False

    _handle_google_intermediate_pages(page)
    return _wait_back_to_cloudflare(page)


def register_account(page, context, email: str, password: str) -> bool:
    """
    Login ke Cloudflare via Google OAuth.
    
    Flow cepat: hit SSO init endpoint → dapat Google OAuth URL → buka langsung.
    Fallback: buka Cloudflare sign-up → klik tombol Google.
    """
    try:
        # ── Fast path: langsung buka Google OAuth URL ────────────────────────
        oauth_url = _get_google_oauth_url()
        if oauth_url:
            log.info(f"[register] Fast path: buka Google OAuth URL langsung")
            page.goto(oauth_url, wait_until="domcontentloaded")
            ok = _do_google_login(page, email, password)
            if ok:
                return True
            log.info("[register] Fast path gagal, coba fallback...")

        # ── Fallback: buka Cloudflare sign-up, klik tombol Google ────────────
        log.info(f"[register] Fallback: buka {DASHBOARD_URL}/sign-up")
        page.goto(f"{DASHBOARD_URL}/sign-up", wait_until="domcontentloaded")
        _d(1.0, 2.0)

        # Tunggu SPA load dan klik tombol Google
        _wait_visible(page, 'button:has-text("Google"), a:has-text("Google")', timeout=15000)
        _d(0.2, 0.4)

        for sel in [
            'button:has-text("Continue with Google")',
            'button:has-text("Sign in with Google")',
            'a:has-text("Continue with Google")',
        ]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    log.info("[register] Tombol Google diklik.")
                    break
            except Exception:
                continue

        # Tunggu navigasi ke Google
        try:
            page.wait_for_url(lambda url: GOOGLE_AUTH in url, timeout=15000)
        except Exception:
            log.error("[register] Tidak redirect ke Google")
            return False

        return _do_google_login(page, email, password)

    except Exception as e:
        log.error(f"[register] Exception: {e}")
        return False


# ── Tempmail registration flow ────────────────────────────────────────────────

SIGNUP_FORM_URL = "https://dash.cloudflare.com/sign-up"


def _dismiss_cookie_popup(page, timeout: int = 5000):
    """Dismiss cookie consent popup Cloudflare (OneTrust) kalau muncul."""
    try:
        # Tunggu popup muncul dulu
        page.wait_for_selector(
            '#onetrust-consent-sdk, #onetrust-banner-sdk, .onetrust-pc-dark-filter',
            state="visible",
            timeout=3000,
        )
    except Exception:
        return  # popup tidak muncul, skip

    # Klik Accept All
    for sel in [
        '#onetrust-accept-btn-handler',
        'button:has-text("Accept All Cookies")',
        'button:has-text("Accept All")',
        'button:has-text("Reject All")',
        '.onetrust-close-btn-handler',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                log.info("[register] Cookie popup dismissed.")
                _d(0.5, 1.0)
                # Tunggu overlay hilang
                try:
                    page.wait_for_selector(
                        '.onetrust-pc-dark-filter',
                        state="hidden",
                        timeout=3000,
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

    # Force remove via JS kalau tombol tidak bisa diklik
    try:
        page.evaluate("""
            () => {
                const sdk = document.getElementById('onetrust-consent-sdk');
                if (sdk) sdk.remove();
                document.querySelectorAll('.onetrust-pc-dark-filter, #onetrust-banner-sdk')
                    .forEach(el => el.remove());
            }
        """)
        log.info("[register] Cookie popup removed via JS.")
        _d(0.3, 0.5)
    except Exception:
        pass


def register_tempmail(page, email: str, password: str, proxy: str | None = None) -> bool:
    """
    Register akun Cloudflare baru via form email+password.
    Biarkan Turnstile solve otomatis (CloakBrowser stealth).
    Kalau CAPTCHA muncul, tunggu auto-solve atau retry.
    """
    try:
        log.info(f"[register] Form register untuk: {email}")

        page.goto(SIGNUP_FORM_URL, wait_until="domcontentloaded")
        _d(1.0, 1.5)

        # Dismiss cookie popup
        _dismiss_cookie_popup(page)

        # Tunggu form render
        email_field = page.locator('input[name="email"]').first
        email_field.wait_for(state="visible", timeout=20000)

        # Isi form
        _type_fast(email_field, email)
        _d(0.3, 0.5)

        pass_field = page.locator('input[type="password"]').first
        pass_field.wait_for(state="visible", timeout=10000)
        _type_fast(pass_field, password)
        _d(0.5, 1.0)

        # Tunggu Turnstile widget solve sendiri (CloakBrowser stealth)
        # Turnstile biasanya auto-solve dalam 2-5 detik pada browser normal
        log.info("[register] Menunggu Turnstile auto-solve...")

        # Dismiss cookie popup lagi kalau muncul setelah form render
        _dismiss_cookie_popup(page)

        _d(3.0, 5.0)

        # Submit form
        submit = page.locator('button[type="submit"]').first
        submit.wait_for(state="visible", timeout=10000)
        submit.click()

        # Tunggu redirect — max 30 detik
        deadline = time.time() + 30
        while time.time() < deadline:
            url = page.url
            if url != SIGNUP_FORM_URL and "sign-up" not in url:
                log.info(f"[register] ✓ Redirect ke: {url}")
                return True
            try:
                body = page.inner_text("body")
            except Exception:
                body = ""

            # Rate limit / IP block — tidak bisa di-retry dengan email sama
            if "unable" in body.lower() and "sign up" in body.lower():
                log.error("[register] IP/rate limit block dari Cloudflare")
                return False

            # CAPTCHA masih muncul — tunggu auto-solve atau submit ulang
            if "captcha" in body.lower() or "human" in body.lower():
                log.warning("[register] CAPTCHA muncul, tunggu auto-solve...")
                _d(3.0, 5.0)
                # Coba submit ulang
                try:
                    btn = page.locator('button[type="submit"]').first
                    if btn.is_visible():
                        btn.click()
                except Exception:
                    pass
                continue

            _d(1.0, 1.5)

        log.warning(f"[register] Timeout. URL terakhir: {page.url}")
        # Return True kalau URL sudah berubah dari sign-up
        return "sign-up" not in page.url

    except Exception as e:
        log.error(f"[register] register_tempmail exception: {e}")
        return False
