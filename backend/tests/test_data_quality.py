"""Fails if any logical invariant of the cleaned CSV files is broken (see scripts/audit_data.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_data  # noqa: E402


def test_data_invariants():
    checks, _ = audit_data.run()
    failed = [(n, d) for n, ok, d in checks if not ok]
    assert not failed, failed
