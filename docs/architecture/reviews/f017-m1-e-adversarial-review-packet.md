# F017 M1-E Adversarial Review Packet

**Scope:** one complete layer-3 expert, checkpoint-aware metadata and
checkpoint-free execution qualification only. Real gate/up/down payloads have
not been read and M1-E has not executed.

## Accepted chain and implementation

- runtime implementation: `466770362e3066fa5fd9827ec1f454e03afe3006`
- tooling/test qualification: `3387bb6d11e4c84e87e323b243142242366bdc5a`
- accepted M1-D evidence: `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- M1-A/B/C: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` / `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` / `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`
- checkpoint/catalog/map: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` / `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` / `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- private immutable execution config: `758bb3092356954ee496743074d61a0dbb792d3b77a9de7651d73383745488c0`
- production preflight: `READY_TO_EXECUTE_M1_E`, non-consuming, no payload access

The trusted execution repository root is a separate clean detached checkout
at the runtime SHA. Its identity is validated independently of the current
tooling/review branch head, preventing a docs/test descendant from silently
becoming the executable source boundary.

Commits after the M1-D evidence head `d70090d0` are deliberately classified:

| Commit | Class | Meaning |
|---|---|---|
| `36c247d3` | runtime/contracts/tests | freeze complete expert composition and evidence |
| `2da67a8d` | runtime/tests | make production preflight non-persisting and repeatable |
| `ad45f4cd` | tooling/runtime/tests | config-only oracle preparation and canonical launch |
| `abe1e497` | oracle/contracts/tests | bind all four oracle bound vectors |
| `46677036` | evidence runtime/test | preserve terminal failures without weakening PASS validation |

There is no unexplained runtime drift.

## Boundary and access budget

Selected before payload observation: layer 3, expert 15,
`blk.3.expert.15`.

| Role | Tensor | Quantization | Logical shape | Shard | Offset | Packed bytes | Row bytes | Catalog identity |
|---|---|---|---:|---:|---:|---:|---:|---|
| gate | `blk.3.ffn_gate_exps.weight` | IQ2_XXS | 2048 × 6144 | 2 | 3423197024 | 3244032 | 1584 | `42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354` |
| up | `blk.3.ffn_up_exps.weight` | IQ2_XXS | 2048 × 6144 | 2 | 4268636000 | 3244032 | 1584 | `011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119` |
| down | `blk.3.ffn_down_exps.weight` | IQ3_XXS | 6144 × 2048 | 2 | 2203342688 | 4816896 | 784 | `1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1` |

The maximum is three payloads, one shard open, three positional reads, and
11,304,960 compressed bytes. Router, shared expert, second expert, adjacent
tensor, layer, logits, and output-head access are prohibited.

## Independent input and oracle

- activation: 6,144 canonical little-endian f32 values, Python 3.13.13,
  NumPy 2.4.5, PCG64 seed 17017005
- activation artifact/payload: `a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8` / `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- generator: `c797e5200bd126a42b1303c2c06d7ef5bbad11738241cbd9f54e014a49a0a77e`
- independent preparer: `1276a2818b9dceaa9e2029461df82d81776d6d8f76f3b3c6033cd903e7b318b6`
- independent IQ2/IQ3 decoders: `9de6b59ce7fa3633e9fc521100badf4f5da2dd37bde037be88e8022904615761` / `316ab363b6a78681a8e3b1960ef86e77983e46654099a2e8aff4f5c81417bec8`

The Python/NumPy oracle reads only the three bounded ranges, independently
decodes them, performs strict sequential-f32 gate/up/SwiGLU/down arithmetic,
and persists canonical bytes and hashes for all decoded matrices, stage
outputs, and four bound vectors. It imports no Rust, MLX, FFI, candidate
reference, or candidate output. Atomic finalization and strict oracle-before-
candidate ordering inherit the accepted M1-D mechanism.

## Frozen contracts

| Contract | SHA-256 |
|---|---|
| boundary | `0b28cc94522c52cc21df3bce72084d07bdd22f92bd21f5f0dd9775066e675a1a` |
| decoder | `357a1989174b0ec86684549f8519bb7a47fdb8b8194fa985c8126d89d6339a00` |
| exact scaffold | `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` |
| expert Tier-B | `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2` |
| repeat integrity | `26e956628006ba86980f106344531586a0437cc0cdf289333144319e3e6c10a4` |
| timing | `1449b2a8253c35627274fc54d722f12e6365a8fb35544c6af2275737764a2ccc` |
| evidence schema | `8779b966080c21f6a287e096363b141158e54e7022df96b3786cb1a1a774b264` |
| execution-config schema | `e7d7b79617adffd35236b2401920d0b9cbb66f52dd2b84ca887ccdcb634cbcab` |
| path resolution | `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d` |

The Tier-B v1 composition is candidate-independent: both 6144-wide input
matvec errors feed a 1.1 global SiLU derivative/product-rounding bound; that
hidden bound feeds the 2048-wide down matvec. It retains nonzero upstream error
when an exact up lane is zero. Per-element bounds, global maximum, RMSE, cosine,
signed-zero, and finite-value policies are immutable before observation.
Greedy is not applicable; the only success classification is
`numerically_qualified_greedy_not_applicable`.

## Production, repeat, lifecycle, and evidence gates

One conceptual expert has gate, up, and down production MLX matvecs. Ten full
repeats therefore require exactly 30 native dispatches. Gate, up,
activated-hidden, and final-output canonical hashes are captured for every
ordinal 0–9 and all four stages must be byte-identical. Exact SwiGLU is a
declared deterministic CPU orchestration operation, never a fallback.
Production scaffold/reference/fallback/backend-error counts must all be zero.

PASS remains structurally after oracle validation, execution, synchronization,
teardown, lifecycle reconciliation, dispatch/repeat reconciliation, oracle and
config immutability rechecks, numerical validation, and final evidence
validation. Terminal failure evidence remains bankable; the PASS-only
invariants are still required for both the pre-PASS `INCOMPLETE` candidate and
the persisted `PASS` record.

The canonical native synthetic integration uses real shapes and quantization
packing through the same immutable config, relocated private package,
unrelated cwd, trusted repository root, private payload-resolution branch,
production MLX adapter, 30 native dispatches, and ten repeats. Failure
injection covers wrong expert/tensor/name/shape/quantization, truncation,
second-expert/router access, wrong activation, stale oracle/order, intermediate
repeat divergence with matching final output, dispatch mismatch, fallback,
lifecycle failure, consumed attempt, and post-preflight config mutation.

## Reviewer checklist

The internal implementation reviewer and independent adversarial reviewer must
separately verify:

1. layer 3/expert 15 and all three catalog/range bindings are exact;
2. activation and oracle are independent of candidate/MLX output;
3. arithmetic and expert-level Tier-B composition were frozen before candidate;
4. the access budget permits exactly the three selected payloads;
5. config-only launch, preflight non-consumption, and one-expert isolation hold;
6. ten-stage repeat hashes, 30 dispatches, and lifecycle accounting fail closed;
7. no production scaffold/reference/fallback path exists;
8. accepted M1-D and all prior evidence are bound immutably;
9. M1-F and P1 remain blocked.

Each review must return exactly one of:

- `GO FOR ONE M1-E REAL EXPERT`
- `GO WITH REQUIRED FIXES`
- `NO-GO`
