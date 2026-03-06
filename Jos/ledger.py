"""Execution ledger - logs every sales pipeline action with timestamps."""
from __future__ import annotations

import logging
from datetime import datetime

_ledger: list[str] = []
_logger = logging.getLogger("joy.pipeline")


def log(message: str):
    """Add timestamped entry to ledger, emit to stdlib logging, and print."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{ts}] {message}"
    _ledger.append(entry)
    _logger.info(message)
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
