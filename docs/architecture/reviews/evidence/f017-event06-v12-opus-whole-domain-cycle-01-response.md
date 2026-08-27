# Claude Opus 5 — F017 Event 06 V12 whole-domain ARBITER cycle 1

Reviewed exact committed head `b26ae20167041ccebaf6d447083de92f47a3e40a` and tree `4860ea04663b58b3ecbdd7dfdb229309772d8e9e` in a fresh detached read-only clone.

Opus independently verified the measured implementation head/tree, 31/31 measured and historical hashes, 15/15 manifest bindings, Event 05 failure reconstruction, typed scope model, event-number capability exclusion, six-shard synthetic hashing, deterministic evidence closure, historical byte immutability, exact-head FULL_NATIVE run, original checkpoint access zero, Event 06 unexecuted, and P1 attempt 2 absent.

Opus rejected three claims and left one unresolved:

- `C-SCOPE-002`: installed authority could substitute package/event/checkpoint bindings while retaining only the candidate digest pointer.
- `C-VALIDATE-002`: installed authorization was not compared field-for-field with the exact approved candidate.
- `C-FAIL-003`: capability drift and producer-measurement drift were modeled but lacked live raise sites; the capability validator could emit a bare generic error.
- `C-GO-001`: unresolved pending final readiness bytes.

It accepted the other twelve claims. Earliest invalidated node was `R7`. It also required reconciliation of the modeled failure transition vocabulary, committed corroboration for evidence-only CI, and append-only review-ledger cleanup.

Counts:

- blocking findings: 2
- non-blocking-required findings: 3
- unresolved claims: 1
- accepted claims: 12
- rejected claims: 3

Global verdict: `REJECT`.
