# PulsarMLX F017 DPREFIX-REAL-3 Rejected Evidence Review

`DPREFIX-REAL-3` executed exactly once from the immutable retained packed package with zero checkpoint reads, zero shard opens, and the real-payload ledger unchanged at `139`.

The candidate completed ten deterministic repeats. All 40 decoded identity gates, all eight Tier-B numerical rows, runtime accounting, lifecycle reconciliation, and oracle post-candidate rehash passed. The event is nevertheless terminally rejected: the freshly recomputed oracle layer-3 state is `ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a`, while the released identity gate required `541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff`.

| Surface | Max abs | RMSE | Cosine | Tier-B |
|---|---:|---:|---:|---|
| `embedding` | `0.0` | `0.0` | `1.0` | `true` |
| `layer_0_attention` | `1.862645149230957e-08` | `9.677885755940546e-10` | `0.9999999999999835` | `true` |
| `layer_0_output` | `1.043081283569336e-07` | `9.695351922438437e-09` | `0.9999999999995636` | `true` |
| `layer_1_attention` | `8.498318493366241e-09` | `1.139565125099775e-09` | `0.9999999999993312` | `true` |
| `layer_1_output` | `7.82310962677002e-08` | `1.1918339595948842e-08` | `0.9999999999992429` | `true` |
| `layer_2_attention` | `1.210719347000122e-08` | `1.2162889371924948e-09` | `0.9999999999994829` | `true` |
| `layer_2_output` | `7.450580596923828e-08` | `1.0915477116554512e-08` | `0.9999999999994807` | `true` |
| `layer_3_entry` | `7.450580596923828e-08` | `1.0915477116554512e-08` | `0.9999999999994807` | `true` |

- Terminal class: `EVIDENCE_VALIDATION`
- Reason code: `ORACLE_STATE_IDENTITY_MISMATCH`
- Runtime-derived host copies: `4050` / `10145280` bytes
- Lifecycle: `PASS`
- Raw evidence: `docs/architecture/reviews/evidence/f017-dprefix-real3-rejected-oracle-state-identity-v1.json` / `0e7f146b7a1491c0ad0b036b031299f4b4ebceb5e9c96fafb6bcdc30bfc60884`
- Replay attempt ledger: `docs/architecture/reviews/evidence/f017-dense-prefix-replay-attempt-ledger-v2.json` / `0f27778e2f7846972f002abd2713a4ac992831065d2e890f17f1804a774e797b`
- Real-payload ledger: `docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json` / `fc32161d30373840126835e8f925179e606c792368131b06647f7cb6f50666b2` (`139 → 139`)
- Representative M1-F0: `NOT_AUTHORIZED_NOT_EXECUTED`

## Exact next action

Independent adversarial review of the terminal failure evidence. No retry.
