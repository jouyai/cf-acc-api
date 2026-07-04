# Cloudflare Workers AI — Auto Register Tool

Tool otomatis untuk register akun Cloudflare dan ambil Workers AI API key secara bulk, menggunakan [CloakBrowser](https://github.com/CloakHQ/cloakbrowser) (stealth Chromium) + Rich terminal UI.

## Fitur

- **Mode Google** — login via Google OAuth pakai akun Gmail/GSuite dari file
- **Mode Tempmail** — generate akun Cloudflare baru otomatis via Mailsac atau mail.tm
- Parallel workers dengan Rich terminal UI live
- Ambil Account ID + buat Workers AI token via Cloudflare API (cepat)
- Output `apikeys.txt` format `accountID:apikey` + `accounts.csv` lengkap
- Fallback browser jika API gagal

## Instalasi

```bash
git clone https://github.com/jouyai/cf-acc-api.git
cd cf-acc-api

pip install -r requirements.txt
python -m cloakbrowser install
```

## Konfigurasi

Buat file `.env`:

```env
# Mode tempmail provider: "mailsac" atau "mailtm"
TEMPMAIL_PROVIDER=mailsac

# Mailsac API key (wajib untuk mode tempmail + provider mailsac)
# Daftar gratis di https://mailsac.com
MAILSAC_API_KEY=your_mailsac_api_key_here

# Browser
HEADLESS=true
HUMANIZE=true
CONCURRENCY=2

# Delay antar akun (detik)
DELAY_MIN=3
DELAY_MAX=8

# Output
OUTPUT_FILE=results/accounts.csv
PAGE_TIMEOUT=60
EMAIL_POLL_TIMEOUT=120
EMAIL_POLL_INTERVAL=5

# Proxy (opsional)
# PROXY=http://user:pass@host:port

# CloakBrowser Pro license (opsional)
# CLOAKBROWSER_LICENSE_KEY=cb_xxxxxxxx
```

## Cara Pakai

### Mode Google (pakai akun Gmail/GSuite)

Buat `emails.txt`:
```
akun1@gmail.com:Password123!
akun2@yourdomain.com:AnotherPass456!
```

Jalankan:
```bash
python main.py --mode google --file emails.txt
python main.py --mode google --file emails.txt --workers 3
python main.py --mode google --file emails.txt --no-headless  # debug
```

### Mode Tempmail (generate akun baru otomatis)

Pastikan `MAILSAC_API_KEY` sudah di-set di `.env`, lalu:

```bash
# Generate 10 akun baru
python main.py --mode tempmail --count 10

# Generate 50 akun, 3 workers paralel
python main.py --mode tempmail --count 50 --workers 3

# Debug
python main.py --mode tempmail --count 3 --no-headless
```

### Semua opsi CLI

```
--mode        google | tempmail
--file PATH   File email:password (mode google, default: emails.txt)
--count N     Jumlah akun baru (mode tempmail, default: 1)
--workers N   Jumlah browser parallel (default: 2)
--proxy URL   Proxy: http://user:pass@host:port
--no-headless Tampilkan browser (debug)
--output PATH Output CSV (default: results/accounts.csv)
```

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

## Struktur Project

```
cf-acc-api/
├── main.py                       # Entry point CLI + Rich UI + parallel workers
├── register.py                   # Google OAuth + Tempmail register flow
├── cloudflare_api.py             # Cloudflare API (account ID + token)
├── browser.py                    # CloakBrowser wrapper
├── get_apikey.py                 # Browser fallback untuk buat token
├── verify_email.py               # Verifikasi email (Mailsac / mail.tm)
├── storage.py                    # Simpan ke CSV + apikeys.txt
├── config.py                     # Konfigurasi global
├── email_providers/
│   ├── file_provider.py          # Baca email dari file
│   ├── tempmail_provider.py      # mail.tm API
│   └── mailsac_provider.py       # Mailsac API
├── emails.txt                    # Template file email (mode google)
└── requirements.txt
```

## Tips

- **Mode Google**: 2-3 workers optimal untuk 1 IP
- **Mode Tempmail**: butuh Mailsac API key, daftar gratis di [mailsac.com](https://mailsac.com)
- Retry akun yang gagal:

```bash
python -c "
import csv
with open('results/accounts.csv') as f:
    for row in csv.DictReader(f):
        if row['status'] == 'failed':
            print(f\"{row['email']}:{row['password']}\")
" > failed.txt
python main.py --mode google --file failed.txt
```

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `MAILSAC_API_KEY belum di-set` | Set `MAILSAC_API_KEY=xxx` di `.env` |
| Login Google gagal | Coba `--no-headless`, cek apakah ada ToS/verifikasi |
| Verifikasi email timeout | Cek inbox Mailsac manual, naikkan `EMAIL_POLL_TIMEOUT=180` |
| `cloakbrowser tidak ditemukan` | `pip install cloakbrowser` |
| Rate limit Google | Kurangi `--workers`, tambah delay di `.env` |
