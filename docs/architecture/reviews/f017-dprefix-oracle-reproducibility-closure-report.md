# PulsarMLX F017 DPREFIX Oracle-Reproducibility Closure Report

- Starting SHA: `6d30b7d26fcc563be85b75909890676efee5096e`
- Final preparation SHA: `PENDING_FINAL_PREPARATION_COMMIT`
- REAL-2 state SHA: `541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff`
- REAL-3 state SHA: `ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a`
- Byte-delta statistics: `5080` differing f32 elements; first index `0`; max abs `7.450580596923828e-09`; RMSE `1.68139073109024e-09`; cosine `0.9999999999999876`; no sign or zero changes.
- First divergent surface: `layer_0_attention`
- BLAS thread/process campaign: `CROSS-PROCESS ORACLE REPRODUCIBILITY CHARACTERIZED`; `NO THREAD-COUNT VARIANCE OBSERVED`; CPython 3.13/Accelerate reproduces REAL-2 and CPython 3.14/OpenBLAS reproduces REAL-3.
- Demonstrated root cause: platform-wheel BLAS backend/reduction realization changed despite identical source, NumPy version, and inputs.
- Exact-scaffold contract SHA: `5c0a23cabe15d9f80be2a9d3ebb84f9fc5c32d3a0a2b1b74c2b746c2728e59f3`
- Exact implementation identities: C `e1e84fe90f768ec62d8c4b523d89afae94ce9d0d9186f736fe7cb2c476f8b3f2`; Rust `cb5064916a98c7adb22d780121dd09a32ee9d4acd555b573e5a112a98af17f1d`
- DPREFIX-EXACT-1 SHA: `9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11`
- Exact fresh-process reproduction: `DPREFIX-EXACT-1 BITWISE SELF-REPRODUCIBLE` across two implementations and four fresh processes.
- Exact vs REAL-2: max abs `1.1175870895385742e-08`, RMSE `2.1970225400794876e-09`, cosine `0.9999999999999779`.
- Exact vs REAL-3: max abs `1.1175870895385742e-08`, RMSE `2.232408575689947e-09`, cosine `0.9999999999999774`.
- Exact vs candidate: max abs `8.195638656616211e-08`, RMSE `1.0581641666683089e-08`, cosine `0.9999999999995107`; frozen final Tier-B remains PASS.
- Identity-gate v2 SHA: `dc4bf4e9e1a8cc15f8737a11a607d15f9b8b0052a35a391fa20b9b65720f4dd4`
- Gate-class audit: `10` gates; `{'EXACT_CLASS': 5, 'PERSISTED_AUTHORITY': 4, 'BOUNDED_CLASS': 1}`; one historical BLAS exact-recomputation gate misclassified, with REAL-3 unchanged.
- Route ambiguity bound: componentwise L-inf `1.1175870895385744e-08`, L2 `2.0736155800732253e-07`, L1 `1.387169322697446e-05`.
- Router-logit ambiguity bound: `NOT_DERIVABLE_FROM_COMMITTED_RETAINED_BYTES`.
- v3 membership minimum factor: `NOT_COMPUTED` (`0/1,984` inequalities proven).
- Worst membership pair: `NOT_COMPUTED`.
- Routing-weight robustness: `NOT_PROVEN`.
- Route-insensitivity disposition: `ROUTE NOT PROVEN INVARIANT`.
- Replay-necessity disposition: `OPTION A — no further dense-prefix replay required`; route proof requires restored/reviewed route inputs rather than another dense-prefix replay.
- Checkpoint access: `0`
- Real-payload ledger: `139`
- Internal verdict: `BLOCKED — ROUTE INSENSITIVITY`
- Adversarial packet SHA: `2ca05920ef7505cada043f7a743208ffe0c3c7fa6848cf2986421841cff08f41`
- Final CI run/head: `PENDING_FINAL_HEAD_CI`

The committed v2 antecedent manifest describes the router matrix and norm artifacts, but the load-bearing private bytes are absent. More importantly, that package retains old-input attention/router antecedents rather than the layer-3 attention tensors or a reviewed global attention propagation bound needed for a new dense-prefix ambiguity set. Reconstructing either from hashes would violate the fail-closed contract; opening the checkpoint is forbidden.

## Exact next action

Restore and independently verify the already-reviewed private route-propagation artifacts, or prepare a checkpoint-free reviewed package containing the missing layer-3 attention and router propagation surface. Then complete all 1,984 v3 membership inequalities and weight intervals before independent adversarial review. No DPREFIX replay, M1-F0, M1-F, or checkpoint access.
