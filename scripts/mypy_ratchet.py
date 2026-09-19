#!/usr/bin/env python3
"""Mypy baseline ratchet: new type errors fail the build; fixes shrink the baseline.

Usage:
  python scripts/mypy_ratchet.py             # compare against baseline (CI mode)
  python scripts/mypy_ratchet.py --regenerate  # rewrite the baseline (after fixing errors)
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "mypy-baseline.txt"
TARGETS = ["core", "apps", "main.py"]


def run_mypy() -> set[str]:
    """Raw error lines (file:line: error: ...)."""
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", *TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        line.strip()
        for line in (proc.stdout + proc.stderr).splitlines()
        if ": error:" in line
    }


_LINE_NO = re.compile(r"^([^:]+):\d+: ")


def normalize(errors: set[str]) -> set[str]:
    """Strip line numbers so edits elsewhere in a file don't shift the baseline."""
    return {_LINE_NO.sub(r"\1: ", e) for e in errors}


def main() -> int:
    current = normalize(run_mypy())
    if "--regenerate" in sys.argv:
        BASELINE.write_text("\n".join(sorted(current)) + "\n", encoding="utf-8")
        print(f"baseline regenerated: {len(current)} errors")
        return 0
    baseline = set(BASELINE.read_text(encoding="utf-8").splitlines()) - {""}
    new_errors = current - baseline
    fixed = baseline - current
    if fixed:
        print(f"{len(fixed)} baseline errors fixed — regenerate with --regenerate to tighten:")
        for e in sorted(fixed):
            print(f"  FIXED: {e}")
    if new_errors:
        print(f"FAIL: {len(new_errors)} NEW mypy error(s) not in baseline:")
        for e in sorted(new_errors):
            print(f"  NEW: {e}")
        return 1
    print(f"mypy ratchet OK: {len(current)} known errors, 0 new, {len(fixed)} fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
