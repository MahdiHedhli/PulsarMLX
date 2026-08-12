# F017 M1-D Packet/Provenance Closure

## Narrow adversarial delta verdict

**GO FOR FRESH M1-D AUTHORIZATION**

Scope was limited to tooling-head binding, provenance separation, activation
continuity, real-reference-preparer binding, immutable handoff binding, direct
contract bindings, and fail-closed packet validation. No runtime compute,
numerical contract, activation payload, checkpoint payload, or M1-D execution
changed.

## Source boundaries

- previous reviewed head: `9d355cc3e1da55696a47b02170b40bd7bb5aeea7`;
- runtime: `d68cb10758693dc61d3af7cf76b8019f6b3b235d`;
- tooling/validator boundary: `15c0de64c342cb5541e643f5e212d2cf5d73da67`;
- old handoff SHA-256:
  `b6f0dab4e69d972d943d69e8981b2ecbe094e16794edfe89ab5cd47ef1a86498`;
- repaired handoff SHA-256:
  `eff56978ed066527dd9e42689b23c4f7a033b4f0dd5ed1815ee001d95bc5d789`.

The final authorization documentation is intentionally a documentation-only
descendant of the tooling boundary; a commit cannot contain its own SHA. The
machine-readable binding validates that only the authorization, readiness,
and closure documents may follow the bound tooling commit.

## Provenance closure

| Role | Commit | File SHA-256 | Disposition |
| --- | --- | --- | --- |
| Activation generation | `992081315073d8eb4eb31a2bb2f1b7b77b9c0ccd` | `29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984` | Created the frozen activation bytes |
| Fixture finalization | `d68cb10758693dc61d3af7cf76b8019f6b3b235d` | `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92` | Added structural finalization metadata; activation bytes unchanged |
| Real-reference preparation | `d68cb10758693dc61d3af7cf76b8019f6b3b235d` | `bdcf8b999de5426872cb31f971b455028746959b30fb2bdf4c2f750f335b7fea` | Controls the future bounded real oracle/package |

Historical and current fixture bytes are identical at SHA-256
`dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`.

## Review questions

1. Runtime and tooling SHAs distinct: **yes**.
2. Tooling SHA exact/current: **yes**, `15c0de64...`.
3. Three provenance roles unambiguous: **yes**.
4. Activation bytes unchanged: **yes**.
5. Real-reference preparer frozen: **yes**.
6. Handoff immutable by SHA: **yes**.
7. All execution-controlling hashes directly bound: **yes**.
8. Stale handoff/generator can silently change execution: **no**.
9. Validators fail closed: **yes**, including independent mutations and the
   legacy generic-generator ambiguity case.

## Authorization disposition

The packet is `AUTHORIZED FOR EXACTLY ONE M1-D ATTEMPT / NOT EXECUTED`.
M1-D attempts remain zero; the real M1-D matrix remains unaccessed. M1-E,
T017-141, P1/P2/golden-eight, and Feature 018 remain blocked.
