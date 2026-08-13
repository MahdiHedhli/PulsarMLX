# F017 Fresh M1-E Authorization

**Status: AUTHORIZED FOR EXACTLY ONE M1-E ATTEMPT / NOT EXECUTED**

This packet authorizes one complete layer-3/expert-15 experiment. It does not
authorize M1-F, a second expert, router/top-8/shared-expert aggregation, a
complete layer, logits, P1/P2/golden-eight, or Feature 018.

## Immutable source and evidence binding

- runtime SHA: `466770362e3066fa5fd9827ec1f454e03afe3006`
- tooling/validator SHA: `3387bb6d4508eb04e672dc6194da2855ba72f072`
- reviewed final package head: `f3a7ba8f3a7eb52dbf48c6929e23835e5c18eeea`
- handoff: `docs/architecture/reviews/f017-m1-e-real-expert-handoff.md`
- handoff SHA-256: `2325f9b2964b5c1120864fbaa4d3fda875f8d263154d783bf02b6ad47e78e531`
- execution-config SHA-256: `7f69550bfd7ccd5e820f23d2bcce7f0e287d2c2bfc5f1ae2adb59ec5467b0a1b`
- M1-A/B/C/D evidence: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` / `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` / `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` / `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` / `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` / `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`

The authorization publication is a documentation-only descendant of the
reviewed package head. It does not replace either the runtime or tooling SHA.

## Exact expert and payload budget

- expert: layer 3, expert 15, `blk.3.expert.15`
- gate: `blk.3.ffn_gate_exps.weight`, IQ2_XXS, shard 2, offset
  3423197024, 3244032 bytes, catalog
  `42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354`
- up: `blk.3.ffn_up_exps.weight`, IQ2_XXS, shard 2, offset 4268636000,
  3244032 bytes, catalog
  `011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119`
- down: `blk.3.ffn_down_exps.weight`, IQ3_XXS, shard 2, offset
  2203342688, 4816896 bytes, catalog
  `1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1`
- maximum: three payloads, one shard open, three positional reads, 11,304,960
  compressed bytes

## Frozen input, oracle, and contracts

- activation artifact/payload: `a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8` / `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- activation generator: `c797e5200bd126a42b1303c2c06d7ef5bbad11738241cbd9f54e014a49a0a77e`
- real-reference preparer: `1276a2818b9dceaa9e2029461df82d81776d6d8f76f3b3c6033cd903e7b318b6`
- independent IQ2/IQ3 decoders: `9de6b59ce7fa3633e9fc521100badf4f5da2dd37bde037be88e8022904615761` / `316ab363b6a78681a8e3b1960ef86e77983e46654099a2e8aff4f5c81417bec8`
- decoder/scaffold/Tier-B: `357a1989174b0ec86684549f8519bb7a47fdb8b8194fa985c8126d89d6339a00` / `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` / `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- boundary/repeat/timing: `0b28cc94522c52cc21df3bce72084d07bdd22f92bd21f5f0dd9775066e675a1a` / `26e956628006ba86980f106344531586a0437cc0cdf289333144319e3e6c10a4` / `1449b2a8253c35627274fc54d722f12e6365a8fb35544c6af2275737764a2ccc`
- path/evidence/config schemas: `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d` / `8779b966080c21f6a287e096363b141158e54e7022df96b3786cb1a1a774b264` / `e7d7b79617adffd35236b2401920d0b9cbb66f52dd2b84ca887ccdcb634cbcab`

## One-attempt execution contract

The operator must use the machine-local immutable execution config and its
exact hash. No tensor, expert, fixture, contract, output, or path argument may
be hand assembled or overridden.

1. Run the config-only non-consuming preflight and require exactly
   `READY_TO_EXECUTE_M1_E`.
2. Require `production_reviewed`, measured-host admission, arm64, and verified
   loaded MLX libraries.
3. Revalidate the same config, then persist `EXECUTION_STARTED`; only this
   transition consumes the attempt.
4. Read only the three authorized payloads and finalize the independent oracle
   before candidate start.
5. Execute one conceptual expert: gate, up, exact CPU SwiGLU orchestration,
   and down. Run ten complete repeats, exactly 30 native matvec dispatches.
6. Require all gate/up/activated-hidden/final hashes to be identical across
   ordinals 0–9, all frozen Tier-B bounds to pass, and production
   scaffold/reference/fallback/backend-error counts to remain zero.
7. Reconcile lifecycle, dispatch, repeat, oracle, path/config, and evidence
   invariants before PASS persistence.
8. Stop after the first result. No retry and no M1-F execution.

Qualification CI: `31656082515`, both Apple jobs green at the reviewed package
head. Internal and independent reviews both returned
`GO FOR ONE M1-E REAL EXPERT`.
