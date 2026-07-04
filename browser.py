# browser.py — wrapper launch dan close CloakBrowser
#
# Setiap panggilan new_browser() membuat Playwright instance baru.
# Ini paling reliable untuk multi-thread — tidak ada shared state antar akun.

import threading
import config

from playwright.sync_api import sync_playwright
from cloakbrowser import build_args, ensure_binary, binary_info

# ── Binary path (resolve sekali saja) ────────────────────────────────────────
_binary_path: str | None = None
_binary_lock = threading.Lock()


def _get_binary() -> str:
    global _binary_path
    if _binary_path:
        return _binary_path
    with _binary_lock:
        if _binary_path:
            return _binary_path
        ensure_binary()
        _binary_path = binary_info()["binary_path"]
    return _binary_path


def _build_chromium_args() -> list[str]:
    return build_args(
        stealth_args=True,
        extra_args=None,
        headless=config.HEADLESS,
        locale="en-US",
        timezone="America/New_York",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def new_browser(proxy: str | None = None):
    """
    Buat Playwright + browser instance baru.
    
    Args:
        proxy: proxy URL override per-akun (e.g. "http://user:pass@host:port")
               Kalau None, pakai config.PROXY global.
    
    Returns (pw, browser, context, page).
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    binary = _get_binary()
    args   = _build_chromium_args()

    # Prioritas: proxy argumen > config.PROXY global
    active_proxy = proxy or config.PROXY
    proxy_opts   = {"server": active_proxy} if active_proxy else None

    pw      = sync_playwright().start()
    browser = pw.chromium.launch(
        executable_path=binary,
        headless=config.HEADLESS,
        args=args,
        proxy=proxy_opts,
    )
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
    )
    context.set_default_timeout(config.PAGE_TIMEOUT * 1000)
    page = context.new_page()
    return pw, browser, context, page


def close_browser(pw, browser):
    """Tutup browser dan stop Playwright instance."""
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


def stop_playwright():
    """No-op — Playwright di-stop di close_browser sekarang."""
    pass
