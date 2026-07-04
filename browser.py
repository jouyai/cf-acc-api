# browser.py — wrapper launch dan close CloakBrowser
#
# Setiap panggilan new_browser() membuat Playwright instance baru.
# Ini paling reliable untuk multi-thread — tidak ada shared state antar akun.

import logging
import threading
import config

from playwright.sync_api import sync_playwright
from cloakbrowser import build_args, ensure_binary, binary_info

log = logging.getLogger(__name__)

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
    args = build_args(
        stealth_args=True,
        extra_args=None,
        headless=config.HEADLESS,
        locale="en-US",
        timezone="America/New_York",
    )
    extra = [
        "--ignore-certificate-errors",
        "--ignore-ssl-errors",
        "--ignore-certificate-errors-spki-list",
        "--allow-insecure-localhost",
    ]
    return args + extra


def _parse_proxy_for_playwright(proxy_url: str) -> dict | None:
    """
    Parse proxy URL ke format Playwright proxy dict.
    Playwright butuh: {server, username, password} — bukan embed di URL.

    Support format:
      - http://user:pass@host:port
      - host:port:user:pass  (format Webshare)
      - host:port
    """
    try:
        url = proxy_url.strip()

        # Format Webshare: host:port:user:pass
        parts = url.split(":")
        if len(parts) == 4 and not url.startswith(("http", "socks")):
            host, port, username, password = parts
            return {
                "server":   f"http://{host}:{port}",
                "username": username,
                "password": password,
            }

        # Detect scheme
        if url.startswith("socks5://"):
            scheme, url = "socks5", url[9:]
        elif url.startswith("socks4://"):
            scheme, url = "socks4", url[9:]
        else:
            scheme = "http"
            for p in ("http://", "https://"):
                if url.startswith(p):
                    url = url[len(p):]

        # Parse auth@host:port
        username, password = "", ""
        if "@" in url:
            auth, hostport = url.rsplit("@", 1)
            if ":" in auth:
                username, password = auth.split(":", 1)
            else:
                username = auth
        else:
            hostport = url

        result = {"server": f"{scheme}://{hostport}"}
        if username:
            result["username"] = username
            result["password"] = password
        return result

    except Exception as e:
        log.warning(f"[browser] Parse proxy error: {e} — input={proxy_url}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def new_browser(proxy: str | None = None):
    """
    Buat Playwright + browser instance baru.

    Args:
        proxy: proxy URL (http://user:pass@host:port atau host:port:user:pass)
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

    # Parse proxy ke format Playwright
    active_proxy = proxy or config.PROXY
    proxy_opts   = None
    if active_proxy:
        proxy_opts = _parse_proxy_for_playwright(active_proxy)
        if proxy_opts:
            log.debug(f"[browser] Proxy: {proxy_opts['server']}")
        else:
            log.warning(f"[browser] Proxy tidak valid, skip: {active_proxy}")

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
        ignore_https_errors=True,
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
