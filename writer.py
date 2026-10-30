#!/usr/bin/env python3
"""writer — append one attested entry to the history log."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent / "history.jsonl"


def _canon(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _digest(obj: dict) -> str:
    return hashlib.sha256(_canon(obj).encode()).hexdigest()


def last_entry() -> dict | None:
    if not LOG.exists():
        return None
    lines = [l for l in LOG.read_text().splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def append(source: str, kind: str, raw: dict, *, residual: dict | None = None,
           provenance_depth: int = 0, capability_id: str | None = None,
           human_root: str | None = None) -> dict:
    if provenance_depth < 1 and human_root is None:
        raise ValueError("ingest rejected: model-only chain (provenance_depth < 1, no human_root)")
    if residual is not None and residual.get("S") is None and residual.get("orientation") != "unmeasured":
        raise ValueError("ingest rejected: unmeasured residual must be explicitly named")
    prev = last_entry()
    entry = {
        "seq": (prev["seq"] + 1) if prev else 0,
        "ts": time.time(),
        "source": source,
        "kind": kind,
        "digest": "",  # filled below
        "provenance_depth": provenance_depth,
        "residual": residual,
        "capability_id": capability_id,
        "human_root": human_root,
        "raw": raw,
        "prev_hash": prev["digest"] if prev else None,
    }
    entry["digest"] = _digest({k: v for k, v in entry.items() if k != "digest"})
    with LOG.open("a") as f:
        f.write(_canon(entry) + "\n")
    return entry


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--raw", required=True, help="JSON string")
    p.add_argument("--S", type=float, default=None)
    p.add_argument("--orientation", default=None)
    p.add_argument("--depth", type=int, default=0)
    p.add_argument("--capability", default=None)
    p.add_argument("--human-root", default=None)
    a = p.parse_args()
    residual = None
    if a.S is not None or a.orientation is not None:
        residual = {"S": a.S, "orientation": a.orientation}
    e = append(a.source, a.kind, json.loads(a.raw), residual=residual,
               provenance_depth=a.depth, capability_id=a.capability,
               human_root=a.human_root)
    print(json.dumps({"seq": e["seq"], "digest": e["digest"]}, indent=2))


if __name__ == "__main__":
    main()
