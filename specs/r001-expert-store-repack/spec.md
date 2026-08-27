# R001: Expert Store Repack

## Scope

R001 repacks byte-identical GLM GGUF expert components into deterministic,
independently addressable `(layer, expert)` bundles. It does not alter tensor
bytes, quantization, shapes, inference numerics, F017 state, or model-output
claims. A complete checkpoint repack is explicitly outside the foundation
graph.

## Mandatory gates

1. Isolated standalone clone from current `origin/main`.
2. Live source-layout inventory with byte-confirmed coverage.
3. Independent bundle-format and verification designs.
4. Adversarial design acceptance before implementation.
5. Bounded Rust copy path and independent verifier.
6. Bounded fixtures plus one complete representative routed-expert layer.
7. Evidence-backed read-pattern benchmark.
8. Independent final acceptance.

## Current state

`R001_FOUNDATION_BLOCKED_SOURCE_CHECKPOINT`

The six-shard source checkpoint is not present on ColPanicM2. Committed F016
catalog facts permit metadata-only estimates but cannot satisfy the live-byte
inventory gate. No format design or implementation is admitted until the
existing checkpoint is mounted or otherwise made locally readable without a
new full-checkpoint download.
