# email_providers/file_provider.py — baca email dari file teks
#
# Format file yang didukung (satu per baris):
#   email:password
#   email          <- password akan di-generate otomatis

import os
import random
import string


def _generate_password(length: int = 14) -> str:
    """Generate password acak yang memenuhi syarat Cloudflare (huruf, angka, simbol)."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    # pastikan minimal ada 1 huruf besar, 1 kecil, 1 angka, 1 simbol
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("!@#$%^&*"),
    ]
    pwd += random.choices(chars, k=length - 4)
    random.shuffle(pwd)
    return "".join(pwd)


def load_emails(filepath: str) -> list[dict]:
    """
    Baca file email dan return list dict:
      [{"email": "...", "password": "..."}, ...]

    Baris kosong dan baris yang diawali # diabaikan.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File email tidak ditemukan: {filepath}")

    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                parts = line.split(":", 1)
                email = parts[0].strip()
                password = parts[1].strip()
            else:
                email = line
                password = _generate_password()
            accounts.append({"email": email, "password": password})

    return accounts
