# attested-history

One append-only log binding every receipt across the compile under a single provenance schema.

## Sources

- swarm-vm-runner/ledger/ — dated chained SHA-256 success proofs
- TrainLLM action log — previousHash-linked ed25519 envelopes
- CONTROL12 attestation ledger — v5 INTENT..LEARN steps
- capability-plane attestpipe bus — sole side-effect path receipts
- trinity-core /tmp/trinity-ledger/events.jsonl — forwarded via Avrone ledger_bridge.py

## Schema

Each entry:

```json
{
  "seq": 0,
  "ts": 0.0,
  "source": "swarm-vm-runner",
  "kind": "success_proof",
  "digest": "<sha256 of canonical payload>",
  "provenance_depth": 1,
  "residual": {"S": 0.0, "orientation": "pass", "cone": false},
  "capability_id": null,
  "human_root": null,
  "raw": {},
  "prev_hash": null
}
```

## Invariants

1. Append-only. No update, no delete. Corrections are new entries referencing the bad seq.
2. Digest covers the canonical JSON of raw, sort_keys, no spaces.
3. prev_hash chains to the digest of the prior entry. First entry prev_hash is null.
4. provenance_depth is strictly the count of human-or-measured ancestors walkable from this entry. A model-only chain cannot exceed depth 0 and is rejected at ingest.
5. Entries with residual.S == null and orientation != "unmeasured" are rejected — unmeasured must be named, never implied.

## Verify

`python verify.py` walks the log, checks every digest and chain link, and reports the deepest provenance chain and the hottest residual. Exit 1 on any invariant break.
