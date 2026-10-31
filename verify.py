#!/usr/bin/env python3
"""Verify a non-empty append-only history chain; missing evidence is HOLD."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

LOG = Path(__file__).resolve().parent / "history.jsonl"


def _canon(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _digest(obj: dict) -> str:
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


def main() -> int:
    if not LOG.exists():
        print(json.dumps({"status": "HOLD", "ok": False, "reason": "history file missing", "entries": 0}))
        return 2
    try:
        lines = [line for line in LOG.read_text().splitlines() if line.strip()]
        entries = [json.loads(line) for line in lines]
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "ok": False, "reason": f"history unreadable: {exc}", "entries": 0}))
        return 2
    if not entries:
        print(json.dumps({"status": "HOLD", "ok": False, "reason": "history empty; no provenance can be established", "entries": 0}))
        return 2

    errs = []
    prev_digest = None
    previous_seq = None
    max_depth = 0
    hot = None
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errs.append(f"line {i + 1}: entry is not an object")
            continue
        missing = [key for key in ("seq", "prev_hash", "digest") if key not in e]
        if missing:
            errs.append(f"line {i + 1}: missing required fields {','.join(missing)}")
            continue
        seq = e.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int):
            errs.append(f"line {i + 1}: seq must be an integer")
        elif previous_seq is not None and seq <= previous_seq:
            errs.append(f"seq {seq}: sequence is not strictly increasing")
        if isinstance(seq, int) and not isinstance(seq, bool):
            previous_seq = seq

        depth = e.get("provenance_depth")
        human_root = e.get("human_root") is True
        if not human_root and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 1):
            errs.append(f"seq {seq}: provenance_depth must be >= 1 or human_root must be true")
        elif isinstance(depth, int) and not isinstance(depth, bool):
            max_depth = max(max_depth, depth)

        raw_wo = {k: v for k, v in e.items() if k != "digest"}
        if not isinstance(e.get("digest"), str) or _digest(raw_wo) != e.get("digest"):
            errs.append(f"seq {seq}: digest mismatch")
        if e.get("prev_hash") != prev_digest:
            errs.append(f"seq {seq}: chain break (prev_hash {e.get('prev_hash')} != {prev_digest})")
        prev_digest = e.get("digest")

        residual = e.get("residual") or {}
        if isinstance(residual, dict) and residual.get("S") is not None:
            value = residual.get("S")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                errs.append(f"seq {seq}: residual.S must be finite and within [0,1]")
            elif hot is None or value > hot["S"]:
                hot = {"seq": seq, "S": value, "orientation": residual.get("orientation")}

    ok = not errs
    print(json.dumps({
        "status": "VERIFIED" if ok else "HOLD",
        "entries": len(entries),
        "errors": errs,
        "ok": ok,
        "max_provenance_depth": max_depth,
        "hottest_residual": hot,
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
