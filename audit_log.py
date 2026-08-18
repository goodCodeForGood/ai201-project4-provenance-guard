import json
import os
from datetime import datetime, timezone

LOG_FILE = "audit_log.json"


def _load_log():
    if not os.path.exists(LOG_FILE):
        return []

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_log(entries):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def add_log_entry(entry):
    entries = _load_log()
    entries.append(entry)
    _save_log(entries)


def create_timestamp():
    return datetime.now(timezone.utc).isoformat()


def get_log():
    return _load_log()


def find_entry(content_id):
    entries = _load_log()

    for entry in entries:
        if entry.get("content_id") == content_id:
            return entry

    return None


def update_status(content_id, status, appeal_reasoning=None):
    entries = _load_log()
    found = False

    for entry in entries:
        if entry.get("content_id") == content_id:
            entry["status"] = status

            if appeal_reasoning is not None:
                entry["appeal_reasoning"] = appeal_reasoning

            found = True

    if found:
        _save_log(entries)

    return found