# F017 Lifecycle V6 Gemini Design Review Cycle 04

Use a fresh `gemini-3.1-pro-high` AGY session at high effort. Review exact committed bytes at `bb15fe27202410aed9842b6b18a8bdb974694949`; repository bytes outrank this request. Do not modify files, access original checkpoint shards, mint or execute Event 04, run a real oracle, or execute P1 attempt 2.

This cycle repairs Opus cycle-03 NBR-1 and NBR-2. Independently verify that authorization candidate validation now reads and SHA-validates every load-bearing authority path before install, including both capability reports; that synthetic qualification no longer substitutes all-zero authority hashes; that synthetic checkpoint roots are structurally isolated; and that the workflow invokes the separately written independent lifecycle checker.

Attack the exact serialization boundary. Verify that every finite float in lifecycle authorities and numerical-result evidence uses one lowercase IEEE-754 binary64 hexadecimal string representation, nonfinite values fail closed, consumers decode only at numerical edges, and the active wrapper does not bank the pure-core compatibility `result_sha256` computed over a different serialization. Check complete result, logits, top-32 values/bits, comparison metrics, receipts, terminals, and SHA/readback behavior.

Also re-audit the full lifecycle V6 design: state/transition reachability, event accounting, conditional unstarted-consumer obligations, path timing, candidate/install identity, authority activation, complete registry/matrix/model byte anchoring, exact semantic-column checking, independent-validator import separation, numerical-contract-v3 binding, tombstones, zero original-checkpoint access, and absence of Event-04 or P1 authority.

Classify findings as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`. Return exactly one advisory verdict: `ACCEPT` or `REJECT`. A material concern must identify exact committed paths and a reproducible failure or contradiction.
