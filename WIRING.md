# Wiring notes (Harbor audit follow-through, 2026-11-15)

`ci/verify.yml` is a complete GitHub Actions workflow that runs this repo's
own `verify.py` against the shipped `history.jsonl` on every push and PR.

It is staged under `ci/` because the Muse GitHub App integration does not
hold GitHub's `workflows` permission, so it cannot write into
`.github/workflows/` directly (both the contents API and the git-trees API
return 403 for that path). To activate:

    mkdir -p .github/workflows && git mv ci/verify.yml .github/workflows/verify.yml

(or move it in the GitHub web UI) and commit. One move, no edits needed.

Expected first result: RED. As shipped, `history.jsonl` seq 0 fails
verification ("digest mismatch") — that is the finding this wiring exists to
catch automatically. Repair or re-issue the ledger entry and the check goes
green; from then on, any edit-after-hash or chain break fails CI instead of
passing silently.
