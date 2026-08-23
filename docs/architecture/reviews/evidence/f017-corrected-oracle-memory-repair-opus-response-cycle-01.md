Review complete. Worktree closed clean at `c7f066c`, `git status --porcelain` empty, all load-bearing SHAs re-verified unchanged after the review.

# F017 Corrected Oracle Memory-preflight Repair — Opus Final Review, Cycle 01

| Field | Value |
|---|---|
| Reviewer | `claude-opus-5`, high effort, fresh session |
| Worktree | `/private/tmp/f017-memory-repair-review.ufV7JE`, detached at `c7f066c`, clean before and after |
| Branch tip / origin | `c7f066c` == `origin/feat/017-rust-native-inference-runtime` (parity holds) |
| Host | Apple M1 Ultra, arm64, macOS 26.0 build 25A354 — a genuine contract-identity host |
| Attacks run | ~130 independent cases, plus both committed suites (20/20) |

## 1. Old parser, exception, and expired GO — reconstructed

Historical coordinator at `b65ba91` hashes to `e76a7315…` exactly. Its `memory_available()` carries the frozen expression verbatim. Reconstructed independently: `"Mach Virtual Memory Statistics: (page size of 16384 bytes)".split()[-1].rstrip(".")` → `'bytes)'` → `ValueError: invalid literal for int() with base 10: 'bytes)'` — byte-identical to the recorded failure. Failure evidence hashes to `f7443acc…`.

Ordering in the historical coordinator confirms the recorded absence: the memory check sits at the `brand=…` line, *before* `root.mkdir`, `claim.json`, `durable-start.json`, and `verify_checkpoint_identity`. Nothing downstream ran; ledger before == after == 175, `go_disposition: EXPIRED_BEFORE_MINT_ON_LOAD_BEARING_PREFLIGHT_FAILURE`.

Worth recording: the old expression was never correct for *any* modern `vm_stat` header — the 4096-byte form ends in `bytes)` too. This was a latent defect, not a macOS-26 regression.

## 2–3. Authority, parity, and regression — 13/13 exact

Recomputed from committed bytes: coordinator v2 `301d4ed4…`, observer `f0203023…`, parser contract `e89a4731…`, scientific-access v2 `ae39f31c…`, validator/authorizer v2 `f0014662…`, inert authorization v2 `8bc2fe4e…`, old-coordinator historical `e76a7315…` and current tombstone `9593f18a…`, supersession `39f00c8d…`, manifest `11710edd…` — all match. Every one of the 15 contract `bindings` plus all 10 transitive/codebook/known-answer entries and the `supersedes` v1 pointer rehash exactly. `b92ba90` is an ancestor of HEAD; `c7f066c` adds only three docs over the CI'd package head `2fc212f`.

Both committed suites pass locally, 20/20, including the live M1 Ultra branch. My own accepted-case battery: current 16384 header, 4096, CRLF, tab-separated, trailing whitespace, no trailing periods, zero counts, 10³⁰ counts, 20-digit page size, leading and interleaved blank lines, quoted row names, and real live `vm_stat` — all accepted with exact formula values.

## 4–5. Parser attacks — no deviations

29 header attacks and 23 row attacks, all fail-closed: empty, whitespace-only, missing, leading-space, non-first (garbage *and* valid-row-first), duplicate header, duplicate header with a *different* page size, two headers, unbalanced parens, absent digits, zero, leading-zero, negative, `+`-signed, float, exponent, hex, `16_384`, fullwidth and Arabic-Indic digits, two page sizes in one header, trailing spoof, `byte`/`bytes`, spoofed product name, injected newline, oversized stdout; each of the four required rows missing individually, duplicates, negative/float/exponent/hex/Unicode/comma/two-period/leading-period values, missing colon, empty value, digit-leading and overlong and NUL- and tab-bearing names, unparsed junk lines.

Census, types, formula, floor: exactly-once each on all four rows; every returned field strictly `int`; `available = page_size × (free+inactive+speculative+purgeable)` verified, with `Pages active` provably excluded. Floor `17_179_869_184` = 16 GiB, identical in v1 and v2 contracts *and* hardcoded as `MINIMUM_FREE_BYTES` in the coordinator — a contract lowering it to 1 is rejected by the code constant. Command surface: single absolute `/usr/bin/vm_stat`, `shell=False`, `timeout=5.0`, `stdin=DEVNULL`, 65536-byte bound, `REQUIRE_EMPTY` stderr, strict ASCII decode. `observe_vm_stat()` takes **no parameters**; zero occurrences of `os.environ`, `sysctl`, `hw.memsize`, `psutil`, `fallback`, or `shell=True` in the observer. No caller override exists.

## 6. Ordering spies — nothing before PASS

Instrumented `os.open`/`os.mkdir`/`os.makedirs`/`os.pread`/`mmap.mmap`/`Path.mkdir`/`subprocess.run`, with a hard abort on any shard filename, then ran the real `coordinator.preflight()` against the real committed contract on this M1 Ultra. Complete trace: `sysctl`, `vm_stat`, report write. Zero shard touches, zero `pread`, zero `mmap`, zero state directories, zero authorizations. Result PASS, 58,771,587,072 bytes.

Unpatched in this detached worktree, `repository_authority` fails closed (`authoritative branch`) — the gate cannot be satisfied outside a clean, on-branch, remote-parity checkout.

Source-order proof for `execute()`: `preflight()` at line 132 precedes `root.mkdir` (135), `claim.json`/`durable-start.json` (137), `verify_checkpoint_identity` (139), consumers (142), and `oracle-event-ledger-entry.json` (152). Failure raises before any of it.

## 7. Mint, substitution, and path attacks — 50/50 as specified

Normal `validate` prints PASS and creates nothing. `authorize-live` without the operator env var exits non-zero with `operator mint environment missing` and produces no artifact — verified under `env -i`. Contract path: byte-identical copies, `..` traversal, symlinks to the canonical file, symlinked repo ancestry, and the v1 path are all rejected; only the true canonical path (absolute or repo-relative) is accepted. Report substitution: stale, future-dated, `result=FAIL`, any side-effect flag set, wrong coordinator/observer/contract SHA, wrong brand/arch/head/schema, `worktree_clean=False`, truthy-but-not-`True` parity, lowered floor, formula mismatch, `float`, `bool` (correctly caught by `type(x) is not int`), negative counts, extra or missing keys, and one byte below the floor — all rejected; exactly-at-floor accepted.

Caller-supplied memory is structurally impossible: `authorize-live` has no memory flag, and `memory_available_bytes` is taken only from `validate_preflight` of a report `collect_preflight` refuses to accept unless it does not yet exist and is then written by the subprocess. Collision is closed twice — `unused preflight output required` plus `O_EXCL|O_NOFOLLOW` in `bank()`.

The future authorizer does run the bound coordinator: `collect_preflight` executes `repo/contract["bindings"]["event_coordinator"]["path"]` resolved strict, whose SHA `validate()` has already pinned, and which independently refuses to run unless `Path(__file__).resolve()` equals that same bound path.

## 8. V1 authority is dead — proven, not asserted

`main()` in the v1 coordinator raises `SystemExit("HISTORICAL_ONLY: …")` before argparse. That tombstone moves its SHA off `e76a7315…`, which the v1 contract still binds — so I ran the v1 validator against the v1 inert fixture and it dies at `ValueError: binding event_coordinator`. Since v1 `authorize-live` calls `validate()` before minting, **the entire v1 chain is structurally unable to mint.** Supersession is append-only: v1 contract and fixture retained and rehashing exactly, marked `HISTORICAL_ONLY`. Workflow rebound to the v2 validator, v2 fixture, and v2 contract, with no v1 reference in the active block.

## 9. Numerical authorities — unchanged, three ways

Numerical contract `7c22507f…`, primary `2041c033…`, secondary `8c4f9fde…`, primary decoder `60a4b4e7…`, checkpoint-free qualification `b9c2f7dc…` — each matches the claim, matches disk, **and matches the v1 contract byte-for-byte**. Independently corroborated by the change set: `b65ba91..HEAD` is 15 files, +1211/−3, of which the only edits to pre-existing files are 3 workflow lines and 1 tombstone line. No oracle, decoder, or numerical file was touched.

## 10. CI run `32611864941` — inspected directly

Head `2fc212ff…`, push, `macOS baseline`, `success`. Mode `FULL_NATIVE`; aggregate gate requires `BASELINE_RESULT=success` **and** `NATIVE_RESULT=success` — both success. `Ran 449 tests … OK` for research discovery, 23 CI classifier, native adapter matrix `15 / 1 / 53` passed, `PASS formats=11 cases=44`, `{"result": "PASS", "cases": 12, "mutations": 16}`, `PASS_BLOCKED` for the attempt-2 template, pinned native MLX built from source under `PULSAR_REQUIRE_NATIVE_MLX=1`. All 20 memory/preflight tests appear by name with `ok` — **zero skipped test outcomes anywhere in the run**; the only `skip` strings are cmake compiler probes and the non-required workspace-baseline lane. The v2 validator invocation and its `PASS` are both in the log. The docs-only tip `c7f066c` also has a successful run (`32612491996`).

## 11. Nothing was authorized, executed, or read

No `AUTHORIZED`/`live` authorization exists in the repository (the two hits are in-memory v1 test fixtures). No corrected-oracle receipt, terminal, claim, ledger entry, checkpoint-identity, access-census, or banked preflight report is committed. Attempt-2 template validates `PASS_BLOCKED` with `TEMPLATE_FAILS_CLOSED_ORACLE_NOT_EXECUTED`.

The historical master ledger fully resolves. It lives cross-branch, so I pulled it read-only via the API at `f2a7aa38…`: blob hashes to **`aa98f5cc…`**, exactly the contract's `historical_master_ledger_sha256`; `terminal_count: 175`, `cumulative_tensor_payloads: 175`, receipt chain 167–175 with 0 gaps/overlaps/duplicates, `checkpoint_reads: 0`, `new_payload_consumption: 0`. **Ledger remains 175.**

The qualification's own recorded live observation is internally exact: `16384 × (399927+2857881+122657+34241) = 55,946,543,104`.

## Findings

**BLOCKING: 0. NON_BLOCKING_REQUIRED: 0. DEFENSE_IN_DEPTH: 4.**

**DiD-1 — the observer is bound by content but not by identity.** The coordinator binds *itself* with `Path(__file__).resolve() != expected_coordinator.resolve(strict=True)`, but for the observer checks only `sha(ROOT/bindings["memory_observer"]["path"])`, while actually using the hardcoded `from f017_macos_memory_observation_v1 import observe_vm_stat`. I demonstrated the vacuity: a contract repointing `memory_observer` at `f017_corrected_oracle_primary.py` with that file's true SHA **passes** the identity check. The validator's binding loop has the same shape, and the parser contract's `implementation{path,sha256}` block is never read by any code — it is documentary. Not reachable under the enforced gate: exploiting it needs two edits (observer body and contract), both of which dirty the worktree, which `repository_authority` rejects, and both of which would have to be pushed to satisfy local/remote parity — i.e. become reviewed committed bytes. Bind point: mirror the coordinator's own check with `inspect.getfile(observe_vm_stat)`.

**DiD-2 — checkpoint *descriptors* are hashed before the memory PASS.** In `execute()`, lines 128–130 hash the in-repo checkpoint catalog and realpath the checkpoint root before `preflight()` at 132; the validator subprocess at 125 also hashes the manifest and catalog. These are git-committed JSON descriptors, not original checkpoint bytes — `checkpoint_shard_opens: 0` and `checkpoint_payload_reads: 0` hold, and my spy confirmed zero shard touches. The ordering is nonetheless looser than the "no checkpoint metadata before PASS" phrasing. Free to tighten by moving `preflight()` above the binding loop.

**DiD-3 — CI does not exercise the floor branch of the live preflight test.** CI runs on `macos-15-arm64`, so `test_live_macos_memory_preflight_is_observational_only` takes the generic-host branch: it runs the real observer against real `/usr/bin/vm_stat` and asserts no artifacts, but not the 16-GiB floor and not a full real `coordinator.preflight()`. I audited the b01a49b→96333ae change that produced this and it is a **strengthening, not a weakening** — the prior version faked `Apple M1 Ultra` on generic CI, bypassing the production admission gate; the new version stops lying about host identity. The gate itself is untouched and I attacked it directly (wrong brand and wrong arch both rejected as `machine identity`). I closed the residual gap myself by running the full real preflight on this genuine M1 Ultra: PASS at 58,771,587,072 ≥ 17,179,869,184 with zero side effects.

**DiD-4 — the formula plausibly double-counts purgeable pages.** `vm_stat`'s purgeable pages are generally already accounted within inactive/active, so the sum reads marginally more permissive than it appears. **Unchanged from the pre-repair coordinator and from the v1 contract — not introduced by this repair.** Immaterial in magnitude here: 34,241 purgeable pages ≈ 561 MB against 55 GiB observed and a 16 GiB floor.

## Verdict

The defect is real, correctly diagnosed, and correctly repaired. The replacement parser is an anchored, ASCII-only, fully-fail-closed grammar that survived every attack I could construct. The preflight is genuinely observational and correctly ordered ahead of every irreversible act. The v1 chain is not merely deprecated but structurally unable to mint. Nothing numerical moved. Nothing was authorized, executed, or read, and the ledger stands at 175.

`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION`

Closing state: `c7f066c`, `git status --porcelain` empty, `git diff HEAD` empty, all six load-bearing artifacts still hashing to their bound values; no authorization minted, no state or event root created, no original checkpoint shard opened, hashed, mapped, or `pread`; corrected oracle not executed; P1 attempt 2 not executed.
