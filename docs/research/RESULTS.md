# Feature 002 Results

**Status**: Four independently sanitized Apple MLX layer-0 router experiment
records are published under `docs/research/raw/002-router-parity/` (primary
plus clean-checkout reproduction). Package-level claims F002-C01 through
F002-C03 are verified. No expert, aggregation, full-layer, generation,
serving, or tokens-per-second result is claimed.

Only validated, committed raw evidence governed by the [Feature 002 evidence
contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md)
may populate model-backed result sections. Fixture-only methodology checks are
documented separately below and are never promoted as model results.

## Fixture-only publication validation

Three full-schema synthetic records exercise `passed`, `failed`, and `aborted`
experiment outcomes. They generate six frozen outputs under
`fixtures/research/router-v1/expected/`. Fixture-only verification remains the
CI default without external checkpoint access. Constructed fixture durations and
errors do not measure checkpoint routing.

## Correctness records

Measured source commit: `04b3502aa5cfbe48cda66d1a5b0b07a45902f762`.

| Field | Value |
| --- | --- |
| Checkpoint | `Qwen3-30B-A3B-Q8_0.gguf` SHA-256 `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c` |
| Router tensor | `blk.0.ffn_gate_inp.weight` encoded SHA-256 `98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c` |
| Input | genuine `ffn_norm-0` direct token IDs `[0,1]`, canonical SHA-256 `978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7` |
| Oracle | independent CPU oracle `qwen3moe-layer0-router-cpu-oracle-v1` |
| Backend / device | `apple-mlx` / `gpu` |
| Fallback | none (`fallback_used` is only `false`) |
| Top-8 IDs | single-row `[114, 45, 99, 46, 98, 74, 102, 65]`; two-row second row `[73, 95, 114, 99, 102, 46, 108, 106]` |
| ID / order mismatches | 0 / 0 |
| Numeric mismatches | 0 |
| Max abs error | `1.239776611328125e-05` |
| Mean abs error | `2.8392920891443887e-06` |
| RMSE | `3.584568198272296e-06` |
| Deterministic repeats | 20 measured hashes (10 identical single-row + 10 identical two-row) |
| Primary raw batch-a | [record](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json) SHA-256 `b5925db8ba68d90a42507e00be6d3159457a2b97d9fc827f0200245cb20851fa` |
| Primary raw batch-b | [record](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json) SHA-256 `99346e8be81b4975cb355759be20872aefdea05baa9960f28aa272d970116801` |
| Repro raw batch-a | [record](raw/002-router-parity/f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-a.json) SHA-256 `0cc828bb77f2dca62d039c700a575ec123cef1367e1d942956f1a6fe8481c616` |
| Repro raw batch-b | [record](raw/002-router-parity/f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-b.json) SHA-256 `ce8e6d71d2a8a209d5119b3a6c886f3f1e65e2d75d4b8502a363dd44edc67a44` |
| Primary source candidate | SHA-256 `b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4` |
| Repro source candidate | SHA-256 `3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3` |

Generated summaries:

- [Markdown table](tables/002-router-parity-summary.md)
- [CSV table](tables/002-router-parity-summary.csv)
- [Median figure](figures/002-router-parity-median.svg)

Two earlier external producer candidates executed the complete bounded router
but failed independent post-processing (resource intake; clean-replication role
labels). They are preserved externally and are not result rows.

## Model-backed repeatability

Within each admitted record, the protocol's twenty measured hashes are
deterministic per case. Clean-process replications are retained inside the same
raw records. A clean-checkout reproduction at measured source `04b3502`
produced an independent candidate whose promotion identity and case output
hashes exactly match the primary admitted candidate.

## Model-backed timing and resources

Timing and resource observations are retained in the raw records and generated
tables. They describe bounded layer-0 router evaluation only. Labels retain
`first_read_new_process_os_cache_uncontrolled` for new-process reads; F32
dequantization is `not_applicable`. No tokens-per-second figure is reported.

Public-safe environment snapshots accompanying the candidate reported normal
memory pressure, nominal thermal state, admitted interference, and selected
backend/device `apple-mlx`/`gpu`.

## Unsupported interpretations

These results do not establish expert MLP execution, selected-expert
aggregation, attention or prior-layer parity in PulsarMLX, a complete
transformer layer or model, language-model-head logits, tokens, generation,
serving, full or giant model inference, projected tokens per second, custom
Metal kernels, or Linux/CUDA runtime parity of fork changes.
