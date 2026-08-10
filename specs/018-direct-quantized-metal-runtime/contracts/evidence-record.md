# Feature 018 Evidence Record Contract

Every record contains:

- schema name/version and attempt ID
- actual status and numerical classification
- clean source commit and branch
- public-safe machine class, macOS, architecture, Metal device, Rust/Python/MLX versions
- checkpoint set SHA-256 and immutable revision for Tier 3
- complete packed matrix binding and activation/reference hashes
- kernel configuration, lookup-table hashes, f32 accumulation, dispatch geometry
- explicit `complete_f32_weight_materialized_bytes = 0`
- explicit CPU fallback count
- setup timing: read, registration, compilation
- per-sample timing: dispatch, execution when independently observable,
  synchronization, total
- warmups and every retained sample
- memory/RSS/resource state before and after
- complete correctness metrics and classification inputs
- failures, unsupported interpretations, claim boundary, and next gate

Validation rejects duplicate JSON keys, negative/non-finite timing, summaries
that disagree with raw samples, missing provenance, hidden fallback, private
paths, checkpoint bytes, or unsupported capability claims.
