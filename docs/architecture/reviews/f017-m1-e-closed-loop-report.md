# PulsarMLX F017 M1-E Closed-Loop Report

## Verdict

`M1-E ACCEPTED`

The loop began at repository head
`a279c0758e3388f15b328c49f91941dd5372e6aa`. Attempts 1 and 2 remained
preserved rejections. Attempt 3 accepted the frozen `blk.3.expert.15` boundary;
attempts 4 and 5 were not needed or authorized.

## Closed-loop history

| Item | Verdict | Evidence / record | Primary class | Remediation |
|---|---|---|---|---|
| attempt 1 | REJECTED | `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119` | `DECODER_IDENTITY` | corrected independent IQ3_XXS grid ordering; decoder v2 |
| attempt 2 | REJECTED | `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00` | `CONFIG_SCHEMA` | preparer-input v3 and schema-confusion regressions |
| attempt-3 preflight | unconsumed blocker | append-only ledger | `INFRASTRUCTURE` | bound and hash-verified native loader environment |
| attempt-3 identity rebuild | unconsumed blocker | append-only ledger | `IDENTITY_BINDING` | republished exact runtime/tooling identity and config |
| attempt 3 | ACCEPTED | `0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9` | PASS | none after execution |

The loader remediation added a fail-before-checkpoint regression for binaries
without `LC_RPATH`, scrubbed ambient dyld overrides, and derived the only loader
directory from the already hash-bound production environment manifest. Internal
and adversarial review verdicts were both exactly `GO FOR NEXT M1-E ATTEMPT`.
Apple-native CI run `31720986490` was green at exact head
`541da1abdbb1767fba9917894adb07c9c93d0ab1` and exercised the canonical
synthetic one-expert, ten-repeat, thirty-dispatch M1-E gate plus M1-D, decoder,
oracle-order, and lifecycle regressions.

Runtime/tooling evolved from
`71476f0d469214c96d803ce4917c43c4562a7183` to
`7e4c3f37049444443164964aea2fc630752d17ce`. The accepted immutable config is
`8213c5fa1c59900a0590977079d0d88f5b55d0faa30e2fa262430271bc3cef2a`.
Decoder v2, activation, scaffold, Tier-B formula, final oracle, and final bound
vector did not change during this closed-loop run.

## Accepted attempt

Attempt 3 read exactly three payloads through one shard open and three
positional reads totaling 11,304,960 bytes. Packed and decoded identities all
matched. The independent oracle package SHA-256 is
`e500f0f9edca67ae42b3302bdb4105ded044a8b42c755aa58abee9af7302dbff`;
structural and timestamp ordering both prove finalization before candidate
start.

Ten complete repeats produced identical gate, up, activated-hidden, and final
hashes. Native dispatches reconciled at 30 with zero scaffold/reference,
fallback, or backend-error dispatches. Final maximum absolute error was
`0.000053882598876953125`, RMSE `0.000013008547444591869`, and cosine
`0.9999999999963376`. Lifecycle reconciled and all isolation counters passed.

Across the closed-loop prompt, one real attempt was consumed, three real tensor
payloads were read, and no attempt 4/5 was launched. M1-F is prepared at
`docs/architecture/reviews/f017-m1-f-real-layer-handoff.md` with status
`PREPARED / NOT AUTHORIZED`; it was not executed.

The exact next action is a separately authorized M1-F admission-package
preparation sprint. T017-141, P1/P2, golden-eight, logits, and Feature 018
integration remain blocked.
