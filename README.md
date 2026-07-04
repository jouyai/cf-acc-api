# Cloudflare Workers AI — Auto Register Tool

Tool otomatis untuk login ke Cloudflare via **Google OAuth** dan ambil Workers AI API key secara bulk, menggunakan [CloakBrowser](https://github.com/CloakHQ/cloakbrowser) (stealth Chromium) + Rich terminal UI.

## Fitur

- Login Cloudflare via Google OAuth otomatis
- Ambil Account ID + buat Workers AI API token via Cloudflare API (cepat, tanpa navigate browser)
- Bulk processing dengan parallel workers
- Terminal UI live dengan status per worker, progress bar, dan log
- Output `apikeys.txt` format `accountID:apikey` + `accounts.csv` lengkap
- Auto-handle Google Workspace ToS, consent page, dan intermediate redirects
- Fallback browser jika API gagal

## Instalasi

```bash
# Clone repo
git clone <repo-url>
cd cloudflare-worker-ai-tool

# Install dependencies
pip install -r requirements.txt

# Download CloakBrowser binary
python -m cloakbrowser install
```

## Format File Email

Buat file `emails.txt` dengan format satu akun per baris:

```
akun1@gmail.com:Password123!
akun2@yourdomain.com:AnotherPass456!
akun3@gmail.com:Pass789!
```

> Akun harus berupa Gmail atau Google Workspace (GSuite).

## Cara Pakai

### Basic

```bash
python main.py --file emails.txt
```

### Dengan jumlah worker (parallel)

```bash
# 3 browser jalan bersamaan
python main.py --file emails.txt --workers 3

# Tampilkan browser (untuk debug)
python main.py --file emails.txt --workers 2 --no-headless
```

### Dengan proxy

```bash
python main.py --file emails.txt --workers 3 --proxy http://user:pass@host:port
```

### Semua opsi CLI

```
--file PATH       File email:password (default: emails.txt)
--workers N       Jumlah browser parallel (default: 2)
--proxy URL       Proxy URL: http://user:pass@host:port
--no-headless     Tampilkan browser (untuk debug)
--output PATH     Path file output CSV (default: results/accounts.csv)
```

## Output

Hasil disimpan di folder `results/`:

**`results/apikeys.txt`** — format siap pakai:
```
8e573757eb652aee8dc0f602a848abdd:cfut_xxxxxxxxxxxxxxxxxxxx
f1b737c82cbd3e2554a419206ce895b5:cfut_yyyyyyyyyyyyyyyyyyyy
```

**`results/accounts.csv`** — data lengkap:
```csv
email,password,account_id,api_token,status,reason,created_at
akun1@gmail.com,Password123!,8e573757...,cfut_xxx...,success,,2026-07-04T08:00:00
```

## Konfigurasi

Buat file `.env` untuk override config tanpa edit kode:

```env
EMAIL_FILE=emails.txt
HEADLESS=true
HUMANIZE=true
CONCURRENCY=2
DELAY_MIN=3
DELAY_MAX=8
OUTPUT_FILE=results/accounts.csv
PAGE_TIMEOUT=60

# License CloakBrowser Pro (opsional)
# CLOAKBROWSER_LICENSE_KEY=cb_xxxxxxxx
```

## Struktur Project

```
cloudflare-worker-ai-tool/
├── main.py                  # Entry point CLI + Rich UI + parallel workers
├── register.py              # Google OAuth login flow
├── cloudflare_api.py        # Cloudflare API (account ID + create token)
├── browser.py               # CloakBrowser wrapper
├── get_apikey.py            # Browser fallback untuk buat token
├── storage.py               # Simpan hasil ke CSV + apikeys.txt
├── config.py                # Konfigurasi global
├── email_providers/
│   ├── file_provider.py     # Baca email dari file
│   └── tempmail_provider.py # Generate email via mail.tm
├── verify_email.py          # Handler verifikasi email (tempmail mode)
├── emails.txt               # Template file email
├── requirements.txt
└── results/                 # Output (di-gitignore)
    ├── apikeys.txt
    ├── accounts.csv
    └── run.log
```

## Tips

- **Mulai dengan `--no-headless`** untuk pastikan flow berjalan benar sebelum headless
- **2-3 workers** optimal untuk 1 IP tanpa kena rate limit Google
- **Gunakan proxy** untuk bulk besar — 1 proxy per worker lebih aman
- Akun yang gagal bisa di-retry dengan filter dari CSV:

```bash
# Export akun yang gagal ke file baru
python -c "
import csv
with open('results/accounts.csv') as f:
    for row in csv.DictReader(f):
        if row['status'] == 'failed':
            print(f\"{row['email']}:{row['password']}\")
" > failed.txt

python main.py --file failed.txt --workers 2
```

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `cloakbrowser tidak ditemukan` | `pip install cloakbrowser` |
| Browser tidak terbuka | `python -m cloakbrowser info` |
| Login Google gagal terus | Coba `--no-headless`, cek apakah ada ToS/verifikasi tambahan |
| Token tidak terbuat | Cek `results/run.log` untuk detail error |
| Rate limit Google | Kurangi `--workers`, tambah delay di `.env` |
