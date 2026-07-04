# debug_tempmail.py — test register Cloudflare + verifikasi via mail.tm
# Jalankan: python debug_tempmail.py

import time
from cloakbrowser import launch
from email_providers import tempmail_provider
import register as register_mod

# 1. Generate tempmail
print("Generating tempmail...")
tm = tempmail_provider.create_account()
email    = tm["email"]
password = tm["password"]
token    = tm["token"]
print(f"Email: {email}")
print(f"Password: {password}")

# 2. Launch browser dan register
browser = launch(headless=False, humanize=False)
context = browser.new_context(viewport={"width": 1366, "height": 768}, locale="en-US")
context.set_default_timeout(30000)
page = context.new_page()

print(f"\nRegister Cloudflare dengan {email}...")
ok = register_mod.register_tempmail(page, email, password)
print(f"Register result: {ok}")
print(f"URL setelah register: {page.url}")

input("\nTekan Enter untuk mulai polling inbox (sambil cek inbox mail.tm)...")

# 3. Poll inbox
print(f"\nPolling inbox mail.tm untuk {email}...")
print("(Tunggu hingga 2 menit)")

deadline = time.time() + 120
interval = 3
import requests
auth_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

while time.time() < deadline:
    try:
        resp = requests.get("https://api.mail.tm/messages", headers=auth_headers, timeout=10)
        data = resp.json()
        messages = data.get("hydra:member", [])
        print(f"  Inbox: {len(messages)} pesan", end="\r")
        
        for msg in messages:
            subject = msg.get("subject", "")
            from_addr = msg.get("from", {}).get("address", "")
            print(f"\n  📧 Email masuk!")
            print(f"     From: {from_addr}")
            print(f"     Subject: {subject}")
            
            # Ambil detail
            detail = requests.get(
                f"https://api.mail.tm/messages/{msg['id']}",
                headers=auth_headers, timeout=10
            ).json()
            
            body = detail.get("html", "") or detail.get("text", "")
            if isinstance(body, list):
                body = " ".join(body)
            
            import re
            links = re.findall(r'https://[^\s"\'<>]+', body[:2000])
            print(f"     Links ditemukan: {len(links)}")
            for l in links[:5]:
                print(f"       {l[:100]}")
            
            input("\nTekan Enter untuk buka link verifikasi pertama di browser...")
            if links:
                page.goto(links[0], wait_until="domcontentloaded")
                time.sleep(3)
                print(f"URL setelah klik link: {page.url}")
            break
        else:
            time.sleep(interval)
            continue
        break
    except Exception as e:
        print(f"\nError: {e}")
        time.sleep(interval)
else:
    print("\nTimeout — tidak ada email masuk dalam 2 menit.")
    print("Kemungkinan Cloudflare tidak mengirim ke domain mail.tm ini.")

input("\nTekan Enter untuk tutup...")
browser.close()
