# Ledger integrity hold — 2026-11-06

## Observed state

The current main branch contains history.jsonl (Git blob 82951f020ec64e179af6bca5dbc8498bb220d647) with one genesis entry:

- recorded entry digest: 7a9e2b07d7e9cdd226a207c487e9caf34f30c86bac34ef9fd14688ce5bb30a17
- digest recomputed from the checked-in entry using the checked-in canonicalization rule (json.dumps(sort_keys=True, separators=(",", ":")), excluding digest): 70377ae5544bfbfc42bcf17c77857cb231db70ecd86b84accfec5e324adca483
- result: **mismatch**.

The entry parses as JSON and has seq=0, prev_hash=null, and provenance_depth=1. Its digest does not reproduce. The cause of the mismatch is not established; do not infer whether it arose during authoring, serialization, or transfer.

The current verify.py also returns exit code 0 when history.jsonl is missing or empty. Those are separate defects:

1. a populated but non-reproducible entry must be HOLD;
2. missing or empty evidence must also be HOLD, never VERIFIED.

## Safe handling

- Do not edit the existing entry or rewrite the history in place.
- Preserve the current history.jsonl bytes and Git blob identity as the legacy evidence artifact.
- A migration, if approved, should create a new genesis record that explicitly references the legacy blob SHA, recorded digest, recomputed digest, and HOLD reason. The new chain must not claim that the legacy entry verified.
- Only an independent successful verification of the new non-empty chain may change its state to VERIFIED.
- The existing writer.py and AVRONE capgate_head_attest.py integration must be tested together after the migration contract is agreed.

## Proposed verifier contract

- Exit 2 / HOLD: missing, empty, unreadable, non-regular, symlinked, FIFO, or oversized history.
- Exit 1 / HOLD: malformed schema, non-contiguous sequence, invalid provenance, digest mismatch, broken chain, or invalid residual.
- Exit 0 / VERIFIED: non-empty history where every entry is valid, canonical, contiguous, provenance-qualified, and hash-linked.

The implementation in this branch is read-only. It does not modify the ledger or writer.