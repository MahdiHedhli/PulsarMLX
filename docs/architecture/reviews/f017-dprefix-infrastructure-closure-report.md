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
  `544f371151bc04a43d337d6765c818ce9d6e38ef`.
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
  `fe53a89ab8619675650346faae314a6219312a5be67e2a85a2c5a64fa5a4abc4`.
- Candidate source-manifest artifact SHA-256:
  `10e59b6223552693b63ab48765e6fe4930c05303af753d19c8dc46b41180fd5f`.
- Candidate executable SHA-256:
  `69b8cda5e3a6e600d29c899cb75ac4cdcf98ef301f50d506240c3499c918ae4f`.
- Executable size: 724,176 bytes; Mach-O arm64.
- Rust/Cargo: 1.97.1; target `aarch64-apple-darwin`.
- Native MLX bindings: libmlx
  `6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed`
  and libmlxc
  `a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62`.
- Build-manifest artifact SHA-256:
  `894e08b0a6da8be670f266f4035dde5eeb9a7a77ea22360f373827e76c92c67a`.

The binary verifies its own bytes, source manifest, config, authorization,
inventory, prompt, attempt, and ledger before accepting a material package.
There is no execution-time build or loose PATH lookup.

## Instantiated independent oracle

The reviewed source contract remains
`0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`.
Its concrete package is now instantiated before candidate creation:

- Oracle source-manifest semantic identity:
  `9e7d233e2816401d95ddd009c239cf78f05b080afe9c3cecc3ad8f60bf8f53ae`.
- Oracle source-manifest artifact SHA-256:
  `555a8b9390489f250dda4a85f16e22e6a178076da6d2c7fa098ad4e2a6ea26a0`.
- Instantiated package semantic identity:
  `4f8344057c962c96f969aeb8dc60b833939dc64dd59ab5addec4b4c2249c486f`.
- Instantiated package artifact SHA-256:
  `2302c92c51428593d927e0ae438d103d60eb7efbac5baf75c290443a597913eb`.
- Environment: CPython 3.13.13, NumPy 2.4.5, no PRNG.
- Independence verdict: `ORACLE PACKAGE INDEPENDENT`.

The package imports no Rust FFI, MLX, candidate helper, candidate output,
candidate intermediate, or candidate-generated expectation. Architectural
constants are explicit shared facts. Oracle completion and freezing precede
candidate context creation; a post-candidate package rehash is mandatory.

## Synthetic actual-binary qualification

The exact candidate binary completed ten complete checkpoint-free native MLX
runs at the production hidden width of 6,144. All required stage hashes were
deterministic. The observed aggregate was
450 native matvecs, 450 synchronizations, 450 readbacks, 120 CPU RMSNorms, 30
CPU attention steps, and 30 CPU activations, with zero fallback and zero backend
errors. Ownership/lifecycle reconciled after every native operation.

The independent NumPy oracle comparison produced max absolute error
`2.980232238769531e-7`, RMSE `8.784636688537564e-8`, and cosine
`0.9999999999999802`, passing the frozen checkpoint-free Tier-B surface.
The retention rehearsal created 6,144 canonical LE-f32 values, made the byte
artifact read-only, and verified its SHA.

## Successor package

- Config successor: `CONFIG_V3`; artifact SHA-256
  `1ec301f23735dbebd7360ef58f38ba78cfc89dad878f3b6c63686ac63952a806`.
- Authorization-binding successor artifact SHA-256:
  `68e37070e50c96cd57d2e0dd79199f1a63952163adfd614f7200907ca3b3d248`.
- Append-only attempt-ledger successor artifact SHA-256:
  `b18be3ab1f5589942a232d5d04fcd57888eb7bde14b363ca62368a387a1242fe`.
- Canonical preflight artifact SHA-256:
  `4bd97b2a39702fc1f6c2362409ef3928ba5983289738c472b7cf66cd0c09952a`.
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
  `cargo test --workspace --no-fail-fast` passed from the clean production-width
  preparation head.
- Python: all 729 research/evidence tests passed.
- Focused closure: all 13 candidate/oracle identity, independence, ordering,
  mutation, retention, memory, and ledger tests passed.
- Apple-native CI run `31923275566` passed at exact head
  `544f371151bc04a43d337d6765c818ce9d6e38ef`.
- Apple jobs `95106636671` and `95106636692` both concluded `success`, including
  the concrete 6,144-wide candidate/oracle rehearsal with no relevant skip.

## Exact next action

Independent adversarial review of
`docs/architecture/reviews/f017-dprefix-infrastructure-closure-adversarial-packet.md`.
Only a verdict of `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` may release a
fresh explicit execution instruction for the still-unconsumed attempt.
