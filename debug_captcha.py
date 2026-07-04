# debug_captcha.py — debug Turnstile injection di Cloudflare sign-up
import time
import config
from cloakbrowser import launch
from captcha_solver import solve_turnstile, get_balance

# Cek balance dulu
balance = get_balance(config.CAPSOLVER_API_KEY)
print(f"CapSolver balance: ${balance}")

browser = launch(headless=False, humanize=False)
context = browser.new_context(viewport={"width": 1366, "height": 768}, locale="en-US")
context.set_default_timeout(30000)
page = context.new_page()

print("Buka halaman sign-up...")
page.goto("https://dash.cloudflare.com/sign-up", wait_until="domcontentloaded")

# Tunggu form render (React SPA)
print("Menunggu form render...")
try:
    page.wait_for_selector('input[type="email"], input[name="email"]', timeout=15000, state="visible")
except Exception:
    pass
time.sleep(2)

# Screenshot sebelum
page.screenshot(path="results/debug_captcha_before.png")
print("Screenshot before: results/debug_captcha_before.png")

# Cek semua iframe dan script untuk cari sitekey Turnstile
turnstile_info = page.evaluate("""
    () => {
        // Cari di semua iframe
        const iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src);

        // Cari di semua elemen dengan data-sitekey
        const sitekeys = Array.from(document.querySelectorAll('[data-sitekey]'))
            .map(el => el.getAttribute('data-sitekey'));

        // Cari di semua script content
        const scripts = Array.from(document.querySelectorAll('script'))
            .map(s => s.src || '')
            .filter(s => s.includes('turnstile') || s.includes('challenge'));

        // Cari di HTML page source
        const html = document.documentElement.innerHTML;
        const turnstileMatches = html.match(/0x[A-Za-z0-9_-]{10,}/g) || [];
        const sitekeyMatches = html.match(/sitekey['":\\s]+['"]([^'"]+)['"]/g) || [];

        // Cari di window object
        const windowTurnstile = !!window.turnstile;
        const cfTurnstile = !!window._cf_chl_opt;

        return {
            iframes: iframes.slice(0, 10),
            sitekeys,
            scripts,
            turnstileMatches: [...new Set(turnstileMatches)].slice(0, 10),
            sitekeyMatches: sitekeyMatches.slice(0, 5),
            windowTurnstile,
            cfTurnstile,
        };
    }
""")
print(f"\nTurnstile info:")
for k, v in turnstile_info.items():
    print(f"  {k}: {v}")

# Isi form dulu, lalu submit dan cek CAPTCHA muncul setelah submit
print("\nIsi form email dan password...")
try:
    ef = page.locator('input[type="email"], input[name="email"]').first
    ef.fill("testcaptcha@mailsac.com")
    time.sleep(0.3)
    pf = page.locator('input[type="password"]').first
    pf.fill("TestPass123!")
    time.sleep(0.3)
except Exception as e:
    print(f"Field error: {e}")

print("\nKlik submit untuk trigger CAPTCHA...")
try:
    btn = page.locator('button[type="submit"]').first
    btn.click()
    time.sleep(3)
except Exception as e:
    print(f"Submit error: {e}")

# Cek lagi setelah submit
turnstile_after = page.evaluate("""
    () => {
        const iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src);
        const sitekeys = Array.from(document.querySelectorAll('[data-sitekey]'))
            .map(el => el.getAttribute('data-sitekey'));
        const html = document.documentElement.innerHTML;
        const turnstileMatches = html.match(/0x[A-Za-z0-9_-]{10,}/g) || [];

        // Extract sitekey dari window._cf_chl_opt
        let cfSitekey = null;
        let cfChlOpt = null;
        try {
            cfChlOpt = JSON.stringify(window._cf_chl_opt);
            if (window._cf_chl_opt && window._cf_chl_opt.chlApiSitekey) {
                cfSitekey = window._cf_chl_opt.chlApiSitekey;
            }
        } catch(e) {}

        // Cari di semua property window yang mengandung sitekey
        let windowSitekeys = [];
        try {
            Object.keys(window).forEach(k => {
                try {
                    const val = JSON.stringify(window[k]);
                    const match = val && val.match(/"sitekey"\s*:\s*"(0x[^"]+)"/);
                    if (match) windowSitekeys.push({key: k, sitekey: match[1]});
                } catch(e) {}
            });
        } catch(e) {}

        return {
            iframes: iframes.filter(s => s.includes('turnstile') || s.includes('challenge')),
            sitekeys,
            cfSitekey,
            cfChlOpt: cfChlOpt ? cfChlOpt.substring(0, 200) : null,
            windowSitekeys: windowSitekeys.slice(0, 5),
            url: window.location.href,
        };
    }
""")
print(f"\nSetelah submit:")
for k, v in turnstile_after.items():
    print(f"  {k}: {v}")

page.screenshot(path="results/debug_captcha_submit.png")
print("Screenshot submit: results/debug_captcha_submit.png")

# Cek elemen Turnstile di halaman
turnstile_info = page.evaluate("""
    () => {
        const inputs = document.querySelectorAll('[name="cf-turnstile-response"]');
        const iframes = document.querySelectorAll('iframe[src*="turnstile"]');
        const challenges = document.querySelectorAll('.cf-turnstile, [data-sitekey]');
        return {
            inputs: inputs.length,
            iframes: iframes.length,
            challenges: challenges.length,
            sitekeys: Array.from(challenges).map(el => el.getAttribute('data-sitekey')),
            inputValues: Array.from(inputs).map(i => i.value.substring(0, 20)),
        };
    }
""")
print(f"\nTurnstile info: {turnstile_info}")

# Solve Turnstile
print("\nSolving Turnstile...")
# Ambil sitekey dari halaman kalau ada
sitekeys = turnstile_info.get('sitekeys', [])
sitekey = sitekeys[0] if sitekeys else "0x4AAAAAAA-3X2SmBEn7SZiS"
print(f"Sitekey: {sitekey}")

token = solve_turnstile(
    api_key=config.CAPSOLVER_API_KEY,
    url="https://dash.cloudflare.com/sign-up",
    site_key=sitekey,
)
print(f"Token: {token[:30] if token else None}...")

if token:
    # Inject token
    result = page.evaluate(f"""
        () => {{
            let injected = 0;

            // Method 1: input hidden
            document.querySelectorAll('[name="cf-turnstile-response"]').forEach(el => {{
                el.value = "{token}";
                injected++;
            }});

            // Method 2: textarea
            document.querySelectorAll('textarea[name="cf-turnstile-response"]').forEach(el => {{
                el.value = "{token}";
                injected++;
            }});

            // Method 3: dispatch event ke Turnstile widget
            if (window.turnstile) {{
                try {{ window.turnstile.execute(); }} catch(e) {{}}
            }}

            // Method 4: Cari callback Turnstile dan panggil langsung
            const keys = Object.getOwnPropertyNames(window);
            const cfKeys = keys.filter(k => k.includes('cf') || k.includes('turnstile'));

            return {{
                injected,
                windowKeys: cfKeys,
                hasTurnstile: !!window.turnstile,
            }};
        }}
    """)
    print(f"Injection result: {result}")

    time.sleep(1)

    # Isi form dan submit
    print("\nIsi form...")
    # email
    try:
        ef = page.locator('input[type="email"], input[name="email"]').first
        ef.wait_for(state="visible", timeout=10000)
        ef.fill("test@mailsac.com")
        time.sleep(0.5)
    except Exception as e:
        print(f"Email field error: {e}")

    # password
    try:
        pf = page.locator('input[type="password"]').first
        pf.wait_for(state="visible", timeout=5000)
        pf.fill("TestPass123!")
        time.sleep(0.5)
    except Exception as e:
        print(f"Password field error: {e}")

    # screenshot setelah inject
    page.screenshot(path="results/debug_captcha_after.png")
    print("Screenshot after inject: results/debug_captcha_after.png")

    input("\nTekan Enter untuk submit form...")

    # Submit
    try:
        btn = page.locator('button[type="submit"]').first
        btn.click()
        time.sleep(3)
        print(f"URL setelah submit: {page.url}")
        page.screenshot(path="results/debug_captcha_submit.png")
        print("Screenshot submit: results/debug_captcha_submit.png")
    except Exception as e:
        print(f"Submit error: {e}")

input("\nTekan Enter untuk tutup...")
browser.close()
