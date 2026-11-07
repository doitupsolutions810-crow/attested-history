from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import verify


def make_entry(seq=0, prev_hash=None, **changes):
    entry = {
        "seq": seq,
        "ts": 1794012208.0,
        "source": "Avrone",
        "kind": "ci_census",
        "provenance_depth": 1,
        "residual": {"S": 0.152344, "orientation": "fail"},
        "capability_id": None,
        "human_root": None,
        "raw": {"runs": 7, "passes": 1},
        "prev_hash": prev_hash,
    }
    entry.update(changes)
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    entry["digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    return entry


def write_log(path: Path, entries):
    path.write_text("".join(json.dumps(e, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for e in entries))


def run_verify(path, monkeypatch):
    monkeypatch.setattr(verify, "LOG", path)
    return verify.main()


def test_missing_and_empty_are_hold(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "missing.jsonl"
    assert run_verify(missing, monkeypatch) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "HOLD"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n  \n")
    assert run_verify(empty, monkeypatch) == 2
    assert "empty" in json.loads(capsys.readouterr().out)["reason"]


def test_current_nonempty_history_verifies(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    write_log(path, [make_entry()])
    assert run_verify(path, monkeypatch) == 0


def test_two_entry_chain_verifies(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    first = make_entry()
    second = make_entry(seq=1, prev_hash=first["digest"], raw={"runs": 8})
    write_log(path, [first, second])
    assert run_verify(path, monkeypatch) == 0


def test_digest_tamper_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    entry = make_entry()
    entry["raw"]["runs"] = 99
    write_log(path, [entry])
    assert run_verify(path, monkeypatch) == 1


def test_sequence_gap_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    write_log(path, [make_entry(seq=3)])
    assert run_verify(path, monkeypatch) == 1


def test_missing_provenance_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    write_log(path, [make_entry(provenance_depth=0)])
    assert run_verify(path, monkeypatch) == 1


@pytest.mark.parametrize("residual", [
    {"S": float("nan"), "orientation": "fail"},
    {"S": float("inf"), "orientation": "fail"},
    {"S": -0.1, "orientation": "fail"},
    {"S": 1.1, "orientation": "pass"},
    {"S": None, "orientation": "pass"},
    {"S": 0.1, "orientation": ""},
])
def test_bad_residual_is_rejected(tmp_path, monkeypatch, residual):
    path = tmp_path / "history.jsonl"
    entry = make_entry()
    entry["residual"] = residual
    entry["digest"] = "0" * 64
    line = json.dumps(entry, sort_keys=True, separators=(",", ":"), allow_nan=True)
    path.write_text(line + "\n")
    assert run_verify(path, monkeypatch) in (1, 2)


def test_invalid_json_and_duplicate_keys_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    path.write_text('{"seq":0,"seq":1}\n')
    assert run_verify(path, monkeypatch) == 2
    path.write_text('{"seq":NaN}\n')
    assert run_verify(path, monkeypatch) == 2


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation unavailable")
def test_fifo_is_rejected_without_blocking(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    os.mkfifo(path)
    assert run_verify(path, monkeypatch) == 2


def test_symlink_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "target.jsonl"
    target.write_text(json.dumps(make_entry()) + "\n")
    link = tmp_path / "history.jsonl"
    link.symlink_to(target)
    assert run_verify(link, monkeypatch) == 2


def test_oversized_history_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "history.jsonl"
    path.write_bytes(b" " * (verify.MAX_LOG_BYTES + 1))
    assert run_verify(path, monkeypatch) == 2
