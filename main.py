# main.py — entry point CLI dengan Rich UI + parallel execution
#
# Usage:
#   python main.py --file emails.txt
#   python main.py --file emails.txt --workers 3
#   python main.py --file emails.txt --workers 4 --no-headless
#   python main.py --file emails.txt --proxy http://user:pass@host:port

import argparse
import logging
import os
import queue
import random
import sys
import threading
import time
from collections import deque
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

import config
import browser as browser_mod
import register as register_mod
import get_apikey as apikey_mod
import cloudflare_api as cf_api
import storage
import verify_email as verify_mod
import proxy_manager
from email_providers import file_provider, tempmail_provider

# ── Logging: file only (Rich handles stdout) ──────────────────────────────────
os.makedirs("results", exist_ok=True)

file_handler = logging.FileHandler("results/run.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
logging.basicConfig(level=logging.INFO, handlers=[file_handler])
log = logging.getLogger(__name__)

console = Console()

# ── Shared state (thread-safe) ────────────────────────────────────────────────
_lock         = threading.Lock()
_start_time   = 0.0
_total_accs   = 0
_recent_logs  = deque(maxlen=6)
_worker_state = {}   # {worker_id: {"email": ..., "status": ...}}


def _set_worker(wid: int, email: str, status: str):
    with _lock:
        _worker_state[wid] = {"email": email, "status": status}


def _add_log(msg: str):
    with _lock:
        ts = datetime.now().strftime("%H:%M:%S")
        _recent_logs.append(f"[dim]{ts}[/dim]  {msg}")


# ── Rich UI builders ──────────────────────────────────────────────────────────

def _build_header(total: int, workers: int) -> Panel:
    elapsed = int(time.time() - _start_time)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    text = Text()
    text.append("  Cloudflare Workers AI", style="bold cyan")
    text.append(" — Auto Register Tool\n", style="bold white")
    text.append(f"  {total} akun", style="yellow")
    text.append("  │  ", style="dim")
    text.append(f"{workers} worker{'s' if workers > 1 else ''}", style="green")
    text.append("  │  elapsed: ", style="dim")
    text.append(f"{h:02d}:{m:02d}:{s:02d}", style="cyan")
    return Panel(text, style="bold blue", padding=(0, 1))


def _build_worker_table(workers: int) -> Table:
    STATUS_STYLE = {
        "idle":    "[dim]⏸  idle[/dim]",
        "login":   "[yellow]🔄 login...[/yellow]",
        "account": "[yellow]🔄 account id[/yellow]",
        "token":   "[yellow]🔄 buat token[/yellow]",
        "verify":  "[yellow]🔄 verifikasi[/yellow]",
        "success": "[green]✓  sukses[/green]",
        "failed":  "[red]✗  gagal[/red]",
        "waiting": "[dim]⏳ menunggu[/dim]",
    }
    tbl = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta", expand=True)
    tbl.add_column("Worker", style="cyan", width=8, justify="center")
    tbl.add_column("Akun", style="white", min_width=30)
    tbl.add_column("Status", min_width=18)
    for i in range(1, workers + 1):
        state  = _worker_state.get(i, {})
        email  = state.get("email", "—")
        status = state.get("status", "idle")
        tbl.add_row(f"#{i}", email, Text.from_markup(STATUS_STYLE.get(status, status)))
    return tbl


def _build_summary(counters: list) -> Panel:
    with _lock:
        done, succ, fail = counters[0], counters[1], counters[2]
    remaining = max(0, _total_accs - done)
    text  = f"[green]✓ Sukses: {succ}[/green]"
    text += f"   [red]✗ Gagal: {fail}[/red]"
    text += f"   [dim]⏳ Sisa: {remaining}[/dim]"
    return Panel(Text.from_markup(text), title="[bold]Summary[/bold]", style="green", padding=(0, 1))


def _build_log_panel() -> Panel:
    with _lock:
        logs = list(_recent_logs)
    content = "\n".join(logs) if logs else "[dim]Belum ada log...[/dim]"
    return Panel(Text.from_markup(content), title="[bold]Log Terbaru[/bold]", style="dim", padding=(0, 1))


def _build_layout(total: int, workers: int, progress: Progress, counters: list) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body"),
        Layout(name="footer", size=10),
    )
    layout["body"].split_row(
        Layout(name="workers", ratio=3),
        Layout(name="right", ratio=2),
    )
    layout["right"].split_column(
        Layout(name="progress", size=5),
        Layout(name="summary", size=5),
    )
    layout["header"].update(_build_header(total, workers))
    layout["workers"].update(Panel(_build_worker_table(workers), title="[bold]Workers[/bold]", style="cyan"))
    layout["progress"].update(Panel(progress, title="[bold]Progress[/bold]", style="blue", padding=(0, 1)))
    layout["summary"].update(_build_summary(counters))
    layout["footer"].update(_build_log_panel())
    return layout


# ── Worker function ───────────────────────────────────────────────────────────

def run_one(worker_id: int, email: str, password: str, mode: str = "google", tm_token: str | None = None, proxy: str | None = None) -> dict:
    result = {
        "email":      email,
        "password":   password,
        "account_id": "",
        "api_token":  "",
        "status":     "failed",
        "reason":     "",
    }
    b, pw = None, None
    try:
        _set_worker(worker_id, email, "login")
        log.info(f"[W{worker_id}] Memulai [{mode}]{' via proxy' if proxy else ''}: {email}")

        pw, b, ctx, page = browser_mod.new_browser(proxy=proxy)

        if mode == "google":
            # ── Mode Google OAuth ────────────────────────────────────────────
            ok = register_mod.register_account(page, ctx, email, password)
            if not ok:
                result["reason"] = "login Google gagal"
                _add_log(f"[red]✗[/red]  {email} → login gagal")
                _set_worker(worker_id, email, "failed")
                return result

            _set_worker(worker_id, email, "account")
            cf_api.wait_for_dashboard_session(page)

        else:
            # ── Mode Tempmail — generate email lazy di dalam worker ──────────
            try:
                _set_worker(worker_id, "generating...", "login")
                provider = config.TEMPMAIL_PROVIDER

                if provider == "mailsac":
                    # Mailsac: tidak perlu register akun, langsung pakai email random
                    from email_providers import mailsac_provider
                    tm       = mailsac_provider.create_account(config.MAILSAC_API_KEY)
                    email    = tm["email"]
                    password = tm["password"]
                    tm_token = None
                else:
                    # mail.tm: perlu buat akun dulu
                    tm       = tempmail_provider.create_account()
                    email    = tm["email"]
                    password = tm["password"]
                    tm_token = tm["token"]

                result["email"]    = email
                result["password"] = password
                _set_worker(worker_id, email, "login")
                log.info(f"[W{worker_id}] Tempmail dibuat [{provider}]: {email}")
            except Exception as e:
                result["reason"] = f"gagal generate tempmail: {e}"
                _add_log(f"[red]✗[/red]  tempmail → generate gagal")
                _set_worker(worker_id, "—", "failed")
                return result

            # Register via form
            ok = register_mod.register_tempmail(page, email, password)
            if not ok:
                result["reason"] = "register form gagal"
                _add_log(f"[red]✗[/red]  {email} → register gagal")
                _set_worker(worker_id, email, "failed")
                return result

            # Verifikasi email
            _set_worker(worker_id, email, "verify")
            verified = verify_mod.verify_email(
                page,
                email_mode="tempmail",
                tm_token=tm_token,
                email=email,
            )
            if not verified:
                result["reason"] = "verifikasi email gagal"
                _add_log(f"[red]✗[/red]  {email} → verifikasi gagal")
                _set_worker(worker_id, email, "failed")
                return result

            _set_worker(worker_id, email, "account")

        # ── Extract cookies + buat session ──────────────────────────────────
        cookies = cf_api.extract_cookies_from_browser(page)
        if not cookies:
            result["reason"] = "gagal extract cookies"
            _set_worker(worker_id, email, "failed")
            return result

        session = cf_api.make_session(cookies)

        # ── Ambil Account ID ─────────────────────────────────────────────────
        account_id = cf_api.get_account_id(session)
        if not account_id:
            account_id = apikey_mod.get_account_id(page)

        # ── Buat Workers AI token ────────────────────────────────────────────
        _set_worker(worker_id, email, "token")
        token_name = f"wai-{email.split('@')[0][:12]}"
        api_token  = cf_api.create_workers_ai_token(session, account_id or "", token_name)

        if not api_token:
            log.info(f"[W{worker_id}] API token gagal, fallback ke browser...")
            api_token = apikey_mod.create_workers_ai_token(page, token_name=token_name)

        if not api_token:
            result["reason"] = "gagal membuat api token"
            _add_log(f"[red]✗[/red]  {email} → gagal buat token")
            _set_worker(worker_id, email, "failed")
            return result

        result.update({
            "account_id": account_id or "",
            "api_token":  api_token,
            "status":     "success",
        })
        _add_log(f"[green]✓[/green]  {email} → [cyan]{api_token[:14]}...[/cyan]")
        log.info(f"[W{worker_id}] ✓ Sukses: {email}")
        _set_worker(worker_id, email, "success")
        return result

    except Exception as e:
        result["reason"] = str(e)
        _add_log(f"[red]✗[/red]  {email} → exception")
        log.error(f"[W{worker_id}] Exception {email}: {e}")
        _set_worker(worker_id, email, "failed")
        return result

    finally:
        if b:
            browser_mod.close_browser(pw, b)


# ── Parallel bulk runner ──────────────────────────────────────────────────────

def run_parallel(accounts: list[dict], workers: int):
    global _start_time, _total_accs

    _total_accs = len(accounts)
    _start_time = time.time()

    # counters[0]=done, counters[1]=success, counters[2]=failed
    counters = [0, 0, 0]

    # Init worker state
    for i in range(1, workers + 1):
        _worker_state[i] = {"email": "—", "status": "idle"}

    # Progress bar
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[cyan]{task.percentage:>5.1f}%[/cyan]"),
        TimeElapsedColumn(),
        expand=False,
    )
    task = progress.add_task("[yellow]Memproses akun...", total=_total_accs)

    # Shared queue — worker ambil satu per satu, tidak ada double-pick
    acc_queue: queue.Queue = queue.Queue()
    for acc in accounts:
        acc_queue.put(acc)

    # Error yang bisa di-retry dengan proxy berbeda
    PROXY_ERRORS = [
        "net::ERR_CERT", "net::ERR_PROXY", "net::ERR_CONNECTION",
        "net::ERR_TUNNEL", "net::ERR_ABORTED", "net::ERR_TIMED_OUT",
        "Target page, context or browser has been closed",
        "Connection closed", "ERR_EMPTY_RESPONSE",
    ]
    MAX_RETRY = 5  # max retry per akun

    def _is_proxy_error(reason: str) -> bool:
        return any(e in reason for e in PROXY_ERRORS)

    def worker_loop(wid: int):
        # Stagger start agar tidak semua login bersamaan
        stagger = random.uniform(1.5, 3.0) * (wid - 1)
        if stagger > 0:
            _set_worker(wid, "—", "waiting")
            time.sleep(stagger)

        while True:
            try:
                acc = acc_queue.get_nowait()
            except queue.Empty:
                break

            # Retry loop — coba sampai sukses atau max retry habis
            retry = 0
            result = None
            while retry < MAX_RETRY:
                # Ambil proxy baru setiap retry
                proxy = acc.get("proxy")
                if not proxy and proxy_manager.has_proxies():
                    proxy = proxy_manager.get_next()

                if retry > 0:
                    log.info(f"[W{wid}] Retry #{retry} untuk {acc.get('email', 'tempmail')} proxy={proxy}")
                    _set_worker(wid, acc.get("email", "—"), "waiting")
                    time.sleep(random.uniform(1.0, 2.0))

                result = run_one(
                    wid,
                    acc["email"],
                    acc["password"],
                    mode=acc.get("mode", "google"),
                    tm_token=acc.get("tm_token"),
                    proxy=proxy,
                )

                if result["status"] == "success":
                    break  # sukses, tidak perlu retry

                reason = result.get("reason", "")

                # Kalau error proxy — retry dengan proxy lain
                if _is_proxy_error(reason) and proxy_manager.has_proxies():
                    log.warning(f"[W{wid}] Proxy error, retry dengan proxy lain: {reason[:60]}")
                    # Reset email untuk tempmail (generate email baru)
                    if acc.get("mode") == "tempmail":
                        acc["email"] = f"__tempmail_retry_{retry}__"
                        acc["password"] = ""
                    retry += 1
                    continue

                # Error lain (register gagal, CAPTCHA, dll) — tidak retry
                break

            with _lock:
                counters[0] += 1
                if result["status"] == "success":
                    counters[1] += 1
                    delay = random.uniform(*config.DELAY_BETWEEN_ACCOUNTS)
                else:
                    counters[2] += 1
                    delay = 0

            storage.save_result(config.OUTPUT_FILE, result)
            progress.advance(task)

            if delay > 0:
                _set_worker(wid, "—", "waiting")
                time.sleep(delay)

        _set_worker(wid, "—", "idle")
        browser_mod.stop_playwright()

    with Live(
        _build_layout(_total_accs, workers, progress, counters),
        refresh_per_second=4,
        console=console,
        screen=False,
    ) as live:
        # Background refresh UI setiap 0.25s
        _stop_refresh = threading.Event()

        def _refresh_loop():
            while not _stop_refresh.is_set():
                live.update(_build_layout(_total_accs, workers, progress, counters))
                time.sleep(0.25)

        refresh_thread = threading.Thread(target=_refresh_loop, daemon=True)
        refresh_thread.start()

        threads = [
            threading.Thread(target=worker_loop, args=(i,), daemon=True)
            for i in range(1, workers + 1)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        _stop_refresh.set()
        refresh_thread.join(timeout=1.0)

    # Final summary
    elapsed = int(time.time() - _start_time)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    apikeys_file = config.OUTPUT_FILE.replace("accounts.csv", "apikeys.txt")
    console.print()
    console.print(Panel(
        f"[green]✓ Sukses: {counters[1]}[/green]   "
        f"[red]✗ Gagal: {counters[2]}[/red]   "
        f"[dim]Total: {_total_accs}   Waktu: {h:02d}:{m:02d}:{s:02d}[/dim]\n"
        f"[dim]📄 CSV    : {config.OUTPUT_FILE}[/dim]\n"
        f"[dim]🔑 API Keys: {apikeys_file}[/dim]",
        title="[bold green]Selesai[/bold green]",
        style="green",
    ))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Cloudflare Workers AI — auto register & get API token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  # Mode Google OAuth
  python main.py --mode google --file emails.txt
  python main.py --mode google --file emails.txt --workers 3

  # Mode Tempmail dengan proxy
  python main.py --mode tempmail --count 10 --proxy-file proxies.txt
  python main.py --mode tempmail --count 50 --workers 3 --proxy-file proxies.txt

  # Debug
  python main.py --mode google --file emails.txt --no-headless
        """,
    )
    parser.add_argument("--mode",       choices=["google", "tempmail"], default="google",
                        help="Mode: 'google' atau 'tempmail'")
    parser.add_argument("--file",       metavar="PATH", default=config.EMAIL_FILE,
                        help=f"File email:password untuk mode google (default: {config.EMAIL_FILE})")
    parser.add_argument("--count",      metavar="N",    type=int, default=1,
                        help="Jumlah akun untuk mode tempmail (default: 1)")
    parser.add_argument("--workers",    metavar="N",    type=int, default=config.CONCURRENCY,
                        help=f"Jumlah browser parallel (default: {config.CONCURRENCY})")
    parser.add_argument("--proxy",      metavar="URL",
                        help="Single proxy URL: http://user:pass@host:port")
    parser.add_argument("--proxy-file", metavar="PATH",
                        help="File list proxy (satu per baris), dirotasi per akun")
    parser.add_argument("--no-headless", action="store_true",
                        help="Tampilkan browser (untuk debug)")
    parser.add_argument("--output",     metavar="PATH",
                        help=f"Output CSV (default: {config.OUTPUT_FILE})")
    return parser.parse_args()


def apply_args(args):
    if args.proxy:       config.PROXY       = args.proxy
    if args.no_headless: config.HEADLESS    = False


def apply_args(args):
    if args.proxy:       config.PROXY       = args.proxy
    if args.no_headless: config.HEADLESS    = False
    if args.output:      config.OUTPUT_FILE = args.output
    if args.file:        config.EMAIL_FILE  = args.file
    if args.workers:     config.CONCURRENCY = args.workers


def _prepare_accounts(args) -> list[dict]:
    """
    Siapkan list akun sesuai mode.
    Mode tempmail: buat placeholder — email di-generate lazy di dalam worker.
    Mode google: baca dari file.
    """
    if args.mode == "tempmail":
        # Buat placeholder — email akan di-generate di dalam worker saat dibutuhkan
        # Ini hindari generate semua di awal (lebih cepat + tidak kena rate limit)
        return [{"email": f"__tempmail_{i}__", "password": "", "mode": "tempmail", "tm_token": None}
                for i in range(args.count)]
    else:
        try:
            raw = file_provider.load_emails(args.file)
            return [{"email": a["email"], "password": a["password"], "mode": "google", "tm_token": None}
                    for a in raw]
        except FileNotFoundError as e:
            console.print(f"[red]❌  {e}[/red]")
            sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    apply_args(args)

    workers  = config.CONCURRENCY
    mode     = args.mode
    provider = config.TEMPMAIL_PROVIDER if mode == "tempmail" else "-"

    # Load proxy file kalau ada
    proxy_count = 0
    if hasattr(args, 'proxy_file') and args.proxy_file:
        proxy_count = proxy_manager.load_proxies(args.proxy_file)
        if proxy_count == 0:
            console.print(f"[yellow]⚠  Proxy file kosong atau tidak ditemukan: {args.proxy_file}[/yellow]")

    # Validasi Mailsac API key kalau mode tempmail + provider mailsac
    if mode == "tempmail" and provider == "mailsac" and not config.MAILSAC_API_KEY:
        console.print("[red]❌  MAILSAC_API_KEY belum di-set![/red]")
        console.print("[dim]    Daftar di https://mailsac.com lalu set di .env:[/dim]")
        console.print("[dim]    MAILSAC_API_KEY=your_api_key[/dim]")
        sys.exit(1)

    # Warn kalau mode tempmail tapi tidak ada proxy
    if mode == "tempmail" and proxy_count == 0 and not config.PROXY:
        console.print("[yellow]⚠  Mode tempmail tanpa proxy — bisa kena rate limit Cloudflare per IP[/yellow]")
        console.print("[dim]    Gunakan --proxy-file proxies.txt untuk rotasi proxy[/dim]")

    proxy_info = f"{proxy_count} proxies dari {args.proxy_file}" if proxy_count > 0 else (config.PROXY or "tidak dipakai")

    console.print(Panel(
        f"[cyan]Mode     :[/cyan] [bold]{mode}[/bold]\n"
        + (f"[cyan]Provider :[/cyan] {provider}\n" if mode == "tempmail" else "")
        + (f"[cyan]File     :[/cyan] {config.EMAIL_FILE}\n" if mode == "google" else f"[cyan]Count    :[/cyan] {args.count} akun\n")
        + f"[cyan]Workers  :[/cyan] {workers}\n"
        f"[cyan]Headless :[/cyan] {config.HEADLESS}\n"
        f"[cyan]Proxy    :[/cyan] {proxy_info}\n"
        f"[cyan]Output   :[/cyan] {config.OUTPUT_FILE}",
        title="[bold cyan]Cloudflare Workers AI — Auto Register Tool[/bold cyan]",
        style="cyan",
    ))

    accounts = _prepare_accounts(args)

    if not accounts:
        console.print("[red]❌  Tidak ada akun yang bisa diproses.[/red]")
        sys.exit(1)

    console.print(f"\n[green]✓[/green] [bold]{len(accounts)}[/bold] akun siap diproses\n")
    log.info(f"Memulai: {len(accounts)} akun, {workers} workers, mode={mode}, provider={provider}, proxies={proxy_count}")

    run_parallel(accounts, workers)


if __name__ == "__main__":
    main()
