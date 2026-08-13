# F017 M1-E Attempt 2 Evidence Review

**Verdict: M1-E ATTEMPT 2 REJECTED**

## Identity and admission

The config-only launcher validated compiled runtime/tooling
`5c7694d6ba48640279e4725ea96104bc179a62cb`, authorization head
`f8a9910ca1c9242c2638556b0daee6a11949a090`, reviewed repository head
`48e30ae4df9c0187bebcd9f6be377331099c86f9`, release executable
`13900ecc2ea5b252c4a83b69ae04ee6b20916a7f3c0133c1b87c9a5c720b2bab`,
and immutable execution config
`a8905b8709aadf8d36bf94c2cb54c14a9ce5bcd31e7a1b184da33127af300f4e`.
Trusted-repository identity v2, ancestry, runtime-drift classification, clean
checkout, remote parity, and direct artifact hashes passed. The canonical
non-consuming preflight returned exactly `READY_TO_EXECUTE_M1_E`.

Live admission passed on arm64 with measured-host telemetry: 128 GiB physical
memory, 95% free memory, normal pressure, 0.12 MiB swap used, safe storage,
no competing inference or port-1234 listener, and no thermal/performance
warning. Actual `libmlx.dylib` and `libmlxc.dylib` hashes matched the pinned
installation.

## Consumed attempt and first failure

Attempt 2 transitioned exactly once to `EXECUTION_STARTED`; its exclusive
state marker hashes to
`a8f0c1644bdf2786818a6de9f291b661544affa0ccc333ae4631c3d81e9dd4ef`.
The independent preparer then rejected the immutable config at its identity
gate with `M1-E execution config identity mismatch`.

The exact incompatibility is structural: the rebuilt identity-v2 config uses
schema `3.0.0`, while the bound preparer accepts only schema `2.0.0`. That
check is performed before the preparer resolves or opens the checkpoint
shard. Classification is `FAIL_INFRASTRUCTURE_EVIDENCE`; first-failure code is
`m1e_oracle_execution_config_identity`.

## Access, execution, and isolation

- real checkpoint/shard opens/positional reads/payloads/bytes: `0/0/0/0/0`
- independent oracle/package: absent
- candidate decoded matrix hashes: absent
- candidate start: false
- conceptual experts/repeats/native matvec dispatches: `0/0/0`
- production scaffold/reference/fallback/backend errors: `0/0/0/0`
- router, second/shared expert, layer, logits, P1/P2/golden-eight, Feature 018:
  all zero or false
- MLX lifecycle context/streams: not created
- numerical metrics/classification: not reached

No raw or decoded checkpoint bytes were produced by attempt 2. The packed and
decoded hashes in the public evidence are authorization bindings, not newly
observed attempt-2 payload identities.

## Disposition

The public-safe evidence artifact is
`docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-2-v1.json`
with SHA-256
`8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.

Attempt 1 remains immutable and rejected at `m1e_down_decoded`; attempt 2 is
now immutable, consumed, and rejected before checkpoint access. There was no
retry, alternate command, decoder substitution, or candidate compute. M1-F is
neither prepared nor authorized. The exact next action is a new, separately
reviewed remediation that makes the independent preparer accept and validate
the identity-v2 config schema, followed by a distinct fresh authorization;
this report does not authorize it.
