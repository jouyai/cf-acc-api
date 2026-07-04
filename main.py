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
from email_providers import file_provider

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

def run_one(worker_id: int, email: str, password: str) -> dict:
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
        log.info(f"[W{worker_id}] Memulai: {email}")

        pw, b, ctx, page = browser_mod.new_browser()

        # 1. Login Google OAuth via browser
        ok = register_mod.register_account(page, ctx, email, password)
        if not ok:
            result["reason"] = "login Google gagal"
            _add_log(f"[red]✗[/red]  {email} → login gagal")
            log.error(f"[W{worker_id}] Login gagal: {email}")
            _set_worker(worker_id, email, "failed")
            return result

        # 2. Tunggu dashboard fully loaded agar semua cookies ter-set
        _set_worker(worker_id, email, "account")
        cf_api.wait_for_dashboard_session(page)

        # 3. Extract cookies dari browser
        cookies = cf_api.extract_cookies_from_browser(page)
        if not cookies:
            result["reason"] = "gagal extract cookies"
            _set_worker(worker_id, email, "failed")
            return result

        # 4. Buat HTTP session dengan cookies — browser tidak dibutuhkan lagi
        session = cf_api.make_session(cookies)

        # 5. Ambil Account ID via API (cepat, tanpa browser)
        account_id = cf_api.get_account_id(session)
        if not account_id:
            # Fallback ke browser kalau API gagal
            account_id = apikey_mod.get_account_id(page)

        # 6. Buat Workers AI token via API (cepat, tanpa browser)
        _set_worker(worker_id, email, "token")
        token_name = f"wai-{email.split('@')[0][:12]}"
        api_token  = cf_api.create_workers_ai_token(session, account_id or "", token_name)

        # Fallback ke browser kalau API gagal
        if not api_token:
            log.info(f"[W{worker_id}] API token gagal, fallback ke browser...")
            api_token = apikey_mod.create_workers_ai_token(page, token_name=token_name)

        if not api_token:
            result["reason"] = "gagal membuat api token"
            _add_log(f"[red]✗[/red]  {email} → gagal buat token")
            log.error(f"[W{worker_id}] Gagal buat token: {email}")
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

    def worker_loop(wid: int):
        # Stagger start agar tidak semua login Google bersamaan
        stagger = random.uniform(1.5, 3.0) * (wid - 1)
        if stagger > 0:
            _set_worker(wid, "—", "waiting")
            time.sleep(stagger)

        while True:
            try:
                acc = acc_queue.get_nowait()
            except queue.Empty:
                break

            result = run_one(wid, acc["email"], acc["password"])

            with _lock:
                counters[0] += 1
                if result["status"] == "success":
                    counters[1] += 1
                    delay = random.uniform(*config.DELAY_BETWEEN_ACCOUNTS)
                else:
                    counters[2] += 1
                    delay = 0  # gagal → langsung lanjut

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
        description="Cloudflare Workers AI — auto login via Google & get API token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python main.py --file emails.txt
  python main.py --file emails.txt --workers 3
  python main.py --file emails.txt --workers 4 --no-headless
  python main.py --file emails.txt --proxy http://user:pass@host:port
        """,
    )
    parser.add_argument("--file",        metavar="PATH", default=config.EMAIL_FILE,
                        help=f"File email:password (default: {config.EMAIL_FILE})")
    parser.add_argument("--workers",     metavar="N",    type=int, default=config.CONCURRENCY,
                        help=f"Jumlah browser parallel (default: {config.CONCURRENCY})")
    parser.add_argument("--proxy",       metavar="URL",
                        help="Proxy URL: http://user:pass@host:port")
    parser.add_argument("--no-headless", action="store_true",
                        help="Tampilkan browser (untuk debug)")
    parser.add_argument("--output",      metavar="PATH",
                        help=f"Output CSV (default: {config.OUTPUT_FILE})")
    return parser.parse_args()


def apply_args(args):
    if args.proxy:       config.PROXY       = args.proxy
    if args.no_headless: config.HEADLESS    = False
    if args.output:      config.OUTPUT_FILE = args.output
    if args.file:        config.EMAIL_FILE  = args.file
    if args.workers:     config.CONCURRENCY = args.workers


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    apply_args(args)

    workers = config.CONCURRENCY

    console.print(Panel(
        f"[cyan]File     :[/cyan] {config.EMAIL_FILE}\n"
        f"[cyan]Workers  :[/cyan] {workers}\n"
        f"[cyan]Headless :[/cyan] {config.HEADLESS}\n"
        f"[cyan]Proxy    :[/cyan] {config.PROXY or 'tidak dipakai'}\n"
        f"[cyan]Output   :[/cyan] {config.OUTPUT_FILE}",
        title="[bold cyan]Cloudflare Workers AI — Auto Register Tool[/bold cyan]",
        style="cyan",
    ))

    try:
        accounts = file_provider.load_emails(config.EMAIL_FILE)
    except FileNotFoundError as e:
        console.print(f"[red]❌  {e}[/red]")
        sys.exit(1)

    if not accounts:
        console.print("[red]❌  File email kosong.[/red]")
        sys.exit(1)

    console.print(f"\n[green]✓[/green] [bold]{len(accounts)}[/bold] akun dimuat dari [cyan]{config.EMAIL_FILE}[/cyan]\n")
    log.info(f"Memulai: {len(accounts)} akun, {workers} workers")

    run_parallel(accounts, workers)


if __name__ == "__main__":
    main()
