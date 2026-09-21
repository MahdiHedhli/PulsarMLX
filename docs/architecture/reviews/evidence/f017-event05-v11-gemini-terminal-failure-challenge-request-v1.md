# F017 Event 05 V11 terminal-failure CHALLENGE review

Review the exact committed bytes at the request-bearing head. Use `gemini-3.1-pro-high` at high effort, read-only. Do not access original checkpoint shards and do not alter the repository.

Event 05 is terminal and must not be retried. Challenge whether the committed evidence truthfully proves: fresh approval and IDs; exact candidate/install identity; package durable start exactly once; accounting root binding; failure at `CHECKPOINT_IDENTITY_START`; exact exception `ValueError("checkpoint identity producer authority")`; static root cause in measured `f017_checkpoint_identity_producer_v10.py`; zero shard opens, identity reads, payload reads, primary starts, secondary starts, and live leases; package accounting delta one; historical ledger 175; complete failure capsule and package terminal; EVIDENCE_ONLY run 33071927245 with zero native jobs; no P1 attempt 2.

Attack fabricated accounting, missing durable artifacts, altered SHAs, hidden shard access, hidden consumer execution, replay authority, and any inference that the event may be retried. Emit structured challenge rows only, each with claim, attack, observed evidence, severity, and disposition. Finish with exactly one verdict: `NO_UNRESOLVED_MATERIAL_CHALLENGE` or `MATERIAL_CHALLENGE_OPEN`.

Primary packet: `f017-event05-v11-terminal-failure-authority-manifest-v3.json`, `f017-event05-v11-terminal-execution-failure-v2.json`, terminal package v2, graph state v10, claim ledger v8, and terminal-failure EVIDENCE_ONLY CI v3.
