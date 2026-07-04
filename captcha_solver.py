# captcha_solver.py — solve Cloudflare challenges via CapSolver API
#
# Dokumentasi: https://docs.capsolver.com
# Daftar di https://capsolver.com untuk dapat API key

import time
import logging
import requests

log = logging.getLogger(__name__)

CAPSOLVER_API = "https://api.capsolver.com"

CF_SIGNUP_URL    = "https://dash.cloudflare.com/sign-up"
CF_TURNSTILE_KEY = "0x4AAAAAAAJel0iaAR3mgkjp"  # sitekey Cloudflare sign-up (verified)


def _create_and_poll(api_key: str, task: dict, max_wait: int = 120) -> dict | None:
    """Helper: buat task dan poll sampai selesai."""
    try:
        resp = requests.post(
            f"{CAPSOLVER_API}/createTask",
            json={"clientKey": api_key, "task": task},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("errorId") != 0:
            log.error(f"[capsolver] Create task error: {data.get('errorDescription')}")
            return None

        task_id = data.get("taskId")
        log.info(f"[capsolver] Task ID: {task_id}")

        for _ in range(max_wait // 3):
            time.sleep(3)
            result_resp = requests.post(
                f"{CAPSOLVER_API}/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=30,
            )
            result_resp.raise_for_status()
            result = result_resp.json()

            status = result.get("status")
            if status == "ready":
                log.info("[capsolver] ✓ Task solved!")
                return result.get("solution", {})
            elif status == "failed":
                log.error(f"[capsolver] Task failed: {result.get('errorDescription')}")
                return None

        log.error("[capsolver] Timeout menunggu solve result")
        return None

    except Exception as e:
        log.error(f"[capsolver] Exception: {e}")
        return None


def solve_turnstile(api_key: str, url: str = CF_SIGNUP_URL, site_key: str = CF_TURNSTILE_KEY, proxy: str | None = None) -> str | None:
    """Solve Cloudflare Turnstile. Coba dengan proxy dulu, fallback ke proxyless."""
    log.info(f"[capsolver] Solving Turnstile {'via proxy' if proxy else 'proxyless'}...")

    # Coba TurnstileTask dengan proxy dulu
    if proxy:
        proxy_data = _parse_proxy(proxy)
        if proxy_data:
            task = {
                "type":       "TurnstileTask",
                "websiteURL": url,
                "websiteKey": site_key,
                **proxy_data,
            }
            log.info(f"[capsolver] TurnstileTask proxy: {proxy_data.get('proxyAddress')}:{proxy_data.get('proxyPort')}")
            solution = _create_and_poll(api_key, task)
            if solution and solution.get("token"):
                log.info(f"[capsolver] ✓ Token via proxy: {solution['token'][:20]}...")
                return solution["token"]
            log.warning("[capsolver] TurnstileTask gagal, fallback ke proxyless...")

    # Fallback: AntiTurnstileTaskProxyLess
    solution = _create_and_poll(api_key, {
        "type":       "AntiTurnstileTaskProxyLess",
        "websiteURL": url,
        "websiteKey": site_key,
    })
    if solution:
        token = solution.get("token")
        if token:
            log.info(f"[capsolver] ✓ Token proxyless: {token[:20]}...")
        return token
    return None


def _parse_proxy(proxy: str) -> dict | None:
    """Parse proxy URL ke format CapSolver TurnstileTask."""
    try:
        original = proxy
        # Detect type
        if proxy.startswith("socks5://"):
            proxy_type = "socks5"
            proxy = proxy[9:]
        elif proxy.startswith("socks4://"):
            proxy_type = "socks4"
            proxy = proxy[9:]
        else:
            proxy_type = "http"
            for prefix in ("http://", "https://"):
                if proxy.startswith(prefix):
                    proxy = proxy[len(prefix):]

        # Parse auth dan host
        if "@" in proxy:
            auth, hostport = proxy.rsplit("@", 1)
            login, password = auth.split(":", 1) if ":" in auth else (auth, "")
        else:
            hostport = proxy
            login, password = "", ""

        if ":" not in hostport:
            log.warning(f"[capsolver] Proxy format invalid: {original}")
            return None

        host, port = hostport.rsplit(":", 1)

        result = {
            "proxyType":    proxy_type,
            "proxyAddress": host.strip(),
            "proxyPort":    int(port.strip()),
        }
        if login:
            result["proxyLogin"]    = login.strip()
            result["proxyPassword"] = password.strip()
        return result
    except Exception as e:
        log.warning(f"[capsolver] Parse proxy error: {e} — proxy={proxy}")
        return None


def solve_cf_challenge(api_key: str, url: str = CF_SIGNUP_URL) -> dict | None:
    """
    Solve Cloudflare Bot Management / Challenge Platform.
    Ini untuk halaman yang pakai challenge-platform bukan Turnstile widget biasa.
    Returns dict dengan cookies atau None.
    """
    log.info(f"[capsolver] Solving CF Challenge untuk {url}...")
    solution = _create_and_poll(api_key, {
        "type":       "AntiCloudflareTask",
        "websiteURL": url,
        "proxy":      "",  # kosong = proxyless
    })
    if solution:
        log.info(f"[capsolver] ✓ CF Challenge solved!")
        return solution
    return None


def inject_cf_cookies(page, cookies: dict):
    """Inject cookies hasil CF challenge solve ke browser."""
    try:
        cf_cookies = cookies.get("cookies", [])
        if isinstance(cf_cookies, list):
            for c in cf_cookies:
                page.context.add_cookies([{
                    "name":   c.get("name", ""),
                    "value":  c.get("value", ""),
                    "domain": ".cloudflare.com",
                    "path":   "/",
                }])
        log.info(f"[capsolver] Injected {len(cf_cookies)} cookies")
    except Exception as e:
        log.warning(f"[capsolver] inject_cf_cookies: {e}")


def get_balance(api_key: str) -> float | None:
    """Cek saldo CapSolver."""
    try:
        resp = requests.post(
            f"{CAPSOLVER_API}/getBalance",
            json={"clientKey": api_key},
            timeout=10,
        )
        data = resp.json()
        if data.get("errorId") == 0:
            balance = data.get("balance", 0)
            log.info(f"[capsolver] Balance: ${balance}")
            return float(balance)
        return None
    except Exception:
        return None
