#!/usr/bin/env python3
"""verify — walk history.jsonl, check digests, chain links, invariants. Exit 1 on break."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

LOG = Path(__file__).resolve().parent / "history.jsonl"


def _canon(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _digest(obj: dict) -> str:
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


def _report(entries: int, errs: list, max_depth: int = 0, hot=None) -> int:
    print(json.dumps({"entries": entries, "errors": errs, "ok": not errs,
                      "max_provenance_depth": max_depth, "hottest_residual": hot}, indent=2))
    return 1 if errs else 0


def main() -> int:
    # A missing ledger is a failure, not an empty pass: deleting the
    # whole history must never verify as OK.
    if not LOG.exists():
        return _report(0, ["ledger file missing: history.jsonl"])
    lines = [l for l in LOG.read_text().splitlines() if l.strip()]
    entries = []
    errs = []
    for n, line in enumerate(lines, start=1):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            errs.append(f"line {n}: malformed JSON ({e.msg})")
    if errs:
        return _report(len(entries), errs)
    prev_digest = None
    max_depth = 0
    hot = None
    for i, e in enumerate(entries):
        # Sequence numbers are the ledger's order: entry i must carry
        # seq == i. A rewritten or duplicated seq is a break, even
        # with a recomputed digest.
        if e.get("seq") != i:
            errs.append(f"seq {e.get('seq')}: out of order (expected {i})")
        raw_wo = {k: v for k, v in e.items() if k != "digest"}
        if _digest(raw_wo) != e["digest"]:
            errs.append(f"seq {e['seq']}: digest mismatch")
        if e["prev_hash"] != prev_digest:
            errs.append(f"seq {e['seq']}: chain break (prev_hash {e['prev_hash']} != {prev_digest})")
        prev_digest = e["digest"]
        max_depth = max(max_depth, e.get("provenance_depth") or 0)
        r = e.get("residual") or {}
        if r.get("S") is not None:
            if hot is None or r["S"] > hot["S"]:
                hot = {"seq": e["seq"], "S": r["S"], "orientation": r.get("orientation")}
    return _report(len(entries), errs, max_depth, hot)


if __name__ == "__main__":
    sys.exit(main())
