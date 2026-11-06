from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verify


def digest(entry):
    raw = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class VerifyHistoryTests(unittest.TestCase):
    def test_missing_history_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            with patch.object(verify, "LOG", path), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 2)

    def test_empty_history_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            path.write_text("")
            with patch.object(verify, "LOG", path), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 2)

    def test_valid_human_root_chain_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            entry = {"seq": 1, "prev_hash": None, "provenance_depth": 0, "human_root": True}
            entry["digest"] = digest(entry)
            path.write_text(json.dumps(entry) + "\n")
            with patch.object(verify, "LOG", path), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 0)

    def test_missing_provenance_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            entry = {"seq": 1, "prev_hash": None}
            entry["digest"] = digest(entry)
            path.write_text(json.dumps(entry) + "\n")
            with patch.object(verify, "LOG", path), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 1)

    def test_non_finite_residual_is_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            entry = {"seq": 1, "prev_hash": None, "provenance_depth": 1, "residual": {"S": float("nan")}}
            entry["digest"] = digest(entry)
            path.write_text(json.dumps(entry) + "\n")
            with patch.object(verify, "LOG", path), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 1)


if __name__ == "__main__":
    unittest.main()
