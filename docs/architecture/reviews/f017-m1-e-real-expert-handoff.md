# F017 M1-E Real Expert Handoff

**Status: PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This handoff freezes one complete-expert boundary. It does not authorize the
three real payload reads or production execution.

Runtime/tooling implementation: `466770362e3066fa5fd9827ec1f454e03afe3006`.
The private, machine-local execution configuration prepared from that exact
implementation has SHA-256
`00ef0a08a033b0652ca521004f8b459a40169d1a43dc5c9cd5dae33a0d80cd90`.
Its canonical non-consuming production preflight returned exactly
`READY_TO_EXECUTE_M1_E`; it created no attempt state, evidence, oracle, or
payload artifact.

## Accepted chain

- M1-A: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- M1-B: `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`
- M1-C: `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`
- M1-D accepted attempt 3: `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` / `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` / `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`

## Frozen expert

Layer 3, expert 15 (`blk.3.expert.15`) is selected from pre-existing Feature
016 routing metadata, before any M1-E payload or candidate observation. The
activation is independently generated; router execution and routing weight
application are not part of this complete-expert boundary.

| Role | Tensor | Quant | Logical matrix | Shard | Offset | Bytes | Row bytes | Catalog identity |
|---|---|---|---:|---:|---:|---:|---:|---|
| gate | `blk.3.ffn_gate_exps.weight` | IQ2_XXS | 2048 × 6144 | 2 | 3423197024 | 3244032 | 1584 | `42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354` |
| up | `blk.3.ffn_up_exps.weight` | IQ2_XXS | 2048 × 6144 | 2 | 4268636000 | 3244032 | 1584 | `011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119` |
| down | `blk.3.ffn_down_exps.weight` | IQ3_XXS | 6144 × 2048 | 2 | 2203342688 | 4816896 | 784 | `1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1` |

Budget: exactly one shard open, three positional reads, three payloads, and
11,304,960 compressed bytes. No wildcard, adjacent expert, router, shared
expert, layer, output-head, or logits read is admitted.

## Frozen input and contracts

- activation fixture: `specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json`
- activation artifact/payload: `a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8` / `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- generator source: `c797e5200bd126a42b1303c2c06d7ef5bbad11738241cbd9f54e014a49a0a77e`
- decoder contract: `357a1989174b0ec86684549f8519bb7a47fdb8b8194fa985c8126d89d6339a00`
- exact scaffold: `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38`
- M1-E Tier-B: `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- repeat integrity: `26e956628006ba86980f106344531586a0437cc0cdf289333144319e3e6c10a4`
- boundary: `0b28cc94522c52cc21df3bce72084d07bdd22f92bd21f5f0dd9775066e675a1a`
- timing contract: `1449b2a8253c35627274fc54d722f12e6365a8fb35544c6af2275737764a2ccc`
- evidence schema: `8779b966080c21f6a287e096363b141158e54e7022df96b3786cb1a1a774b264`
- execution-config schema: `e7d7b79617adffd35236b2401920d0b9cbb66f52dd2b84ca887ccdcb634cbcab`
- execution-config preparer: `695e62302605f75c07de23382507beb58fb0c439f3fe83af2b6b1887ad948c40`
- config-only authorized launcher: `c23a1b9f40acca8214594a226bcec8596e3e2ee40877aa61198365f21bdfd211`
- real-reference preparer: `1276a2818b9dceaa9e2029461df82d81776d6d8f76f3b3c6033cd903e7b318b6`
- independent IQ2_XXS decoder: `9de6b59ce7fa3633e9fc521100badf4f5da2dd37bde037be88e8022904615761`
- independent IQ3_XXS decoder: `316ab363b6a78681a8e3b1960ef86e77983e46654099a2e8aff4f5c81417bec8`
- path-resolution contract: `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d`

The activation has 6,144 little-endian f32 elements, Python 3.13.13, NumPy
2.4.5, PCG64 seed 17017005, finite mixed-sign values, signed zero,
subnormal-adjacent, cancellation, and moderate-large values.

The independent Python/NumPy preparer decodes only the three authorized
ranges, produces gate/up/SwiGLU/down stage bytes and hashes, derives the
immutable v1 gate/up/activated-hidden/final bound vectors and hashes, atomically finalizes its read-only package, and
completes before candidate start. It imports no Rust, MLX, FFI, or candidate
output. Real stage hashes deliberately do not exist until the separately
authorized attempt reads the real payloads.

## Numerical and production contract

`f017-production-m1e-expert-tier-b-v1` composes candidate-independent
operation-count bounds for both 6144-wide input matvecs, a global 1.1 SiLU
derivative bound plus product rounding, and the 2048-wide down matvec. It was
frozen without candidate output. NaN/Inf and signed-zero disagreement fail;
greedy is not applicable; success is
`numerically_qualified_greedy_not_applicable`. v1 is immutable after
observation; any semantic change requires reviewed v2.

One conceptual expert requires ten complete repeats. Each repeat records gate,
up, activated-hidden, and final-output hashes. All four stages must be
bit-identical across ordinals 0–9. Three production matvecs per repeat yield
exactly 30 native dispatches. Production scaffold, explicit reference,
fallback, backend error, router, layer, and logits counts are zero.

## Canonical future flow

The only admitted launch shape is:

```text
M1-E authorization -> immutable typed execution config
  -> --m1e-preflight-only CONFIG --execution-config-sha256 SHA256
  -> READY_TO_EXECUTE_M1_E
  -> --m1e-execution-config CONFIG --execution-config-sha256 SHA256
```

There are no loose tensor, expert, activation, contract, or output overrides.
Preflight performs metadata/content-hash/root checks without tensor payload
access and does not consume the attempt. Consumption begins only after
preflight, production admission, immutable-config revalidation, and the
`EXECUTION_STARTED` transition.

The future authorized launcher consumes only the config path and its hash.
The config itself binds the runner binary, oracle launcher, private roots,
three tensor ranges, activation, every contract/source hash, all prior
evidence, the 30-dispatch budget, and all private output targets. Loose tensor,
fixture, expert, contract, or evidence-output arguments do not exist.

After consumption there is no retry. PASS is persisted only after oracle
ordering, ten-repeat integrity, Tier-B qualification, teardown, lifecycle,
dispatch, path/config immutability, evidence validation, and privacy checks.
Stop before M1-F regardless of result.
