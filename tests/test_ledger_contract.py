from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import writer
import verify
from ledger_contract import LedgerError, record_digest, strict_loads


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = pathlib.Path(self.temp.name) / "history.jsonl"
        self.patcher = patch.object(writer, "LOG", self.log)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def put(self, **kw):
        return writer.append("great-scale", "measurement", {"value": 3},
                             provenance_depth=1, residual={"S": 0.125, "orientation": "mixed"}, **kw)

    def test_valid_chain_and_last_entry(self):
        first, second = self.put(), self.put()
        self.assertEqual(first["seq"], 0)
        self.assertEqual(second["prev_hash"], first["digest"])
        self.assertEqual(writer.last_entry()["digest"], second["digest"])
        report = verify.verify(self.log)
        self.assertEqual(report["entries"], 2)
        self.assertTrue(report["verified"])
        self.assertFalse(report["cryptographically_authenticated"])

    def test_empty_log_not_claimed_verified(self):
        self.assertTrue(verify.verify(self.log)["ok"])
        self.assertFalse(verify.verify(self.log)["verified"])

    def test_tampered_digest_fails(self):
        self.put()
        record = json.loads(self.log.read_text())
        record["raw"]["value"] = 200
        self.log.write_text(json.dumps(record) + "\n")
        self.assertFalse(verify.verify(self.log)["ok"])

    def test_recomputed_digest_cannot_mask_invalid_provenance(self):
        self.put()
        record = json.loads(self.log.read_text())
        record["provenance_depth"] = 0
        record["digest"] = record_digest({k: v for k, v in record.items() if k != "digest"})
        self.log.write_text(json.dumps(record) + "\n")
        self.assertFalse(verify.verify(self.log)["ok"])

    def test_noncontiguous_seq_and_bad_link(self):
        self.put()
        self.put()
        first, second = [json.loads(s) for s in self.log.read_text().splitlines()]
        second["seq"] = 99
        second["digest"] = record_digest({k: v for k, v in second.items() if k != "digest"})
        self.log.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
        self.assertFalse(verify.verify(self.log)["ok"])

    def test_unmeasured_must_be_named(self):
        with self.assertRaises(LedgerError):
            writer.append("x", "y", {}, provenance_depth=1,
                          residual={"S": None, "orientation": "pass"})
        self.assertFalse(self.log.exists())

    def test_reject_nan_and_inf(self):
        for raw in ({"x": float("nan")}, {"x": float("inf")}):
            with self.assertRaises(LedgerError):
                writer.append("x", "y", raw, provenance_depth=1)
        self.assertFalse(self.log.exists())

    def test_reject_unknown_orientation(self):
        with self.assertRaises(LedgerError):
            writer.append("x", "y", {}, provenance_depth=1,
                          residual={"S": .2, "orientation": "unknown"})

    def test_concurrent_serialized_writers(self):
        def append_one(i):
            return writer.append("x", "tick", {"n": i}, provenance_depth=1)
        with ThreadPoolExecutor(max_workers=8) as executor:
            rows = list(executor.map(append_one, range(36)))
        self.assertEqual(sorted(x["seq"] for x in rows), list(range(36)))
        self.assertEqual(verify.verify(self.log)["entries"], 36)
        self.assertTrue(verify.verify(self.log)["ok"])

    def test_torn_line_rejected_and_no_append(self):
        self.put()
        with self.log.open("ab") as file:
            file.write(b'{"partial":')
        self.assertFalse(verify.verify(self.log)["ok"])
        before = self.log.read_bytes()
        with self.assertRaises(LedgerError):
            self.put()
        self.assertEqual(self.log.read_bytes(), before)

    def test_duplicate_key_rejected(self):
        with self.assertRaises(LedgerError):
            strict_loads(b'{"x":1,"x":2}')
        self.put()
        self.log.write_text(self.log.read_text().replace('"seq":0', '"seq":0,"seq":0'))
        self.assertFalse(verify.verify(self.log)["ok"])

    def test_symlink_forbidden(self):
        self.put()
        target = self.log.with_name("shadow.jsonl")
        self.log.rename(target)
        self.log.symlink_to(target)
        self.assertFalse(verify.verify(self.log)["ok"])
        with self.assertRaises(LedgerError):
            self.put()

    def test_oversized_line_rejected(self):
        with self.assertRaises(LedgerError):
            writer.append("x", "y", {"blob": "x" * 1_048_580}, provenance_depth=1)

    def test_legacy_digest_full_entry_minus_digest(self):
        entry = self.put()
        self.assertEqual(entry["digest"], record_digest({k: v for k, v in entry.items() if k != "digest"}))

    def test_giant_int_refuses_cleanly(self):
        with self.assertRaises(LedgerError):
            writer.append("x", "y", {}, provenance_depth=1,
                          residual={"S": 10 ** 400, "orientation": "pass"})
        self.assertFalse(self.log.exists())

    def test_depth_zero_with_human_root(self):
        entry = writer.append("x", "y", {}, human_root="operator-approved")
        self.assertEqual(entry["provenance_depth"], 0)
        self.assertTrue(verify.verify(self.log)["ok"])


if __name__ == "__main__":
    unittest.main()
