# config.py — konfigurasi global untuk tool
# Bisa di-override lewat .env atau argumen CLI

import os
from dotenv import load_dotenv

load_dotenv()

# --- Email Mode ---
# "file"     : baca email dari EMAIL_FILE (format: email:password atau email saja)
# "tempmail" : generate otomatis pakai mail.tm API
EMAIL_MODE = os.getenv("EMAIL_MODE", "file")
EMAIL_FILE = os.getenv("EMAIL_FILE", "emails.txt")

# --- Browser ---
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
HUMANIZE = os.getenv("HUMANIZE", "true").lower() == "true"

# Proxy opsional: "http://user:pass@host:port" atau None
PROXY = os.getenv("PROXY", None)

# Jumlah browser yang jalan paralel (mulai dari 2, naikkan pelan-pelan)
CONCURRENCY = int(os.getenv("CONCURRENCY", "2"))

# Delay antar akun (detik), diambil random dari range ini
DELAY_BETWEEN_ACCOUNTS = (
    int(os.getenv("DELAY_MIN", "3")),
    int(os.getenv("DELAY_MAX", "8")),
)

# --- Output ---
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "results/accounts.csv")

# --- Timeout (detik) ---
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "60"))          # timeout navigasi halaman
EMAIL_POLL_TIMEOUT = int(os.getenv("EMAIL_POLL_TIMEOUT", "120"))  # max tunggu email verifikasi
EMAIL_POLL_INTERVAL = int(os.getenv("EMAIL_POLL_INTERVAL", "5"))  # interval cek inbox

# --- License CloakBrowser (opsional, untuk binary Pro) ---
CLOAKBROWSER_LICENSE_KEY = os.getenv("CLOAKBROWSER_LICENSE_KEY", None)

# --- CAPTCHA Solver ---
# CapSolver API key untuk solve Cloudflare Turnstile di sign-up form
# Daftar di https://capsolver.com
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")

# --- Email Provider untuk mode tempmail ---
# "mailsac" : pakai Mailsac API (butuh MAILSAC_API_KEY)
# "mailtm"  : pakai mail.tm (gratis, tidak butuh API key)
TEMPMAIL_PROVIDER = os.getenv("TEMPMAIL_PROVIDER", "mailsac")

# Mailsac API key (wajib untuk provider mailsac)
# Daftar di https://mailsac.com dan ambil API key
MAILSAC_API_KEY = os.getenv("MAILSAC_API_KEY", "")
