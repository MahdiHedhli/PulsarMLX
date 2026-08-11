# F017 Canonical Runner Internal Review

## Prior verdict

`GO WITH REQUIRED FIXES BEFORE M1-A/B` at reviewed source
`74cd1f3af3538dfdff0fa1343542a9ec7656c0ef`.

The review accepted the Rust-native architecture, production `MlxContext`
adapter, split store, complete 1,809-contract tensor map, checkpoint-free
R7-R12 numerical basis, and lifecycle design. It did not authorize M1-A/B
because production environment/admission proof, loaded-library identity,
identity-mode map validation, lifecycle applicability, and R12 accounting and
claims required remediation.

## Remediation submitted for follow-up review

The complete finding-to-code-to-test map is in
[`f017-pre-m1-ab-remediation-review-packet.md`](f017-pre-m1-ab-remediation-review-packet.md).
In summary:

- production M1-A/B collect real admission state and fail closed;
- the reviewed environment manifest has a strict schema and the actually
  loaded MLX native/C files are resolved, architecture-checked, and hashed;
- evidence paths are exclusively acquired;
- PASS follows explicit teardown and reconciliation;
- lifecycle observation state distinguishes measured zero from not applicable;
- production M1-B validates `Glm52TensorMap::from_gguf` without tensor compute;
- production R12 no longer invokes the exact scaffold and binds the full
  inherited contract set; and
- runtime-reuse wording now describes the literal fixture-specific
  composition.

## Task and admission state

T017-160 remains open until this internal review reruns and returns GO.
T017-161 remains open pending the independent review. T017-140 and T017-141
also remain open. No checkpoint was accessed; M1-A/B, M1-C, and P1 remain
blocked.

## Requested follow-up verdict

Return exactly one:

- `GO FOR M1-A/B STAGED INTEGRATION`
- `GO WITH REQUIRED FIXES BEFORE M1-A/B`
- `NO-GO`

A GO admits only preparation for a separately authorized M1-A. It does not
authorize M1-B without M1-A evidence review, and never authorizes M1-C or P1.
