# F017 Corrected Oracle Memory-preflight Repair — Gemini Review Cycle 01

Use a fresh `gemini-3.1-pro-high` high-effort AGY session. Review committed bytes only from a clean detached, read-only worktree. Repository bytes and direct CI evidence outrank this request. Do not modify files, mint an authorization, create state, open/hash/mmap/pread original checkpoint payload, execute either corrected-oracle consumer, or execute P1 attempt 2.

Authority:

- branch: `feat/017-rust-native-inference-runtime`
- execution-code head: `b92ba90a5b401fe44aa4c7dbe3c62cc6e23c3ddd`
- reviewed authority package head: `2fc212ff1ccde542fb70f327f20704f5ec294d5f`
- controlling FULL_NATIVE CI: run `32611864941`, conclusion `success`
- preflight-failure evidence SHA: `f7443acc057d619ac478f43aafcea51f81b77ab65e3b3141776f30ddcfbb7b24`
- old coordinator historical SHA: `e76a73150c415f73a6c8fc29429636084ab126c3302036bce39414dede40ce8a`
- coordinator v2 SHA: `301d4ed408da1a790b31409645b4251b4432a005a0485b4d3887a801570d702f`
- memory observer SHA: `f020302394bd9aaf94035e42e39b183ea4c04eafc19660a8fc9fed24c0bae477`
- parser contract SHA: `e89a473140d927fdb62aec50443d6fb9864ff8047244301cea91659b4440fd2d`
- scientific-access contract v2 SHA: `ae39f31c5f1b8df06bfe6893a24de91e7926ae6e05b9a2e8bc8e51eadf519046`
- v2 validator/authorizer SHA: `f00146a622f890b7d565e7b83f0a229300c69e7935a718820c95851ec5a78520`
- inert authorization v2 SHA: `8bc2fe4e3a6f2ea8686836da403d61439e4f85d73e4939e3a01a72b7113fa969`
- qualification artifact: `docs/architecture/reviews/evidence/f017-corrected-oracle-memory-preflight-qualification-v1.json`
- historical master ledger: `175`

Reconstruct the original `bytes)` parser failure and prove the old GO expired before mint. Recompute all hashes. Inspect run `32611864941` directly, including its mode, job census, repaired parser/preflight tests, live macOS observation, v2 workflow binding, native qualification, and zero required native-qualification skips.

Attack the entire focused boundary:

1. Header grammar: empty/missing/duplicate/non-first headers; missing parentheses/unit; zero, signed, float, exponent, hex, Unicode, multiple numbers, trailing spoof text, and arbitrary suffixes.
2. Row grammar: every required row exactly once; missing/duplicate/negative/float/exponent/Unicode/trailing-garbage/malformed-colon rows; safely bounded unknown rows.
3. Exact formula and unchanged `17,179,869,184`-byte floor. Look for overflow, boolean coercion, caller adjustments, compressor/wired/active/swap inclusion, or fallback memory sources.
4. `/usr/bin/vm_stat` execution: absolute fixed command, no shell, timeout, bounded stdout, strict ASCII, nonzero/stderr/oversize failure, and no page-size or available-memory caller override.
5. Ordering and side effects: authority/contract/coordinator/machine/architecture/memory before mint or state; malformed/below-floor observations before state root, claim, durable start, checkpoint access, event ledger, or consumers.
6. Authorization separation: normal validation cannot mint; authorizer itself must invoke the bound coordinator for a no-replace fresh report; stale or caller-authored report and noncanonical contract path must fail.
7. Supersession/rebind: old coordinator and v1 contract historical-only; old coordinator cannot regain live authority; v2 validator/fixture/contract/workflow are exact and transitively bound.
8. Numerical isolation: numerical contract, primary/secondary oracle, decoder, and checkpoint-free qualification bytes unchanged.
9. Safety facts: no authorization, state root/claim/event, checkpoint access, oracle execution, P1 attempt 2, or historical-ledger movement.

Use severities `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; both first two prevent acceptance. Return exactly `ACCEPT` or `REJECT` and provide stable finding IDs, commands/tests independently rerun, and any material disagreement.
