# F017 DPREFIX Infrastructure-Closure Adversarial Packet

## Review boundary

This is a checkpoint-free delta review of the two infrastructure surfaces
missing from the earlier `DPREFIX-REAL-1` release. It does not re-authorize or
execute checkpoint access. Ledger authority remains 59.

Review the report at
`docs/architecture/reviews/f017-dprefix-infrastructure-closure-report.md` and
the following machine evidence:

- `docs/architecture/reviews/evidence/f017-dprefix-candidate-source-manifest-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-candidate-build-manifest-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-oracle-source-manifest-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-instantiated-oracle-package-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-unconsumed-attempt-continuation-v1.json`
- `docs/architecture/reviews/evidence/f017-dense-prefix-execution-config-v3.json`
- `docs/architecture/reviews/evidence/f017-dense-prefix-authorization-binding-v2.json`
- `docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v2.json`
- `docs/architecture/reviews/evidence/f017-dprefix-infrastructure-closure-preflight-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-actual-binary-synthetic-rehearsal-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-candidate-oracle-synthetic-parity-v1.json`
- `docs/architecture/reviews/evidence/f017-dprefix-concrete-memory-admission-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-evidence-v3.schema.json`

The prior non-execution evidence remains immutable at SHA-256
`b8495bd1a4129efc7e24c687289bcb3be7af7f153e24d45ccffdccb79e79d60a`.

## Questions

1. Was stopping before consumption mandatory?
2. Did the original release genuinely omit a candidate executable identity?
3. Did it genuinely omit an instantiated oracle package?
4. Is the exact production candidate now source- and binary-bound?
5. Is the candidate executable scope sufficiently narrow?
6. Is the oracle package concrete, immutable, and source-bound?
7. Are candidate and oracle genuinely independent?
8. Can any load-bearing code be generated after release?
9. Is `DPREFIX-REAL-1` still valid and unconsumed?
10. Does preflight reject executable/package drift?
11. Does the actual candidate binary pass synthetic ten-repeat, lifecycle, and dispatch rehearsal?
12. Is layer-3 retention operational for exactly 6,144 canonical f32 values?
13. Is the 27 GiB floor still sufficient?
14. Is the real-payload ledger still 59?
15. May exactly one real dense-prefix execution now be released?

## Required verdict

Return exactly one:

- `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO permits only a later fresh explicit instruction for `DPREFIX-REAL-1`. It
does not itself access the checkpoint or authorize M1-F0 or downstream work.
