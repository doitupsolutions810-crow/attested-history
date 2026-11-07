#!/usr/bin/env python3
"""Verify a v1 hash-chained history; never mistake digest for signature/identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ledger_contract import LedgerError, iter_entries

LOG = Path(__file__).resolve().parent / "history.jsonl"


def verify(path: Path) -> dict:
    count = 0
    deepest = 0
    hottest = None
    try:
        for entry in iter_entries(path):
            count += 1
            deepest = max(deepest, entry["provenance_depth"])
            residual = entry.get("residual")
            if isinstance(residual, dict) and residual.get("S") is not None:
                if hottest is None or residual["S"] > hottest["S"]:
                    hottest = {"seq": entry["seq"], "S": residual["S"],
                               "orientation": residual.get("orientation")}
    except LedgerError as exc:
        return {"entries": count, "ok": False, "verified": False, "errors": [str(exc)],
                "max_provenance_depth": deepest, "hottest_residual": hottest,
                "cryptographically_authenticated": False}
    return {"entries": count, "ok": True, "verified": count > 0, "errors": [],
            "max_provenance_depth": deepest, "hottest_residual": hottest,
            "cryptographically_authenticated": False}


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify hash integrity, not signer authenticity")
    ap.add_argument("path", nargs="?", type=Path, default=LOG)
    args = ap.parse_args()
    report = verify(args.path)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
