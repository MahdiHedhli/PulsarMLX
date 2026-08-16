# F017 DPREFIX-REAL-2 Evidence-Validation Rejection Review

`DPREFIX-REAL-2` crossed its reviewed consumption boundary exactly once. The
committed terminal evidence records one shard open, 40 issued and completed
positional reads, 40 payloads, and `1,431,263,232` packed bytes. The real-payload
ledger therefore advances from 99 to 139. All 40 packed identities matched the
predecessor-derived hard-gate manifest, and the Q4_K and Q6_K decoded identities
matched their accepted values.

The private packed package was finalized with 40 immutable, read-only payload
objects and a retained byte count of `1,431,263,232`. Its manifest and package
identity is `705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156`.
The oracle was finalized and its Class-A layer-2 and layer-3 products were
durably persisted before candidate launch. Both retained oracle states have
content SHA-256
`541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff`;
the private oracle manifest SHA-256 is
`553e2d61bb6de3bf14b79b1ffb6140f4e03db75d4479debed2346e34e2ed021b`.
The post-candidate oracle rehash passed.

The corrected candidate launched and completed all 27 native contraction
shapes, all ten repeats were deterministic, fallback and backend-error counts
were zero, and every one of the eight paired Tier-B surfaces qualified. These
facts establish successful numerical observations, but they do not establish
an accepted terminal event.

The bound success path did not persist two fields required for terminal PASS:
complete success-path lifecycle reconciliation and actual host-copy count.
Those facts cannot be reconstructed from the immutable runtime evidence without
candidate recomputation. Under the fail-closed evidence rule, the terminal
disposition is therefore `REJECTED / EVIDENCE_VALIDATION /
SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING`. No checkpoint reread, candidate
recomputation, oracle recomputation, or retry was performed.

The authoritative raw evidence is
`docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json`,
SHA-256 `a9708c84ebe08e9c3717cd3abbaec37c15fa06cb99d2f97d5a7dc87871e79039`,
committed in `1c072ee99388e49a60392f3cc44c732a2e2a21d6`.

The retained oracle state is restricted to
`ANALYTICAL_ROUTE_PLANNING_ONLY`. Representative M1-F0 remains not authorized
and not executed. The exact next action is independent adversarial review of
the failure evidence. The checkpoint must not be reread.

Final Apple-native CI run `31979940586` is bound to the exact real-evidence
head `1c072ee99388e49a60392f3cc44c732a2e2a21d6`; its final conclusion is recorded
in the append-only CI run-to-head binding ledger.
