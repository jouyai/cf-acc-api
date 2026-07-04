# proxy_scraper.py — scrape dan filter proxy publik gratis
#
# Source:
#   - https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt
#   - https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-status.txt
#   - https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt
#   - https://api.proxyscrape.com/v2/?request=getproxies&protocol=http
#
# Jalankan: python proxy_scraper.py
# Output: proxies.txt (proxy yang masih hidup)

import requests
import concurrent.futures
import time
import sys
import os
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

console = Console()

SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-status.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
]

# URL untuk test apakah proxy hidup
TEST_URL     = "https://api.ipify.org?format=json"
TEST_TIMEOUT = 8  # detik


def fetch_proxies_from_source(url: str) -> list[str]:
    """Ambil list proxy dari satu source."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        proxies = []
        for line in resp.text.splitlines():
            line = line.strip()
            # Filter baris yang bukan IP:port
            if not line or line.startswith("#"):
                continue
            # Format: IP:PORT atau IP:PORT online/dead
            parts = line.split()
            addr = parts[0]
            # Skip kalau ada "dead" di baris
            if len(parts) > 1 and "dead" in parts[1].lower():
                continue
            # Validasi format IP:PORT
            if ":" in addr and len(addr.split(":")) == 2:
                proxies.append(f"http://{addr}")
        return proxies
    except Exception as e:
        return []


def test_proxy(proxy: str) -> bool:
    """Test apakah proxy masih hidup dan bisa akses internet."""
    try:
        resp = requests.get(
            TEST_URL,
            proxies={"http": proxy, "https": proxy},
            timeout=TEST_TIMEOUT,
        )
        return resp.status_code == 200
    except Exception:
        return False


def scrape_and_filter(
    output_file: str = "proxies.txt",
    max_proxies: int = 50,
    max_workers: int = 50,
):
    """
    Scrape proxy dari semua source, test yang hidup, simpan ke file.
    
    Args:
        output_file: path output file
        max_proxies: jumlah proxy hidup yang diinginkan
        max_workers: jumlah thread concurrent untuk test
    """
    console.print("\n[bold cyan]Proxy Scraper[/bold cyan] — mengambil proxy publik gratis\n")

    # 1. Fetch dari semua source
    console.print("[dim]Mengambil proxy dari sources...[/dim]")
    all_proxies = set()
    for url in SOURCES:
        console.print(f"  Fetch: [dim]{url[:70]}[/dim]", end="")
        proxies = fetch_proxies_from_source(url)
        all_proxies.update(proxies)
        console.print(f" → [green]{len(proxies)} proxies[/green]")

    all_proxies = list(all_proxies)
    console.print(f"\n[green]Total unik: {len(all_proxies)} proxies[/green]\n")

    if not all_proxies:
        console.print("[red]Tidak ada proxy yang berhasil di-fetch.[/red]")
        return []

    # 2. Test proxy secara parallel
    console.print(f"[dim]Testing {min(len(all_proxies), 500)} proxy (timeout {TEST_TIMEOUT}s)...[/dim]\n")
    
    # Batasi yang di-test agar tidak terlalu lama
    test_batch = all_proxies[:1000]
    live_proxies = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[green]{task.fields[alive]} live[/green]"),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[yellow]Testing proxies...",
            total=len(test_batch),
            alive=0,
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(test_proxy, p): p for p in test_batch}
            for future in concurrent.futures.as_completed(futures):
                proxy = futures[future]
                progress.advance(task)
                try:
                    if future.result():
                        live_proxies.append(proxy)
                        progress.update(task, alive=len(live_proxies))
                        if len(live_proxies) >= max_proxies:
                            # Cancel semua future yang tersisa
                            for f in futures:
                                f.cancel()
                            break
                except Exception:
                    pass

    console.print(f"\n[green]✓ {len(live_proxies)} proxy hidup ditemukan[/green]")

    # 3. Simpan ke file
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Proxy list — di-generate oleh proxy_scraper.py\n")
        f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(live_proxies)} live proxies\n\n")
        for p in live_proxies:
            f.write(f"{p}\n")

    console.print(f"[dim]📄 Disimpan ke: {output_file}[/dim]\n")
    return live_proxies


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape proxy publik gratis")
    parser.add_argument("--output",  default="proxies.txt", help="Output file (default: proxies.txt)")
    parser.add_argument("--count",   type=int, default=50,  help="Jumlah proxy hidup yang diinginkan (default: 50)")
    parser.add_argument("--threads", type=int, default=50,  help="Jumlah thread test (default: 50)")
    args = parser.parse_args()

    proxies = scrape_and_filter(
        output_file=args.output,
        max_proxies=args.count,
        max_workers=args.threads,
    )

    if proxies:
        console.print(f"[bold green]Selesai! {len(proxies)} proxy siap dipakai.[/bold green]")
        console.print(f"\nJalankan tool dengan proxy:")
        console.print(f"  [cyan]python main.py --mode tempmail --count 10 --proxy-file {args.output}[/cyan]\n")
    else:
        console.print("[red]Tidak ada proxy hidup yang ditemukan.[/red]")
        sys.exit(1)
