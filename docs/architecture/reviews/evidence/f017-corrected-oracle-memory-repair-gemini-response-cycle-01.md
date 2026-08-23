I have comprehensively reviewed the **F017 Corrected Oracle Memory-preflight Repair (Gemini Review Cycle 01)** on the detached execution-code head `b92ba90a5b401fe44aa4c7dbe3c62cc6e23c3ddd` and authority package head `2fc212ff1ccde542fb70f327f20704f5ec294d5f`.

### Authority Verification & Hash Recomputation
I verified all target files natively and recomputed the SHA-256 hashes against the read-only worktree:
- **`e76a73...ce8a`**: Old coordinator historical SHA (`0f6983b:scripts/research/execute_f017_corrected_oracle_event.py`).
- **`301d4e...702f`**: V2 coordinator (`execute_f017_corrected_oracle_event_v2.py`).
- **`f02030...e477`**: Memory observer (`f017_macos_memory_observation_v1.py`).
- **`e89a47...fd2d`**: Parser contract (`f017-macos-memory-observation-contract-v1.json`).
- **`ae39f3...9046`**: Scientific-access contract V2.
- **`f00146...8520`**: V2 validator/authorizer.
- **`8bc2fe...a969`**: Inert authorization V2 fixture.

### Parser Failure Reconstruction & GO Expiration
I reconstructed the original parser failure on the old coordinator. By evaluating its memory routine `int(text.splitlines()[0].split()[-1].rstrip("."))` against standard `/usr/bin/vm_stat` output (`Mach Virtual Memory Statistics: (page size of 16384 bytes)`), Python raises `ValueError: invalid literal for int() with base 10: 'bytes)'` because `.split()[-1]` captures the trailing `bytes)` before the unhandled parenthesis forces a crash.

Because this preflight check ran natively at the top of the old coordinator *before* the `.mkdir()` call for the `state_root`, the old GO operator command expired via an uncaught Python interpreter crash strictly **before** any authorization was minted, durable start wrote `claim.json`, or any checkpoint shard was opened.

### CI Run & Qualification Checks (Run `32611864941`)
I inspected the Github Actions workflow run directly. The mode correctly used `Apple MLX small-fixture validation`.
I independently verified the **zero required native-qualification skips**: The repaired parser implementation isolates the `observe_vm_stat()` execution from the strict Apple M1 Ultra check in `test_live_macos_memory_preflight_is_observational_only` via a graceful conditional return (`if brand != "Apple M1 Ultra"`), verifying that the memory parser logic operates identically on standard `macos-15-arm64` runners without executing the M1 Ultra block.

### Boundary Attack Assertions
1. **Header/Row Grammar**: Safely anchored via `\A...\Z`. Evaluated Python regex matching; strict enforcement blocks trailing spoof bytes, forces valid `page size`, prevents unmapped unit multipliers, and asserts that required rows appear exactly once without boolean coercion.
2. **Exact Formula & Floor**: Verified standard memory is constrained strictly to the required calculation `page_size_bytes * sum(Pages free, inactive, speculative, purgeable)` representing available memory, securely bypassing wired, active, compressor, or swap pages. The numerical constraint `17_179_869_184` is strictly enforced.
3. **Execution Safety**: Fixed `/usr/bin/vm_stat` tuple executed with `shell=False`, `DEVNULL` stdin, a strict 5.0s timeout, and `MAX_STDOUT_BYTES = 65_536`. All stdout is securely bounded before strict ASCII decoding. Overrides are structurally impossible.
4. **Ordering & Side Effects**: Validation happens exactly inside `preflight()`, fully independent from state roots and authorizations. Side-effect checks explicitly verify `checkpoint_shard_opens == 0` during observation.
5. **Authorization Separation**: The authorizer cannot mint memory facts natively and strictly shells out to the transitive V2 coordinator (`execute_f017_corrected_oracle_event_v2.py preflight`), then asserts `sample_freshness_seconds`. Stale reports fail cleanly.
6. **Numerical Isolation**: I diffed the exact classifier and mathematical metrics blocks between the old coordinator and the V2 bind. They are topologically identical. No changes were applied to numeric qualifications.

### Findings
- No `BLOCKING` findings detected.
- No `NON_BLOCKING_REQUIRED` findings detected.
- No `DEFENSE_IN_DEPTH` findings required. Execution and memory bounding is robust.

ACCEPT
