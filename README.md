# attested-history

A local append-only, hash-chained JSONL ledger for cross-repository evidence **indexing**. This implementation checks record integrity but does **not** authenticate the producer or independently prove the claimed provenance depth. Cryptographic signatures, trusted commit anchoring and source receipt verification belong to a separate trusted verifier.

## Potential source systems (integration contracts are not enabled by this file)

- [swarm-vm-runner](https://github.com/doitupsolutions810-crow/swarm-vm-runner) — coordinator/worker receipts
- [TrainLLM](https://github.com/doitupsolutions810-crow/TrainLLM) — previously signed action envelopes
- [control12-lattice-ops](https://github.com/doitupsolutions810-crow/control12-lattice-ops) — attestation and control events
- [capability-plane](https://github.com/doitupsolutions810-crow/capability-plane) — attestation event bus
- [trinity-core](https://github.com/doitupsolutions810-crow/trinity-core) / [Avrone](https://github.com/doitupsolutions810-crow/Avrone) — orchestration events

No direct import of these sources occurs automatically.

## v1 entry contract

Each record is an exact JSON object containing `seq`, `ts`, `source`, `kind`, `digest`, `provenance_depth`, `residual`, `capability_id`, `human_root`, `raw`, and `prev_hash`. `raw` must be an object. `seq` starts at zero and increments by one.

- `digest = SHA256(json.dumps(record **without digest**, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False))` (UTF-8). This is the historical writer's *actual* full-record digest. Previous documentation incorrectly described it as a digest of `raw` alone.
- `prev_hash` equals the **previous record digest**, or `null` for the first record.
- `provenance_depth` is a claimed nonnegative integer and is admitted only when it is at least one or `human_root` is a nonempty string. The verifier checks structure, **not** the truth of ancestry.
- If a `residual` is present, its `orientation` must be `pass`, `fail`, `mixed`, or `unmeasured`. Its `S` is `null` only when orientation is `unmeasured`; measured `S` must be finite in [0, 0.25].
- Entries are capped at 1 MiB; invalid UTF-8, duplicate JSON keys, NaN/Infinity, oversized lines, noncontiguous sequence numbers, broken links, and torn final lines are refused.
- A writer holds a POSIX `flock` sidecar lock across verification and append and syncs the appended data with `fsync`. A damaged ledger must be inspected/recovered explicitly, not silently repaired or truncated.

## Commands

```bash
python3 writer.py --source great-scale --kind measurement --raw '{"claim":"test"}' --depth 1 --S 0.125 --orientation mixed
python3 verify.py
python3 -m unittest discover -s tests -v
```

The verifier exits nonzero on corruption and returns JSON with `ok`, `verified` (false for an empty ledger), and `cryptographically_authenticated:false`. **A clean digest chain is not a signed execution receipt.** A consumer must verify source identity, authorization, operation idempotency and completion status separately before treating a claim as production evidence.

## Further integration gate

Reconcile exact operation ID + canonical request digest + signed completion receipt before ingesting cross-repository execution evidence. A queued Swarm receipt, a capability grant, and a numerical Great Scale result are three different evidence types; none alone establishes completed execution. Future v2 work should bind records to independent signer keys and externally anchored chain heads without retroactively relabeling v1 history as authenticated.
