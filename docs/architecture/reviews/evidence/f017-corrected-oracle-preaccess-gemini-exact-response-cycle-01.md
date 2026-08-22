# F017 Corrected Full-Checkpoint Oracle Preaccess Cross-Vendor Review

**Reviewer Model**: Gemini 3.1 Pro (High)
**Target Head**: `b9607b1e7bd2d9b58b849b9df9ecd5d810efcca8`

## Zero-Execution Attestation
- **Original checkpoint reads during review:** 0
- **Corrected target-oracle executions:** 0
- **P1 attempt-2 executions:** 0
- **Live authorizations created:** 0

All review steps were performed entirely offline via direct static analysis of the codebase and exact-head CI logs (`run 32600160665`). Recomputation of load-bearing file hashes (including the attempt-1 offline closeout, historical ledger SHA `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`, and terminal `175`) confirms that these constraints are safely banked and mathematically unchangeable.

Target observations `21615` and `17351` were verified to be disclosures only; `qualify_f017_corrected_oracles.py` strictly quarantines them via an explicit text scan that guarantees no implementation leakage. Attempt 2 template is proven non-executable (`executable_authority: false` and blocked by `REJECT_UNTIL_CORRECTED_ORACLE_EVENT_RESULT...`). CI routing enforces `FULL_NATIVE` properly, correctly bypassing the Apple MLX jobs on evidence-only paths, and safely defaults unknown states to full coverage.

## Findings and Verdict

**F017-Q-MUTATION-FAKE** (`BLOCKING`)
- **Path/symbol**: `scripts/research/qualify_f017_corrected_oracles.py:mutate`
- **Evidence**: The synthetic qualification intercepts `Q6_K_LANE`, `IQ3_XXS_LANE`, `QK_TRANSPOSE`, `TENSOR_OFFSET`, `QUANT_TYPE_ID`, and `ACCUMULATION_PRECISION` and alters `token_embd.weight` instead of applying the named structural mutation.
- **Failure mode**: Fake mutation labels. The test harness declares successful coverage of these quant formats and routing paths but silently bypasses their actual logic by arbitrarily fuzzing the embedding token to pass the equality gate. Unexercised quant formats are masked.
- **Smallest repair**: Apply bit-exact structural mutations for packed blocks and precision variables to genuinely exercise the decoders.

**F017-GRAPH-SIMPLIFIED** (`BLOCKING`)
- **Path/symbol**: `crates/f017-native/src/model.rs:390-408` (and Python `oracle` in `qualify_f017_native_synthetic_family_v1.py`)
- **Evidence**: Q/K computation explicitly drops K-RoPE (`q[head * qdim..head * qdim + config.qk_nope]`). The `score` calculation is a dummy numerical gate; `attention` is derived strictly from `values` which is effectively `attn_v_b * kvn`.
- **Failure mode**: Missing K-RoPE and sequence/KV simplification. The graph fundamentally collapses the contextual attention matrix to a linear sequence bypass, ignoring true 79-layer production semantics.
- **Smallest repair**: Implement complete rotary embeddings and causal sequence attention over an actual K/V cache.

**F017-SECONDARY-CIRCULAR** (`BLOCKING`)
- **Path/symbol**: `scripts/research/f017_corrected_oracle_secondary.py:79`
- **Evidence**: The secondary script explicitly executes `from qualify_f017_quantization_matrix_v1 import independent_decode`.
- **Failure mode**: Shared-code contamination. Reusing the primary's diagnostic quantization metadata helper makes the secondary cross-check circular.
- **Smallest repair**: Re-implement independent dequantization semantics inside the secondary oracle without external imports.

**F017-ACCOUNTING-COLLISION** (`NON_BLOCKING_REQUIRED`)
- **Path/symbol**: `f017_corrected_oracle_primary.py:__init__` & `f017_corrected_oracle_secondary.py:__init__`
- **Evidence**: Both oracles share `event_root = Path.home()/".local"/.../auth["authorization_id"]` and start `self.sequence = 0`.
- **Failure mode**: Ambiguous dual-consumer accounting. Due to `O_EXCL`, the secondary consumer will violently fault on `00000000.json` if run after the primary under the same authorization.
- **Smallest repair**: Namespace the `event_root` directory by appending the consumer identity (e.g. `INDEPENDENT_ACCELERATED_CROSS_CHECK`).

**F017-ACCESS-EVENT-LATE** (`NON_BLOCKING_REQUIRED`)
- **Path/symbol**: `scripts/research/f017_corrected_oracle_primary.py:_raw`
- **Evidence**: `os.open` and `os.pread` are executed before their respective `SHARD_OPEN` and `PAYLOAD_READ` events are emitted.
- **Failure mode**: Unsafe failure handling. Access events are emitted only after a successful action. Short reads or permission denials will raise an exception and leave the ledger silently missing the failed attempt.
- **Smallest repair**: Emit a pre-action event prior to `os.open` and `os.pread`, recording the definitive result only after the syscall completes.

**F017-TOP-N-STABILITY** (`DEFENSE_IN_DEPTH`)
- **Path/symbol**: `crates/f017-native/src/model.rs:514-518`
- **Evidence**: Token extraction calculates `max_by` strictly over `logits`, defaulting to a top-1 selector with tie-breaking rules, even though `DiagnosticObserver` processes top-32.
- **Failure mode**: Weak top-1 stability mechanism; missing robust top-N structural resolution.
- **Smallest repair**: Align the layer's math boundary to project and utilize full top-32 stabilization as requested.

---

`REJECT`
