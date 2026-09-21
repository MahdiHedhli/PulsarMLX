# F017 Event 05 V11 terminal-failure ARBITER review

Use `claude-opus-5`, high effort, fresh detached read-only worktree, committed bytes only. Do not access original checkpoint shards and do not modify files.

Independently reconstruct the fresh approval, candidate, installation, package durable start, accounting-root binding, transition journal, failure capsule, and package terminal. Verify the exact failure at `CHECKPOINT_IDENTITY_START`, the `ValueError("checkpoint identity producer authority")`, and the static measured-code cause: V11 coordinator supplies `PRODUCTION_EVENT_05`, while measured V10 identity producer admits only synthetic or `PRODUCTION_EVENT_04`.

Attack candidate/install mismatch, altered SHA closure, fabricated accounting, root substitution, hidden shard opens or reads, hidden primary/secondary execution, descriptor leakage, retry/resume authority, EVIDENCE_ONLY CI mismatch, historical-ledger drift, and hidden P1 authority.

Return a verdict for every claim in execution claim ledger v8 using `ACCEPT`, `REJECT`, or `UNRESOLVED`. Claims invalidated by the terminal failure must not be converted to ACCEPT. Because `E-IDENTITY-001` failed and no oracle completed, the global execution-evidence verdict must be exactly `REJECT`; independently state whether the terminal failure evidence is truthful and complete. Report blocking, non-blocking-required, and unresolved counts. No conditional acceptance and no execution rerun.

Review target is the exact request-bearing Git head. Primary packet: terminal-failure authority manifest v3, terminal package v2, terminal execution failure v2, EVIDENCE_ONLY CI v3, Gemini cycle-01 result, graph state v11, claim ledger v8, challenge ledger v3, and support ledger v3.
