# PulsarMLX F017 Route-Stability v2 Finalization + Recovery Preparation Report

## Outcome

The final route-stability v2 contract is frozen and checkpoint-free qualified.
The antecedent-recovery package is complete, immutable, non-consuming, and not
authorized. No real checkpoint data was accessed in this phase.

- Starting SHA: `ab3d991260d9f262430731e762282a7b9cd8995b`
- Tooling SHA: `6b56dc88f89b92ebaeb525a35e48b3c2c1bc8fec`
- Tooling tree: `61eda4e19c57b0ddeea92a73468cbb5edff6019e`
- Final evidence head: the commit containing this report; recorded in the final
  handoff after Git assigns the non-circular commit identity
- Candidate v2: `fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c`
- Final v2: `36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7`
- Accepted route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- Accepted analytical recovery: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- Historical v1 remains: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`

## Candidate-to-final amendments

Bias-operand perturbation remains exactly zero because candidate and oracle use
identical decoded bias bytes. The final contract now separately covers the
rounding of `fl(sigmoid(logit) + bias)`: one outward full-ULP guard for each
candidate/oracle score addition, four additions in the pairwise envelope. The
maximum observed guard in stress was `5.684341886080804e-14`, at most
`5.204970970788562e-6` of the total sampled bound.

Ordered selected stability is now required, not conditional. Membership uses all
`8 * 248 = 1,984` selected/unselected pairs; normative top-8 byte order uses the
seven adjacent selected pairs. Strict adjacent stability preserves the complete
order by transitivity, and any non-adjacent reorder requires at least one
adjacent crossing. Exact ties fail the strict proof and are resolved
deterministically by lower expert ID.

No other mathematical term changed. Mathematical stability is the strict
pairwise theorem. Engineering headroom remains `H = 2`, explicitly reserving one
additional complete modeled error envelope for implementation/library drift; it
is not required mathematically for swap prevention. Post-observation retuning
and candidate-observed inputs remain forbidden.

## Mathematical qualification

- Randomized cases: `100,000`
- Directed adversarial cases: all PASS
- Under-bounds: `0`
- Independent implementation mismatches: `0`
- Maximum observed actual/bound ratio: `0.9563522005807091`
- High precision: six 100-digit Decimal outward-rounding checks, PASS
- Final stress evidence SHA: `438fc823de4c25fa7e462aeeed6a041180c0393bcf82b9f30bbb96ab4fa5b309`

Sigmoid derivative tests cover `[-1,1]`, `[0,1]`, `[-1,0]`, `[5,10]`,
`[-10,-5]`, a tiny interval around zero, and one-ULP endpoint shifts. Intervals
crossing zero use `0.25`; one-sided intervals use the endpoint closest to zero,
with outward logit-interval construction.

The primary structured CPython implementation has SHA
`113d6bcd530ea41b9af6f00df31c9efa8498c6f76775b9087a161275d971b848`.
The separately transcribed scalar implementation has SHA
`ae121252714c6f082a9d084b7323013136ebfe18978bc75ed9e3e860e5f0c220`.
They share binary64 primitives and input mappings only: no shared parser,
generated expected outputs, or expression implementation. Provenance evidence
SHA: `8af3f5791776d3ff9493e1304139b1bc8696a013a9acb156b62f41ff70571d08`.

## Supporting research closures

The random-normal support artifact is classified
`SEMI_ANALYTIC_EFFECTIVE_CEILING`, explicitly not a proven theorem. It binds the
ladder generator, ladder, estimator, estimator contract, bias, and final v2. Its
SHA is `0faf128b54e5dc0de24fe0b404df818284a142926c83c80213f5fe9da8e18fd1`.
The observed v1 maximum remains `3.129417274314236`; the eight-seed ladder was
not executed and remains numerical-stress-only pending later policy review.

The metadata-only expert-166 catalog cross-check passed. Gate starts at
`3913045856` with length `3244032`; up starts at `4758484832` with length
`3244032`; down starts at `2930693984` with length `4816896`. IDs
`0,1,15,166,255` pass and invalid IDs `-1,256` reject. Evidence SHA:
`5cc9845291ce57741a406c5d1b2417c6d3dbe93b85c3139ef16faf10053d5cec`.
It is metadata-only and does not bind expert 166 to a future route.

## Recovery retention

The retention manifest SHA is
`bd3cc6c10faee0d8c8072000403bbef68354286515482a6b78869ab02be81e13`.
Direct canonical little-endian f64 pre-sigmoid logits are required; logit
reconstruction from rounded probabilities is not used.

Public values and hashes required are: all 256 logits, probabilities, f32 bias
values, f64 scores, and u16 ranking; eight ordered selected IDs; 248 unselected
IDs; all 1,984 selected/unselected bounds; all seven adjacent-selected bounds;
minimum mathematical and engineering factors; per-selected worst challengers;
global membership worst pair; ordered worst adjacent pair; and both
classifications.

Private immutable antecedents required are: the 6,144-element attention
residual; 6,144-element router-normalized input; 256-by-6,144 router matrix;
6,144-element ffn-norm weight; RMSNorm decomposition inputs; 6,144 non-radial
component bounds; 256 router reduction bounds; and 256 import/materialization
bounds. Public descriptors retain SHA, dtype, shape, element count, canonical
serialization, provenance, source identities, creation ordering, and immutable/
read-only status. Absolute or machine-local public paths are forbidden.

## Exact future 12-tensor allowlist

All entries are shard ordinal 2 and allow exactly one read.

| Tensor | Quant | Offset | Packed bytes | Packed SHA-256 | Decoded SHA-256 |
|---|---:|---:|---:|---|---|
| `blk.3.attn_norm.weight` | F32 | 2008634208 | 24576 | `8f642efd9c89ec5cb59fea36262ad370985428a8f0f028b78d524e581f584b85` | `8f642efd9c89ec5cb59fea36262ad370985428a8f0f028b78d524e581f584b85` |
| `blk.3.attn_q_a.weight` | Q5_K | 2077864800 | 8650752 | `30eac1dc6c0538ebff3ceb56216423002ec798fd896785186e0653af3758d579` | `35e4f06b179cee97d791476882e2f1ed7ebbaa4ecd7c7e5a3e108a2c42520c45` |
| `blk.3.attn_q_a_norm.weight` | F32 | 2086515552 | 8192 | `faf7fc183f8539ac4c7be45d97353ca0068212d435c46c96daa1f6b8bb809f0f` | `faf7fc183f8539ac4c7be45d97353ca0068212d435c46c96daa1f6b8bb809f0f` |
| `blk.3.attn_q_b.weight` | Q8_0 | 2086523744 | 35651584 | `c54a2250b8da6f4bb4a3f7676a83dec862ccfd0d145634250dea7167496f1b47` | `5cff2689826b4608162dae7932f2187aa31ff5e2063655a62fce0a17ac185623` |
| `blk.3.attn_kv_a_mqa.weight` | Q8_0 | 2004872032 | 3760128 | `8f45a6d6e69a204c714acf4a09f7c29a1c5b34e4f581fb2fcc5771f0290d9053` | `332ce4d35767105dbef7e98c2ddb1093e624188d71a068dbca58579ff5c259ac` |
| `blk.3.attn_kv_a_norm.weight` | F32 | 2008632160 | 2048 | `ab7ae58c665fd82c5731ebea86b818d7d9652f870e503019068e154524801ce4` | `ab7ae58c665fd82c5731ebea86b818d7d9652f870e503019068e154524801ce4` |
| `blk.3.attn_k_b.weight` | Q8_0 | 1998187360 | 6684672 | `9903c9eea679d86016d28d61f8cf30f831ddf0d1458f9a8f43e062f2aa1f420f` | `89c38fc8661405b675c738de4a7ac6115931c492b00231b4e1c4562676f6b7ff` |
| `blk.3.attn_v_b.weight` | Q8_0 | 2122175328 | 8912896 | `86dbc54eae38b1d0dc8f9f7a3dfdbcca00e0eb87ac6dee2d244054a496a35367` | `3e4a176c261d7f9e612fc7f7dc7047cb9c7b338cdce71c47527aa7224f92f3a7` |
| `blk.3.attn_output.weight` | Q5_K | 2008658784 | 69206016 | `30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084` | `2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8` |
| `blk.3.ffn_norm.weight` | F32 | 4219950944 | 24576 | `1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f` | `1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f` |
| `blk.3.ffn_gate_inp.weight` | F32 | 4205008736 | 6291456 | `da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a` | `da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a` |
| `blk.3.exp_probs_b.bias` | F32 | 2131088224 | 1024 | `eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491` | `eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491` |

The budget is one shard open, 12 positional reads, 12 payloads,
`139217920` compressed bytes, and `666430464` decoded bytes. Expert payloads,
expert computation, MLX candidate dispatches, and M1-F execution are all zero.

## Identity reproduction gates

The config binds the accepted input fixture/package and hidden, position, MLA,
DSA, and mask identities, plus every tensor identity above. Required stage/route
hashes include:

- attention output: `9c7c150dfef3bf284e94fe1679844879bc1a9ec464c8161f9cb6ca71cc4f8911`
- attention residual: `1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7`
- router normalized input: `98275027e2427276822b84fc0c7747014b0f4d79b40c07e6d8267060db7762e1`
- router logits: `883580486b67430314738b1d98080ffafda77e957c4705b8258e3ac3decbd6fc`
- router probabilities: `9037c52ee87e06c6aeaf36ffe9a6d94a3ce84434028e1b751b44cc14f9317964`
- router scores: `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4`
- ranking: `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede`
- top-8 bytes: `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca`
- routing weights: `e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18`

The route remains `[166,78,26,186,163,199,233,177]`. Any mismatch fails before
v2 instantiation and cannot select a replacement route.

## Recovery package and simulation

- Execution config SHA: `649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2`
- Status: `NOT_AUTHORIZED_NOT_EXECUTED`
- Authorization head: `null`
- Current ledger: `45`
- Future successful recovery ledger: `57`
- Preparation ledger increment: `false`
- Preflight: `READY_TO_EXECUTE_V2_ANTECEDENT_RECOVERY`
- Preflight reads/contexts/oracle/consumption: all zero/false
- Synthetic full artifact SHA: `9dad2b614581c4aba95cf0587bf9508c154fa702ff7d65354730c03ad1001810`
- Synthetic public evidence SHA: `4ed5fd61035b93dc3368733da517706294e752ddc5611a6939dc7c9fef0fd82e`
- Synthetic result: PASS; 12 synthetic payloads, eight private artifacts,
  1,984 membership bounds, seven ordered bounds, immutable before/after hashes,
  zero MLX/expert activity, no route discovery, no attempt consumption

The result schema SHA is
`e4e414e4f7dd720b6a6884457edd7a85c0f5ee1a805a712de47435f692c6af61`.
It separates identity reproduction, antecedent completeness, retrospective v2
mathematical/engineering annotations, and immutable historical v1 status.

## Review and phase status

- Internal review: `GO FOR V2 RECOVERY-PACKAGE ADVERSARIAL REVIEW`
- Internal review SHA: `bb09e110c04637c285de6fc6e4e5a18d1067bab824716ceb991ef1631ce8ccce`
- Adversarial packet:
  `docs/architecture/reviews/f017-route-stability-v2-recovery-preparation-adversarial-packet.md`
- Adversarial packet SHA: `94aef229e295ee5a859bf079de9f2547406999f6af000d4b2b1efcea5a220e6e`
- Final-head Apple CI: required green before READY; exact run is recorded in the
  final handoff because the run is created only after this report is committed
- Real checkpoint access: `0`
- Frozen ladder execution: `false`
- Q6_K qualification: `false`
- M1-F execution: `false`
- P1: blocked

Exact next action: independent adversarial delta review of the final v2 contract
and this non-authorized recovery package.
