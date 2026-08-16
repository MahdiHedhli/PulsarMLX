# PulsarMLX F017 DPREFIX Infrastructure-Closure Report

## Disposition

`READY FOR DPREFIX INFRASTRUCTURE-CLOSURE ADVERSARIAL REVIEW`

Internal verdict: `GO FOR DPREFIX INFRASTRUCTURE-CLOSURE ADVERSARIAL REVIEW`.

This phase performed zero checkpoint opens, positional reads, or payload reads.
The real-payload ledger remains 59 and `DPREFIX-REAL-1` remains authorized,
unconsumed, unexecuted, and checkpoint-unaccessed.

## Lineage and prior event

- Starting/authorization lineage: `6120be0c279c6b8e8cd3a44ec52790a5fbe7811b`.
- Final preparation evidence head:
  `80b600928b7bddb6b3275daa876a7ee1cba81350`.
- Immutable prior non-execution evidence SHA-256:
  `b8495bd1a4129efc7e24c687289bcb3be7af7f153e24d45ccffdccb79e79d60a`.
- The historical fact remains `DPREFIX-REAL-1 / NOT_EXECUTED /
  INFRASTRUCTURE`, consumed false, checkpoint access zero, ledger 59→59.
- Continuation decision: `SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE`.
  Consumption begins only immediately before the first authorized positional
  checkpoint read. The prior event stopped during non-consuming preflight and
  did not change the append-only attempt state.

## Candidate execution surface

The dedicated `f017-dense-prefix-candidate` binary exposes only self-verification,
checkpoint-free synthetic rehearsal, and consumption of a pre-authorized
40-tensor material package. Its computation surface ends after embedding plus
dense layers 0–2 and layer-3-entry retention. Layer-3 attention, routing,
experts, logits, the output head, generation, M1-F0, M1-F, and P1 are absent.

- Candidate source-manifest semantic identity:
  `ec1a5796f6e8225b2f003d49f240e69e110195a8b10af4c457fef731a710f996`.
- Candidate source-manifest artifact SHA-256:
  `449540d3926e9651f7a629ac414bcc3e806af671361e8acafb25934407145760`.
- Candidate executable SHA-256:
  `1b35cb487289007ccfb09bed7dab8ce6d5794048de7578ae74e3935edba64bb5`.
- Executable size: 724,128 bytes; Mach-O arm64.
- Rust/Cargo: 1.97.1; target `aarch64-apple-darwin`.
- Native MLX bindings: libmlx
  `6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed`
  and libmlxc
  `a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62`.
- Build-manifest artifact SHA-256:
  `7afd92b6231422909fc495b70e8b2b73415f792e04b25390040aabfadc92eb83`.

The binary verifies its own bytes, source manifest, config, authorization,
inventory, prompt, attempt, and ledger before accepting a material package.
There is no execution-time build or loose PATH lookup.

## Instantiated independent oracle

The reviewed source contract remains
`0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`.
Its concrete package is now instantiated before candidate creation:

- Oracle source-manifest semantic identity:
  `c133d16d411fb4a3c1dc649515527f555e8f0c5e43243127fcd29ed61d773674`.
- Oracle source-manifest artifact SHA-256:
  `8ac82dd7c0400655be72f6bb0d8a78ab72783e1003ccde458274d1ad014164ee`.
- Instantiated package semantic identity:
  `709f4ff88c71d4f017be6a709a255f4f77fe4ef06c82268c44b4b0c2f5ea98c4`.
- Instantiated package artifact SHA-256:
  `2e80e5fddc6d3089d229e0a28252aa5345c821886583fb0a9cf1a66578642633`.
- Environment: CPython 3.13.13, NumPy 2.4.5, no PRNG.
- Independence verdict: `ORACLE PACKAGE INDEPENDENT`.

The package imports no Rust FFI, MLX, candidate helper, candidate output,
candidate intermediate, or candidate-generated expectation. Architectural
constants are explicit shared facts. Oracle completion and freezing precede
candidate context creation; a post-candidate package rehash is mandatory.

## Synthetic actual-binary qualification

The exact candidate binary completed ten complete checkpoint-free native MLX
runs. All required stage hashes were deterministic. The observed aggregate was
450 native matvecs, 450 synchronizations, 450 readbacks, 120 CPU RMSNorms, 30
CPU attention steps, and 30 CPU activations, with zero fallback and zero backend
errors. Ownership/lifecycle reconciled after every native operation.

The independent NumPy oracle comparison produced max absolute error
`2.9802322387695312e-8`, RMSE `1.1292023679607682e-8`, and cosine
`0.9999999999999973`, passing the frozen checkpoint-free Tier-B surface.
The retention rehearsal created 6,144 canonical LE-f32 values, made the byte
artifact read-only, and verified its SHA.

## Successor package

- Config successor: `CONFIG_V3`; artifact SHA-256
  `b6524603085b9921a6ebc23adc191c636afc9853e83d6d1ebdb476ebb257b752`.
- Authorization-binding successor artifact SHA-256:
  `9b0445e281000f295a4b21bbab6bbaa7b7b8390ce350f400ce5546725033ad4e`.
- Append-only attempt-ledger successor artifact SHA-256:
  `c797c7aa9300d75c03194cd0c88f3b1c33df298746ccfe113d07cb6339c7fd87`.
- Canonical preflight artifact SHA-256:
  `0ed032067fe44480d930b0001bb84332de5eb9b814b09fb6ecf6ca9e0e8b49f6`.
- Preflight result: `READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`.

The config keeps preparation-contract v2, the 40-entry inventory, prompt,
Tier-B, repeat, dispatch, lifecycle, retention, host admission, ledger 59→99,
and all numerical thresholds unchanged. It adds direct candidate binary/source
and oracle package/source bindings. Authorization is exact to
`DPREFIX-REAL-1`; automatic retry and automatic M1-F0 continuation remain
false.

## Memory and access

Concrete candidate and oracle package overhead fits within the existing
pre-observation reserve. The 27 GiB free-memory floor is unchanged and was not
lowered. Real checkpoint access is 0; the real-payload ledger is 59.

## Validation and CI

- Rust: `cargo check --workspace --all-targets` and
  `cargo test --workspace --no-fail-fast` passed from the clean preparation
  head.
- Python: all 729 research/evidence tests passed.
- Focused closure: all 13 candidate/oracle identity, independence, ordering,
  mutation, retention, memory, and ledger tests passed.
- Apple-native CI run `31922410121` passed at exact head
  `80b600928b7bddb6b3275daa876a7ee1cba81350`.
- Apple jobs `95104326196` and `95104326249` both concluded `success`, including
  the concrete candidate/oracle rehearsal with no relevant skip.

## Exact next action

Independent adversarial review of
`docs/architecture/reviews/f017-dprefix-infrastructure-closure-adversarial-packet.md`.
Only a verdict of `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` may release a
fresh explicit execution instruction for the still-unconsumed attempt.
