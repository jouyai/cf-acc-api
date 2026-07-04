# storage.py — simpan dan baca hasil akun ke CSV/JSON

import csv
import json
import os
import threading
from datetime import datetime, timezone


FIELDNAMES = ["email", "password", "account_id", "api_token", "status", "reason", "created_at"]

_file_lock = threading.Lock()


def _ensure_dir(filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)


def _apikeys_filepath(csv_filepath: str) -> str:
    """Derive path file apikeys.txt dari path CSV."""
    return os.path.join(os.path.dirname(csv_filepath), "apikeys.txt")


def save_result(filepath: str, record: dict):
    """
    Tambah satu record ke CSV.
    Kalau sukses, juga append ke apikeys.txt dengan format accountID:apikey
    """
    _ensure_dir(filepath)

    record.setdefault("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
    record.setdefault("status", "success")
    record.setdefault("reason", "")

    with _file_lock:
        # Simpan ke CSV
        file_exists = os.path.isfile(filepath)
        with open(filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(record)

        # Kalau sukses, append ke apikeys.txt
        if record.get("status") == "success":
            account_id = record.get("account_id", "").strip()
            api_token  = record.get("api_token", "").strip()
            if account_id and api_token:
                apikeys_file = _apikeys_filepath(filepath)
                with open(apikeys_file, "a", encoding="utf-8") as f:
                    f.write(f"{account_id}:{api_token}\n")


def save_failed(filepath: str, email: str, password: str, reason: str):
    """Shortcut: simpan record gagal."""
    save_result(filepath, {
        "email":      email,
        "password":   password,
        "account_id": "",
        "api_token":  "",
        "status":     "failed",
        "reason":     reason,
    })


def load_results(filepath: str) -> list[dict]:
    """Baca semua record dari CSV."""
    if not os.path.isfile(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def export_json(csv_filepath: str, json_filepath: str | None = None):
    """Export CSV ke JSON (opsional, untuk integrasi lain)."""
    records = load_results(csv_filepath)
    if json_filepath is None:
        json_filepath = csv_filepath.replace(".csv", ".json")
    _ensure_dir(json_filepath)
    with open(json_filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    return json_filepath

