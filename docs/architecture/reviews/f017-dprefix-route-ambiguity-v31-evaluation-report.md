# F017 DPREFIX routing-contract v3.1 ambiguity evaluation

## Scope

This analytical event applies the frozen routing-contract v3.1 theorem to
DPREFIX-EXACT-1, the frozen REAL-2/REAL-3 componentwise ambiguity box, and the
eight artifacts authorized for consumer
`F017-DPREFIX-ROUTE-AMBIGUITY-PROPAGATION-ANALYTICAL-1`.

It is not model execution or representative M1-F0. It opened no checkpoint or
shard, dispatched no candidate, and left the real-payload ledger at 139.

## Inputs and immutability

The state-box center remains DPREFIX-EXACT-1
`9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11`.
The REAL-2 and REAL-3 members remain
`541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff`
and
`ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a`.

All eight authorized private artifacts matched their committed SHA-256 values
before and after evaluation. No absolute private path is present in public
evidence. Older v2 attention-residual and non-radial artifacts were verified
but were not substituted for the frozen v3.1 direct state-box theorem.

## Result

The exact analytical top-8 order is:

`[250, 10, 237, 73, 62, 177, 218, 28]`

All 1,984 selected/unselected inequalities have a strictly positive lower
score difference. The minimum factor is `1.180434247555598` for selected
expert 28 against challenger 26. The exact margin there is
`0.00032107808556247614`, and its outward difference lower bound is
`0.00004907811078425083`.

No pair is below mathematical factor 1. Two pairs are below engineering H=2;
1,982 pass H=2. Engineering headroom does not alter the mathematical selected
set result.

All eight ID-keyed exact routing weights lie inside their v3.1 intervals.
However, v3.1 freezes no mathematical or engineering acceptance threshold for
interval width. It is therefore not permissible to call the weights qualified
after observation.

Final disposition:

`ROUTE SET INVARIANT / WEIGHTS REQUIRE QUALIFICATION`

## Expectation comparison

The observed maximum score-interval width is `0.0033221868664057297`, wider
than the rough planning expectation near `1e-6`. The retained row-specific
reduction guards dominate the worst enclosure. The theorem and guards were not
changed after observing this result.

The complete 256-expert surface, 1,984 pair records, weight intervals,
identity bindings, deterministic replay hashes, and isolation evidence are in
`docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json`.
