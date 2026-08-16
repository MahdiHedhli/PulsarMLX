# F017 DPREFIX Numerical-Surface Closure Adversarial Delta Packet

## Requested decision

Can the exact bound candidate and oracle now instantiate every field required by the frozen real Tier-B contract before any real read is authorized?

Return exactly one:

- `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

This review authorizes no checkpoint access by itself. `DPREFIX-REAL-1` remains unconsumed and the ledger remains 59.

## Review set

- frozen Tier-B: `specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-real-tier-b-v1.json`, SHA-256 `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`
- surface manifest: `docs/architecture/reviews/evidence/f017-dprefix-numerical-surface-manifest-v1.json`
- metric engine and contract: `scripts/research/f017_dprefix_metric_engine.py` and `docs/architecture/reviews/evidence/f017-dprefix-tier-b-metric-engine-v1.json`
- candidate source/build successors: `docs/architecture/reviews/evidence/f017-dprefix-candidate-source-manifest-v2.json` and `f017-dprefix-candidate-build-manifest-v2.json`
- oracle source/package successors: `docs/architecture/reviews/evidence/f017-dprefix-oracle-source-manifest-v2.json` and `f017-dprefix-instantiated-oracle-package-v2.json`
- full rehearsal: `docs/architecture/reviews/evidence/f017-dprefix-full-tier-b-synthetic-rehearsal-v1.json`
- memory admission: `docs/architecture/reviews/evidence/f017-dprefix-paired-surface-memory-admission-v1.json`
- schema v4: `specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-evidence-v4.schema.json`
- config/auth/attempt successors: `f017-dense-prefix-execution-config-v4.json`, `f017-dense-prefix-authorization-binding-v3.json`, and `f017-dense-prefix-attempt-ledger-v4.json`
- preflight/internal review: `f017-dprefix-numerical-surface-closure-preflight-v1.json` and `f017-dprefix-numerical-surface-closure-internal-review-v1.json`
- implementation/tests: `scripts/research/f017_dprefix_numerical_surface_closure.py`, `scripts/research/f017_dprefix_oracle_runtime.py`, `crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs`, and `scripts/research/tests/test_f017_dprefix_numerical_surface_closure.py`

## Reviewer checks

1. Confirm the prior blocker was valid and both prior non-consuming refusals remain immutable.
2. Derive the eight surfaces from Tier-B rather than trusting this packet.
3. Verify every surface has semantically aligned candidate and oracle producers.
4. Verify metric-bearing surfaces cannot be hash-only and the final state remains full-value retained.
5. Verify the metric engine derives results from paired bytes and does not trust producer PASS flags.
6. Verify candidate instrumentation is observational and predecessor/successor model-semantic hashes are exact.
7. Verify oracle arithmetic is unchanged and no candidate/MLX/Rust dependency was introduced.
8. Recompute or spot-check every production-width rehearsal metric and its threshold.
9. Review the `7.771561172376096e-16` cosine-method delta attribution; confirm canonical f32 outputs are unchanged.
10. Mutate a surface at each major stage and confirm localized failure plus overall failure.
11. Confirm schema v4 requires all eight unique surfaces and complete diagnostics.
12. Recompute paired-value memory overhead and confirm 27 GiB remains conservative.
13. Confirm `DPREFIX-REAL-1` remains the same authorized, unconsumed real-budget identity.
14. Confirm config v4 and authorization v3 preserve all execution semantics and prohibit retry/M1-F0 chaining.
15. Confirm canonical preflight checks full Tier-B instantiability and performs zero checkpoint reads.

## Release boundary

A GO verdict releases exactly one later 40-read `DPREFIX-REAL-1` execution under the bound successor candidate, oracle, surface manifest, metric engine, and evidence schema. It does not authorize M1-F0 or any downstream phase.
