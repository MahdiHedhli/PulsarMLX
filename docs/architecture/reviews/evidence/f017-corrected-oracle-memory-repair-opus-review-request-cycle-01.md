# F017 Corrected Oracle Memory-preflight Repair — Opus Final Review Cycle 01

You are the final independent adversarial reviewer. Use `claude-opus-5`, high effort, in a fresh session. Review committed bytes only from a clean detached, read-only worktree. Repository bytes and direct CI evidence outrank this request. Do not modify files, mint an authorization, create an event/state root, open/hash/mmap/pread original checkpoint payload, execute the corrected oracle, or execute P1 attempt 2.

Authority:

- branch: `feat/017-rust-native-inference-runtime`
- execution-code head: `b92ba90a5b401fe44aa4c7dbe3c62cc6e23c3ddd`
- reviewed authority package head: `2fc212ff1ccde542fb70f327f20704f5ec294d5f`
- controlling FULL_NATIVE CI: run `32611864941`, conclusion `success`
- historical ledger: `175`
- failure evidence SHA: `f7443acc057d619ac478f43aafcea51f81b77ab65e3b3141776f30ddcfbb7b24`
- old coordinator historical SHA: `e76a73150c415f73a6c8fc29429636084ab126c3302036bce39414dede40ce8a`
- coordinator v2 SHA: `301d4ed408da1a790b31409645b4251b4432a005a0485b4d3887a801570d702f`
- memory observer SHA: `f020302394bd9aaf94035e42e39b183ea4c04eafc19660a8fc9fed24c0bae477`
- parser contract SHA: `e89a473140d927fdb62aec50443d6fb9864ff8047244301cea91659b4440fd2d`
- scientific-access v2 SHA: `ae39f31c5f1b8df06bfe6893a24de91e7926ae6e05b9a2e8bc8e51eadf519046`
- validator/authorizer v2 SHA: `f00146a622f890b7d565e7b83f0a229300c69e7935a718820c95851ec5a78520`
- inert authorization v2 SHA: `8bc2fe4e3a6f2ea8686836da403d61439e4f85d73e4939e3a01a72b7113fa969`
- qualification: `docs/architecture/reviews/evidence/f017-corrected-oracle-memory-preflight-qualification-v1.json`

Independently perform all required attacks, not a prose review:

1. Reconstruct the old positional parser, accepted header, `bytes)` token, exception, absence of mint/state/access, and expired GO.
2. Recompute every load-bearing SHA and verify exact execution-code/package authority and parity model.
3. Rerun the exact current-header regression and accepted 4096/CRLF/whitespace/period/zero/large/live cases.
4. Attack empty/missing/duplicate/non-first/malformed/spoofed headers; zero/signed/float/exponent/hex/Unicode/multiple page sizes; and every malformed-row class.
5. Verify exact required-row census, strict integer types, formula, unchanged 16-GiB floor, command timeout/output bound/no-shell/absolute path, and no fallback or caller override.
6. Attack preflight ordering with spies: no auth, root, claim, durable start, checkpoint metadata/payload open/hash/map, ledger, or consumer before PASS.
7. Attack normal-validation minting, stale/hand-authored report substitution, caller-supplied memory, alternate contract path, contract symlink ancestry, and report collision. Confirm the future authorizer itself runs the bound coordinator.
8. Verify old coordinator/v1 authority is historical-only and unreachable for current live authority; verify v2 contract/fixture/validator/workflow rebind and append-only supersession.
9. Recompute unchanged numerical-methodology, primary, secondary, decoder, and checkpoint-free qualification SHAs.
10. Inspect FULL_NATIVE run `32611864941` directly: 449 research tests, live macOS observer, exact v2 workflow validation, workspace baseline, pinned native job, no required native qualification skips, and aggregate success.
11. Verify no scientific authorization/event/P1 attempt 2/checkpoint access occurred and ledger remains 175.

Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; both first two prevent acceptance. Return exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION` or `REJECT`. No conditional acceptance.
