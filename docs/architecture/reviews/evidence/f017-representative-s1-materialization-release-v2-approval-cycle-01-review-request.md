# F017 representative S1 release-v2 approval review — cycle 1

Review only committed bytes on branch `feat/017-real-checkpoint-runner` at the
exact clean `HEAD` present when this committed request is invoked. Record that
target in the review. Repository bytes are authoritative. Do not
modify implementation artifacts, do not reconstruct or materialize S1, and do
not access checkpoint or shard payloads.

## Immutable target

- approval-bearing authority head: `fe644ce672ab6705931d2ae427a3ef34cb7b2804`
- approval path: `docs/architecture/reviews/evidence/f017-representative-s1-materialization-single-use-release-v2-independent-approval-v1.json`
- approval SHA-256: `e2729bb1c8aee5ef8cc1b9920bfa832c4eb2ffcb72b782e8df20af1698f36108`
- release-v2 SHA-256: `c441f956122cba6866a6729248d092584c4b1ee7e9d574bd98cffe9d74247424`
- authorization SHA-256: `f2efce04a1047d0e31b16f44e976a8b2b3102b340a6e3adfac32dfdf73f3ce0f`
- accepted release-review SHA-256: `bd56546e21f8291864afbc0775681d63113f1629178c53ca49e7c8e79ae541d7`
- accepted release-review target: `f0165acdae302aee3709070288af3178045de4c0`
- required reviewer model: `claude-fable-5`

## Independent adjudication

Independently inspect the exact committed approval, release, authorization,
wrapper v2, release review, and their SHA-bound transitive dependencies. Test
claims from committed bytes rather than trusting builder prose. At minimum:

1. derive the wrapper-enforced approval schema and verify the approval has
   exactly that schema, with no missing or extra fields;
2. verify release-v2, authorization, expected S1, execution-code, reviewed-head,
   accepted release-review SHA/model/verdict, ledger, accounting, and boundary
   authority are enforced either directly by the approval gate or transitively
   through exact SHA-pinned committed authorities;
3. verify the chain release -> review -> approval -> machine-local token is
   acyclic, fail-closed, and keeps approval distinct from execution authority;
4. verify release v1 cannot satisfy the v2 gate;
5. verify the approval permits no checkpoint/shard access, new attention event,
   FFN composition, S2 construction, materialization, attempt creation, or token
   consumption by itself;
6. verify a future exact eight-field token can authorize at most one S1
   materialization and that the stop boundary remains
   `AFTER_REPRESENTATIVE_S1_RETENTION_ONLY`.

Classify every finding as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or
`DEFENSE_IN_DEPTH`. Both first classes require `REJECT`. Return `ACCEPT` only
when neither remains. Do not fix findings.

Write the exact JSON review artifact directly to:

`docs/architecture/reviews/evidence/f017-representative-s1-materialization-release-v2-approval-cycle-01-independent-review.json`

The JSON must record the actual reviewer model, exact reviewed head, approval
path/SHA, release/review identities, tests or inspections performed, findings,
verdict, counter observations, and an explicit answer to whether the committed
approval is sufficient for a later machine-local token readiness phase without
executing or materializing S1. Print the artifact path, SHA-256, verdict, and
actual reviewer model after writing it.
