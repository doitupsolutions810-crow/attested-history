"""Strict v1 attested-history JSONL contract (hash chained, NOT authenticated)."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterator

MAX_LINE_BYTES = 1_048_576
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_ORIENTATION = frozenset({"pass", "fail", "mixed", "unmeasured"})


class LedgerError(ValueError):
    """The ledger contains an untrusted or inconsistent record."""


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise LedgerError("duplicate JSON key")
        obj[key] = value
    return obj


def strict_loads(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8", errors="strict"),
                          parse_constant=lambda _: (_ for _ in ()).throw(LedgerError("nonfinite JSON token")),
                          object_pairs_hook=_no_duplicates)
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise LedgerError(f"invalid JSON record: {type(exc).__name__}") from exc


def canonical_bytes(obj: Any) -> bytes:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise LedgerError("record cannot be canonicalized") from exc


def record_digest(entry_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(entry_without_digest)).hexdigest()


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _label(value: Any, name: str, max_len: int = 128) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise LedgerError(f"{name} must be a nonempty bounded string")


def validate_entry(entry: Any, *, seq: int, previous_digest: str | None) -> str:
    if not isinstance(entry, dict):
        raise LedgerError("entry must be an object")
    required = {"seq", "ts", "source", "kind", "digest", "provenance_depth", "residual",
                "capability_id", "human_root", "raw", "prev_hash"}
    if set(entry) != required:
        raise LedgerError("entry schema mismatch")
    if type(entry["seq"]) is not int or entry["seq"] != seq:
        raise LedgerError("non-contiguous sequence")
    stamp = entry["ts"]
    if not _finite_number(stamp) or stamp <= 0:
        raise LedgerError("invalid timestamp")
    _label(entry["source"], "source")
    _label(entry["kind"], "kind")
    if not isinstance(entry["raw"], dict):
        raise LedgerError("raw evidence must be an object")
    depth = entry["provenance_depth"]
    if type(depth) is not int or not 0 <= depth <= 1_000_000:
        raise LedgerError("invalid provenance depth")
    root = entry["human_root"]
    if root is not None:
        _label(root, "human_root", 256)
    if depth == 0 and root is None:
        raise LedgerError("unprovenanced/model-only entry is not admissible")
    cap = entry["capability_id"]
    if cap is not None:
        _label(cap, "capability_id", 256)
    residual = entry["residual"]
    if residual is not None:
        if not isinstance(residual, dict):
            raise LedgerError("residual must be an object or null")
        orientation = residual.get("orientation")
        if orientation not in _ALLOWED_ORIENTATION:
            raise LedgerError("invalid or missing orientation")
        s = residual.get("S")
        if s is None:
            if orientation != "unmeasured":
                raise LedgerError("unmeasured residual must be named")
        elif not _finite_number(s) or not 0 <= s <= 0.25:
            raise LedgerError("residual S must be finite and between zero and one-quarter")
        cone = residual.get("cone")
        if cone is not None and type(cone) is not bool:
            raise LedgerError("cone must be boolean")
    if entry["prev_hash"] != previous_digest:
        raise LedgerError("chain link mismatch")
    digest = entry["digest"]
    if not isinstance(digest, str) or not _HEX.fullmatch(digest):
        raise LedgerError("digest format invalid")
    actual = record_digest({k: v for k, v in entry.items() if k != "digest"})
    if digest != actual:
        raise LedgerError("record digest mismatch")
    return digest


def iter_entries(path: Path) -> Iterator[dict[str, Any]]:
    """Streaming verification, including duplicate keys, oversized and torn lines."""
    seq, previous = 0, None
    if not path.exists():
        return
    if path.is_symlink():
        raise LedgerError("ledger path must not be a symlink")
    try:
        with path.open("rb") as stream:
            while True:
                line = stream.readline(MAX_LINE_BYTES + 2)
                if not line:
                    break
                if len(line) > MAX_LINE_BYTES:
                    raise LedgerError(f"line {seq}: exceeds byte limit")
                if not line.endswith(b"\n"):
                    raise LedgerError(f"line {seq}: torn final append")
                if not line.strip():
                    raise LedgerError(f"line {seq}: blank record")
                entry = strict_loads(line)
                try:
                    previous = validate_entry(entry, seq=seq, previous_digest=previous)
                except LedgerError as exc:
                    raise LedgerError(f"line {seq}: {exc}") from exc
                seq += 1
                yield entry
    except OSError as exc:
        raise LedgerError(f"ledger I/O failed: {type(exc).__name__}") from exc
