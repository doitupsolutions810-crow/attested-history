# SYSTEM_ACCESS

Self-readable entry point on the default branch for the attested-history cross-repo receipt index.

## Role in the compile

attested-history is the single append-only log that turns twenty-six repos into one attested history. Born private — the one repo that was never public.

## Schema

Each entry: residual (S, orientation, cone status), provenance (who measured, from where, with what prior, parent pointer), trust score (provenance depth / (1 + S)), source repo, source layer, timestamp, signature.

## Writers

- swarm-vm-runner's prove-success.sh
- control12-workspace's workspace-attestor
- TrainLLM's chained envelopes
- capability-authority's AttestPipe
- Avrone's ledger_bridge.py (forwards trinity-core's events.jsonl)
- Avrone's swarm_bridge.py (ADMITTED intents as swarm jobs)
- avrone-daemon's capgate_head_attest.py (forwards capgate's signed head — count, head hash, verify_chain walk — as capgate_head entries)

## Verification

`verify` pass checks: zero bad digests, corrupt lines named unmeasured, model-only ingest rejected, unnamed unmeasured rejected, chain integrity.

## Invariants

- Append-only. No deletion, no rewrite.
- Every entry carries provenance; unprovenanced entries are unmeasured.
- Trust ranking: deeper provenance wins conflicts.
- Poisoned chains rejected on structure.

This file is the index's self-memory. It is the floor the whole compile hangs from.
