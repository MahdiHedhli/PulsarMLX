# PulsarMLX F017 V2 Antecedent Recovery Report

## Result

`V2 ANTECEDENT RECOVERY ACCEPTED`

The single authorized event reproduced the accepted M1-F0 oracle computation
exactly and retained the complete antecedent surface required by route-stability
v2. It did not discover a route, consume an M1-F0 attempt, access an expert,
dispatch MLX candidate work, or execute M1-F.

## Reviewed execution identities

| Binding | Identity |
|---|---|
| Reviewed execution head | `493a087a4aafc28aee1e5933400ac77366521361` |
| Execution-controlling tooling commit | `6b56dc88f89b92ebaeb525a35e48b3c2c1bc8fec` |
| Tooling tree | `61eda4e19c57b0ddeea92a73468cbb5edff6019e` |
| Final route-stability v2 contract | `36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7` |
| Recovery execution config | `649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2` |
| Recovery authorization | `46c1f8e0ef0ee38aee5565ccf3f389a29266beba1bcca32a41848bacde6ab906` |
| Start marker | `8f1308601c4d0976c7f52fd9cf641b50eac99c9d45b9b476768cc10bf50b9c0c` |
| Accepted route evidence | `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e` |
| Accepted analytical recovery | `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686` |

Preflight returned exactly
`READY_TO_EXECUTE_V2_ANTECEDENT_RECOVERY`, with zero checkpoint reads and no
attempt consumption. The recovery event was consumed once after its immutable
start marker; no retry occurred. Observed wall duration from start marker to
the immutable result artifact was approximately 238.99 seconds.

## Tensor allowlist and actual access

| Tensor | Quantization | Packed bytes | Decoded bytes | Packed SHA-256 | Decoded SHA-256 |
|---|---:|---:|---:|---|---|
| `blk.3.attn_norm.weight` | F32 | 24,576 | 24,576 | `8f642efd9c89ec5cb59fea36262ad370985428a8f0f028b78d524e581f584b85` | `8f642efd9c89ec5cb59fea36262ad370985428a8f0f028b78d524e581f584b85` |
| `blk.3.attn_q_a.weight` | Q5_K | 8,650,752 | 50,331,648 | `30eac1dc6c0538ebff3ceb56216423002ec798fd896785186e0653af3758d579` | `35e4f06b179cee97d791476882e2f1ed7ebbaa4ecd7c7e5a3e108a2c42520c45` |
| `blk.3.attn_q_a_norm.weight` | F32 | 8,192 | 8,192 | `faf7fc183f8539ac4c7be45d97353ca0068212d435c46c96daa1f6b8bb809f0f` | `faf7fc183f8539ac4c7be45d97353ca0068212d435c46c96daa1f6b8bb809f0f` |
| `blk.3.attn_q_b.weight` | Q8_0 | 35,651,584 | 134,217,728 | `c54a2250b8da6f4bb4a3f7676a83dec862ccfd0d145634250dea7167496f1b47` | `5cff2689826b4608162dae7932f2187aa31ff5e2063655a62fce0a17ac185623` |
| `blk.3.attn_kv_a_mqa.weight` | Q8_0 | 3,760,128 | 14,155,776 | `8f45a6d6e69a204c714acf4a09f7c29a1c5b34e4f581fb2fcc5771f0290d9053` | `332ce4d35767105dbef7e98c2ddb1093e624188d71a068dbca58579ff5c259ac` |
| `blk.3.attn_kv_a_norm.weight` | F32 | 2,048 | 2,048 | `ab7ae58c665fd82c5731ebea86b818d7d9652f870e503019068e154524801ce4` | `ab7ae58c665fd82c5731ebea86b818d7d9652f870e503019068e154524801ce4` |
| `blk.3.attn_k_b.weight` | Q8_0 | 6,684,672 | 25,165,824 | `9903c9eea679d86016d28d61f8cf30f831ddf0d1458f9a8f43e062f2aa1f420f` | `89c38fc8661405b675c738de4a7ac6115931c492b00231b4e1c4562676f6b7ff` |
| `blk.3.attn_v_b.weight` | Q8_0 | 8,912,896 | 33,554,432 | `86dbc54eae38b1d0dc8f9f7a3dfdbcca00e0eb87ac6dee2d244054a496a35367` | `3e4a176c261d7f9e612fc7f7dc7047cb9c7b338cdce71c47527aa7224f92f3a7` |
| `blk.3.attn_output.weight` | Q5_K | 69,206,016 | 402,653,184 | `30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084` | `2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8` |
| `blk.3.ffn_norm.weight` | F32 | 24,576 | 24,576 | `1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f` | `1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f` |
| `blk.3.ffn_gate_inp.weight` | F32 | 6,291,456 | 6,291,456 | `da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a` | `da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a` |
| `blk.3.exp_probs_b.bias` | F32 | 1,024 | 1,024 | `eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491` | `eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491` |

Actual accounting: one shard open, 12 positional reads, 12 payloads,
139,217,920 compressed bytes, and 666,430,464 decoded bytes. Expert payloads,
expert computation, MLX candidate dispatches, and M1-F executions were zero.

## Accepted-computation reproduction

The recovery reproduced every reviewed identity. Load-bearing outputs include:

| Output | SHA-256 |
|---|---|
| Attention output | `9c7c150dfef3bf284e94fe1679844879bc1a9ec464c8161f9cb6ca71cc4f8911` |
| Attention residual | `1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7` |
| Router-normalized input | `98275027e2427276822b84fc0c7747014b0f4d79b40c07e6d8267060db7762e1` |
| Pre-sigmoid logits | `883580486b67430314738b1d98080ffafda77e957c4705b8258e3ac3decbd6fc` |
| Probabilities | `9037c52ee87e06c6aeaf36ffe9a6d94a3ce84434028e1b751b44cc14f9317964` |
| Router scores | `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4` |
| Ranking | `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede` |
| Ordered top-8 bytes | `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca` |
| Routing weights | `e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18` |

Ordered IDs remained `[166, 78, 26, 186, 163, 199, 233, 177]`. The immutable
raw recovery evidence SHA-256 is
`f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a`.

## Antecedent retention

Public evidence retains canonical values plus hashes for all 256 logits,
probabilities, biases, scores, the full ranking, ordered and unselected IDs,
routing weights, all 1,984 membership bounds, all seven ordered-selected
bounds, per-selected worst challengers, and global extrema. Completeness is
1984/1984 and 7/7.

The public-safe private manifest SHA-256 is
`1007112a0642919321d0081e79bba12fe3809c456e79a22b9623d19689b78112`.
It describes eight immutable private artifacts:

| Private antecedent | Shape / dtype | SHA-256 |
|---|---|---|
| Attention residual | `[6144]` LE f32 | `1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7` |
| Router-normalized input | `[6144]` LE f32 | `98275027e2427276822b84fc0c7747014b0f4d79b40c07e6d8267060db7762e1` |
| Router matrix | `[256,6144]` LE f32 | `da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a` |
| FFN norm weight | `[6144]` LE f32 | `1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f` |
| RMSNorm decomposition inputs | canonical JSON | `09b6147d093cecdf587e39acae9010b39100f2dcc2868838032ffcba2183a468` |
| Non-radial component bounds | `[6144]` LE f64 | `5f049e9d00a658bdc8efeeef4ddd4b07198218db70229b5d7cf164a28b6a5583` |
| Router reduction bounds | `[256]` LE f64 | `eb764badb65d06c63ca267652c06af23b9df00bcebd01a845d95915a1ab7f5cf` |
| Router import/materialization bounds | `[256]` LE f64 | `b5df17d9c7cb737f840825fe8116e6f4cfdb8ce547a18419bb57be083286e937` |

No machine-local absolute path is published.

## Retrospective v2 result

All 1,984 selected-versus-unselected membership pairs are mathematically
stable. H=2 engineering membership headroom fails. The worst membership pair
is selected expert 177 versus unselected expert 98, with margin
`0.003818698540044352`, bound `0.003055557606453781`, and safety factor
`1.2497550469932908`.

The seven ordered-selected bounds are complete, but ordered stability fails.
The global worst pair is adjacent selected expert 233 versus expert 177, with
margin `0.0006498095249156677`, bound `0.0028814413437103334`, mathematical
safety factor `0.22551544432236478`, and engineering factor
`0.11275772216118239`.

Therefore:

- Membership verdict: `MATHEMATICALLY_STABLE`, without H=2 headroom.
- Selected-order verdict: `NOT_MATHEMATICALLY_STABLE`.
- Retrospective mathematical status: `NOT_MATHEMATICALLY_STABLE`.
- Retrospective engineering status: `NO_ENGINEERING_HEADROOM`.
- Historical v1 status unchanged: `true`.

The executor's immutable raw summary correctly rejected exact ordered stability
but reported its first failing ordered pair rather than the global minimum and
used exact-ordered stability as its route-set summary. The raw artifact was not
changed. A checkpoint-free audit over all retained pairs corrects the summary,
with a dedicated regression; the overall retrospective disposition is
unchanged. Its review SHA-256 is
`dd235d3e006e8721cf2f3decb1ea822c76cbce65a1660941661e7f68816f76ea`.

## Ledger, validation, and phase stop

The append-only real-payload ledger advances from 45 to 57 and has SHA-256
`1dc884c4a9c328bef518a3989e671ff33467f38b48d61405fdc25c160b7a6401`.
The recovery did not consume an M1-F0 route attempt and did not reclassify the
accepted route or historical v1 evidence.

Checkpoint-free validation covers result and identity reproduction, complete
pair surfaces, private-artifact hashes, raw-summary amendment, historical-v1
immutability, ledger arithmetic, duplicate-key and privacy/path rejection,
Spec Kit, Rust/Python regressions, and final-head Apple-native CI. The exact CI
run-to-head binding is recorded in the final handoff after the evidence head is
pushed and green.

M1-F execution: `false`. Q6_K: `blocked`. P1: `blocked`.

Exact next action: independent adversarial review of the recovery evidence.
