"""Execution ledger - logs every sales pipeline action with timestamps."""

from datetime import datetime

_ledger = []


def log(message: str):
    """Add timestamped entry to ledger and print to console."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] {message}"
    _ledger.append(entry)
    print(entry)


def get_log() -> list[str]:
    """Return copy of all ledger entries."""
    return _ledger.copy()


def clear():
    """Clear ledger (for testing)."""
    global _ledger
    _ledger = []


def print_all():
    """Print full ledger to console."""
    print("\n" + "=" * 60)
    print("SALES PIPELINE LEDGER")
    print("=" * 60)
    for entry in _ledger:
        print(entry)
    print("=" * 60 + "\n")
