#!/usr/bin/env python3
"""Verify a non-empty append-only history chain; missing evidence is HOLD."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

LOG = Path(__file__).resolve().parent / "history.jsonl"
MAX_LOG_BYTES = 16 * 1024 * 1024
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED = (
    "seq", "ts", "source", "kind", "digest", "provenance_depth",
    "residual", "capability_id", "human_root", "raw", "prev_hash",
)


def _canon(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(obj: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_log(path: Path) -> bytes:
    """Read a bounded regular file without following links or blocking on FIFOs."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("history path is not a regular file")
        if info.st_size > MAX_LOG_BYTES:
            raise OSError(f"history exceeds {MAX_LOG_BYTES} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, MAX_LOG_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_LOG_BYTES:
                raise OSError(f"history exceeds {MAX_LOG_BYTES} bytes")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_entries(path: Path) -> list[dict[str, Any]]:
    raw = _read_log(path)
    text = raw.decode("utf-8", errors="strict")
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(entry, dict):
            raise ValueError(f"line {line_number}: entry must be an object")
        entries.append(entry)
    return entries


def _validate(entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    previous_digest: str | None = None
    hottest: dict[str, Any] | None = None
    max_depth = 0

    for index, entry in enumerate(entries):
        line_number = index + 1
        missing = [key for key in _REQUIRED if key not in entry]
        if missing:
            errors.append(f"line {line_number}: missing required fields: {','.join(missing)}")
            continue

        seq = entry["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq != index:
            errors.append(f"line {line_number}: seq must be contiguous from zero (expected {index})")

        ts = entry["ts"]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= 0:
            errors.append(f"line {line_number}: ts must be a finite positive number")
        for key in ("source", "kind"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                errors.append(f"line {line_number}: {key} must be a non-empty string")
        if not isinstance(entry["raw"], dict):
            errors.append(f"line {line_number}: raw must be an object")

        depth = entry["provenance_depth"]
        human_root = entry["human_root"] is True
        if not human_root and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 1):
            errors.append(f"line {line_number}: provenance_depth must be >= 1 or human_root must be true")
        elif isinstance(depth, int) and not isinstance(depth, bool):
            max_depth = max(max_depth, depth)

        digest = entry["digest"]
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            errors.append(f"line {line_number}: digest must be 64 lowercase hex characters")
        else:
            try:
                expected = _digest({key: value for key, value in entry.items() if key != "digest"})
            except (TypeError, ValueError, OverflowError, RecursionError) as exc:
                errors.append(f"line {line_number}: entry cannot be canonically encoded: {type(exc).__name__}")
            else:
                if expected != digest:
                    errors.append(f"line {line_number}: digest mismatch")

        if entry["prev_hash"] != previous_digest:
            errors.append(f"line {line_number}: chain break")
        previous_digest = digest if isinstance(digest, str) else None

        residual = entry["residual"]
        if residual is not None:
            if not isinstance(residual, dict):
                errors.append(f"line {line_number}: residual must be an object or null")
            else:
                score = residual.get("S")
                orientation = residual.get("orientation")
                if not isinstance(orientation, str) or not orientation.strip():
                    errors.append(f"line {line_number}: residual orientation must be named")
                if score is None:
                    if orientation != "unmeasured":
                        errors.append(f"line {line_number}: null residual.S requires orientation=unmeasured")
                elif (isinstance(score, bool) or not isinstance(score, (int, float))
                      or not math.isfinite(score) or not 0 <= score <= 1):
                    errors.append(f"line {line_number}: residual.S must be finite and within [0,1]")
                elif hottest is None or score > hottest["S"]:
                    hottest = {"seq": seq, "S": score, "orientation": orientation}

    return {
        "status": "VERIFIED" if not errors else "HOLD",
        "entries": len(entries),
        "errors": errors,
        "ok": not errors,
        "max_provenance_depth": max_depth,
        "hottest_residual": hottest,
    }


def main() -> int:
    try:
        entries = _load_entries(LOG)
    except FileNotFoundError:
        print(json.dumps({"status": "HOLD", "ok": False, "reason": "history file missing", "entries": 0}))
        return 2
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as exc:
        print(json.dumps({"status": "HOLD", "ok": False, "reason": f"history unreadable: {exc}", "entries": 0}))
        return 2

    if not entries:
        print(json.dumps({"status": "HOLD", "ok": False,
                          "reason": "history empty; no provenance can be established", "entries": 0}))
        return 2

    report = _validate(entries)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
