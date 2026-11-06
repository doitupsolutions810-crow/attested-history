#!/usr/bin/env python3
"""Append a validated history record with cross-process locking and fsync."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import time
from pathlib import Path
from typing import Iterator

from ledger_contract import LedgerError, canonical_bytes, iter_entries, record_digest, validate_entry

LOG = Path(__file__).resolve().parent / "history.jsonl"


@contextlib.contextmanager
def _exclusive_writer(path: Path) -> Iterator[None]:
    # A stable sidecar lock survives atomic replaces. Do not silently weaken on Windows.
    try:
        import fcntl
    except ImportError as exc:
        raise LedgerError("POSIX flock required for safe concurrent appends") from exc
    lock_path = path.with_name(path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LedgerError("cannot open ledger lock") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def last_entry(path: Path | None = None) -> dict | None:
    last = None
    for last in iter_entries(path if path is not None else LOG):
        pass
    return last


def append(source: str, kind: str, raw: dict, *, residual: dict | None = None,
           provenance_depth: int = 0, capability_id: str | None = None,
           human_root: str | None = None) -> dict:
    with _exclusive_writer(LOG):
        prev = last_entry()
        entry = {
            "seq": prev["seq"] + 1 if prev else 0,
            "ts": time.time(),
            "source": source,
            "kind": kind,
            "digest": "",
            "provenance_depth": provenance_depth,
            "residual": residual,
            "capability_id": capability_id,
            "human_root": human_root,
            "raw": raw,
            "prev_hash": prev["digest"] if prev else None,
        }
        entry["digest"] = record_digest({k: v for k, v in entry.items() if k != "digest"})
        validate_entry(entry, seq=entry["seq"], previous_digest=entry["prev_hash"])
        encoded = canonical_bytes(entry) + b"\n"
        if len(encoded) > 1_048_576:
            raise LedgerError("entry exceeds ledger byte limit")
        flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(LOG, flags, 0o600)
            try:
                cursor = 0
                while cursor < len(encoded):
                    count = os.write(fd, encoded[cursor:])
                    if count <= 0:
                        raise OSError("short append")
                    cursor += count
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise LedgerError("append failed; inspect ledger for a torn final line") from exc
        return entry


def main() -> None:
    p = argparse.ArgumentParser(description="Append strictly checked attested-history record")
    p.add_argument("--source", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--raw", required=True, help="JSON object string")
    p.add_argument("--S", type=float, default=None)
    p.add_argument("--orientation", default=None)
    p.add_argument("--depth", type=int, default=0)
    p.add_argument("--capability", default=None)
    p.add_argument("--human-root", default=None)
    a = p.parse_args()
    residual = None
    if a.S is not None or a.orientation is not None:
        residual = {"S": a.S, "orientation": a.orientation}
    from ledger_contract import strict_loads
    try:
        e = append(a.source, a.kind, strict_loads(a.raw.encode()), residual=residual,
                   provenance_depth=a.depth, capability_id=a.capability, human_root=a.human_root)
    except LedgerError as exc:
        p.exit(1, f"ledger refused: {exc}\n")
    print(json.dumps({"seq": e["seq"], "digest": e["digest"]}, indent=2))


if __name__ == "__main__":
    main()
