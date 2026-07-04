# Cloudflare Workers AI — Auto Register Tool

Tool otomatis untuk register akun Cloudflare dan ambil **Workers AI API key** secara bulk, menggunakan [CloakBrowser](https://github.com/CloakHQ/cloakbrowser) (stealth Chromium) + Rich terminal UI dengan parallel workers.

## Fitur

- **Mode Google** — login via Google OAuth pakai akun Gmail/GSuite dari file
- **Mode Tempmail** — generate akun Cloudflare baru otomatis via Mailsac
- Parallel workers dengan live terminal UI (progress, status per worker, log)
- Ambil Account ID + buat Workers AI token via Cloudflare API (cepat, tanpa navigate browser)
- Output `results/apikeys.txt` format `accountID:apikey` + `results/accounts.csv` lengkap
- Proxy support dengan rotasi otomatis + dead proxy detection
- Auto-retry sampai sukses (max 10x per akun)
- Proxy scraper built-in untuk proxy publik gratis

---

## Struktur Project

```
cf-acc-api/
│
├── main.py                        # Entry point — CLI + Rich UI + parallel workers
├── register.py                    # Login flow: Google OAuth + Tempmail form
├── cloudflare_api.py              # Cloudflare API: account ID + create token
├── browser.py                     # CloakBrowser wrapper (stealth Chromium)
├── get_apikey.py                  # Browser fallback untuk buat token
├── verify_email.py                # Verifikasi email (Mailsac / mail.tm)
├── captcha_solver.py              # Turnstile solver via CapSolver API
├── storage.py                     # Simpan hasil ke CSV + apikeys.txt
├── config.py                      # Konfigurasi global (load dari .env)
├── proxy_manager.py               # Rotasi proxy + dead proxy detection
├── proxy_scraper.py               # Scrape proxy publik gratis
│
├── email_providers/
│   ├── file_provider.py           # Baca email dari file
│   ├── tempmail_provider.py       # mail.tm API
│   └── mailsac_provider.py        # Mailsac API
│
├── emails.txt                     # Template file akun Google
├── proxies.txt                    # Template file proxy
├── .env.example                   # Template konfigurasi
├── requirements.txt
│
└── results/                       # Output (di-gitignore)
    ├── apikeys.txt                # Format: accountID:apikey
    ├── accounts.csv               # Data lengkap semua akun
    └── run.log                    # Log eksekusi
```

---

## Instalasi

```bash
# 1. Clone repo
git clone https://github.com/jouyai/cf-acc-api.git
cd cf-acc-api

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download CloakBrowser binary
python -m cloakbrowser install

# 4. Setup konfigurasi
cp .env.example .env
# Edit .env sesuai kebutuhan
```

---

## Konfigurasi

Copy `.env.example` ke `.env` lalu isi:

```env
# Browser
HEADLESS=true
HUMANIZE=true

# Parallel & Delay
CONCURRENCY=2
DELAY_MIN=3
DELAY_MAX=8

# Output
OUTPUT_FILE=results/accounts.csv

# Tempmail provider: "mailsac" atau "mailtm"
TEMPMAIL_PROVIDER=mailsac
MAILSAC_API_KEY=your_mailsac_api_key_here   # daftar gratis di mailsac.com

# CAPTCHA solver (untuk mode tempmail)
CAPSOLVER_API_KEY=your_capsolver_api_key_here   # daftar di capsolver.com

# Proxy tunggal (opsional)
# PROXY=http://user:pass@host:port
```

---

## Cara Pakai

### Mode Google OAuth (pakai akun Gmail/GSuite)

1. Isi `emails.txt` dengan format `email:password`:
```
akun1@gmail.com:Password123!
akun2@yourdomain.com:AnotherPass456!
```

2. Jalankan:
```bash
# Basic
python main.py --mode google --file emails.txt

# Dengan 3 workers paralel
python main.py --mode google --file emails.txt --workers 3

# Debug (tampilkan browser)
python main.py --mode google --file emails.txt --no-headless
```

### Mode Tempmail (generate akun baru otomatis)

> **Catatan:** Mode tempmail membutuhkan **residential proxy** untuk bypass Cloudflare sign-up. Datacenter proxy (termasuk Webshare free) biasanya di-block Cloudflare.

```bash
# Generate 10 akun baru
python main.py --mode tempmail --count 10 --proxy-file proxies.txt

# Dengan 3 workers
python main.py --mode tempmail --count 50 --workers 3 --proxy-file proxies.txt

# Debug
python main.py --mode tempmail --count 1 --no-headless
```

### Scrape proxy publik gratis

```bash
# Scrape 100 proxy hidup
python proxy_scraper.py --count 100

# Dengan lebih banyak thread (lebih cepat)
python proxy_scraper.py --count 100 --threads 100
```

### Semua opsi CLI

```
--mode          google | tempmail
--file PATH     File email:password (mode google, default: emails.txt)
--count N       Jumlah akun baru (mode tempmail, default: 1)
--workers N     Jumlah browser parallel (default: 2)
--proxy URL     Single proxy: http://user:pass@host:port
--proxy-file    File list proxy, dirotasi per akun
--no-headless   Tampilkan browser (untuk debug)
--output PATH   Output CSV (default: results/accounts.csv)
```

---

## Format File

### `emails.txt` — akun Google
```
# Format: email:password
akun1@gmail.com:Password123!
akun2@yourdomain.com:AnotherPass!
```

### `proxies.txt` — list proxy
```
# Format yang didukung:
http://user:pass@host:port
socks5://user:pass@host:port
host:port:user:pass          # format Webshare
host:port                    # tanpa auth
```

---

## Output

**`results/apikeys.txt`** — format siap pakai:
```
8e573757eb652aee8dc0f602a848abdd:cfut_xxxxxxxxxxxxxxxxxxxx
f1b737c82cbd3e2554a419206ce895b5:cfut_yyyyyyyyyyyyyyyyyyyy
```

**`results/accounts.csv`** — data lengkap:
```csv
email,password,account_id,api_token,status,reason,created_at
akun1@gmail.com,Pass123!,8e573757...,cfut_xxx...,success,,2026-07-04T08:00:00
```

---

## Tips

- **Mode Google** adalah yang paling reliable — tidak kena CAPTCHA, tidak butuh proxy
- Untuk mode tempmail: gunakan **residential proxy** (Webshare Residential, BrightData, IPRoyal)
- Mulai dengan `--no-headless` untuk pastikan flow benar sebelum headless
- Retry akun yang gagal:

```bash
# Export akun gagal ke file baru
python -c "
import csv
with open('results/accounts.csv') as f:
    for row in csv.DictReader(f):
        if row['status'] == 'failed':
            print(f\"{row['email']}:{row['password']}\")
" > failed.txt

python main.py --mode google --file failed.txt
```

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `cloakbrowser tidak ditemukan` | `pip install cloakbrowser` |
| `MAILSAC_API_KEY belum di-set` | Set di `.env`, daftar gratis di mailsac.com |
| Login Google gagal | Coba `--no-headless`, cek apakah ada 2FA/ToS |
| `You are unable to sign up` | IP/proxy di-block Cloudflare — pakai residential proxy |
| `Please complete the CAPTCHA` | Pakai residential proxy + set `CAPSOLVER_API_KEY` |
| Rate limit Cloudflare | Tunggu 15-30 menit, kurangi `--workers` |
| Verifikasi email timeout | Naikkan `EMAIL_POLL_TIMEOUT=180` di `.env` |
