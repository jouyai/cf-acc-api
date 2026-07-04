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

log = logging.getLogger(__name__)

_lock       = threading.Lock()
_proxies    = []
_index      = 0


def load_proxies(filepath: str) -> int:
    """Load proxy dari file. Return jumlah proxy yang berhasil di-load."""
    global _proxies
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
        log.info(f"[proxy] Loaded {len(loaded)} proxies dari {filepath}")
        return len(loaded)
    except FileNotFoundError:
        log.error(f"[proxy] File proxy tidak ditemukan: {filepath}")
        return 0


def _normalize(raw: str) -> str | None:
    """
    Normalisasi format proxy ke http://user:pass@host:port
    Support format:
      - http://user:pass@host:port
      - socks5://host:port
      - host:port:user:pass
      - host:port
    """
    raw = raw.strip()
    if not raw:
        return None

    # Sudah dalam format URL
    if raw.startswith(("http://", "https://", "socks5://", "socks4://")):
        return raw

    # Format host:port:user:pass
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f"http://{user}:{passwd}@{host}:{port}"

    # Format host:port
    if len(parts) == 2:
        return f"http://{raw}"

    return None


def get_next() -> str | None:
    """Ambil proxy berikutnya (round-robin)."""
    global _index
    with _lock:
        if not _proxies:
            return None
        proxy = _proxies[_index % len(_proxies)]
        _index += 1
        return proxy


def get_random() -> str | None:
    """Ambil proxy random."""
    with _lock:
        if not _proxies:
            return None
        return random.choice(_proxies)


def count() -> int:
    """Jumlah proxy yang tersedia."""
    with _lock:
        return len(_proxies)


def has_proxies() -> bool:
    return count() > 0
