# proxy_manager.py — manage dan rotasi proxy untuk setiap akun
#
# Format file proxy (satu per baris):
#   http://user:pass@host:port
#   socks5://user:pass@host:port
#   host:port:user:pass
#   host:port  (tanpa auth)

import random
import threading
import logging
import requests

log = logging.getLogger(__name__)

_lock       = threading.Lock()
_proxies    = []
_dead       = set()  # proxy yang sudah terbukti mati
_index      = 0


def load_proxies(filepath: str) -> int:
    """Load proxy dari file. Return jumlah proxy yang berhasil di-load."""
    global _proxies, _dead
    loaded = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                proxy = _normalize(line)
                if proxy:
                    loaded.append(proxy)
        with _lock:
            _proxies = loaded
            _dead    = set()
        log.info(f"[proxy] Loaded {len(loaded)} proxies dari {filepath}")
        return len(loaded)
    except FileNotFoundError:
        log.error(f"[proxy] File proxy tidak ditemukan: {filepath}")
        return 0


def _normalize(raw: str) -> str | None:
    """Normalisasi format proxy ke http://user:pass@host:port"""
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://", "socks5://", "socks4://")):
        return raw
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f"http://{user}:{passwd}@{host}:{port}"
    if len(parts) == 2:
        return f"http://{raw}"
    return None


def mark_dead(proxy: str):
    """Tandai proxy sebagai mati agar tidak dipakai lagi."""
    with _lock:
        _dead.add(proxy)
    log.debug(f"[proxy] Marked dead: {proxy}")


def get_next() -> str | None:
    """Ambil proxy berikutnya (round-robin), skip yang sudah mati."""
    global _index
    with _lock:
        live = [p for p in _proxies if p not in _dead]
        if not live:
            # Semua mati — reset dan coba lagi
            log.warning("[proxy] Semua proxy mati, reset dead list...")
            _dead.clear()
            live = list(_proxies)
        if not live:
            return None
        proxy = live[_index % len(live)]
        _index += 1
        return proxy


def get_random() -> str | None:
    """Ambil proxy random dari yang masih hidup."""
    with _lock:
        live = [p for p in _proxies if p not in _dead]
        if not live:
            _dead.clear()
            live = list(_proxies)
        return random.choice(live) if live else None


def count() -> int:
    with _lock:
        return len(_proxies)


def live_count() -> int:
    with _lock:
        return len([p for p in _proxies if p not in _dead])


def has_proxies() -> bool:
    return count() > 0
