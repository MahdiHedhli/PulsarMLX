# PulsarMLX F017 Numerical Classification Remediation

## Executive result

The R7/R8 adversarial review's required machine-readable vocabulary fix is
implemented without rerunning a numerical experiment. The classification
contract now distinguishes a qualified boundary with no model-token greedy
decision from one that proves exact top-k and argmax identity.

This remediation does not admit a checkpoint, P1, Feature 018 kernel, or
output-head residency experiment.

## Source

- Starting source: `a572a2d560f5bc33f823e74c3bbc95ff2b164314`
- Branch under remediation: `feat/017-real-checkpoint-runner`
- Isolated remediation branch: `codex/f017-numerical-vocabulary`
- Checkpoint access: none
- Numerical reruns: none

## Vocabulary and invariant

The retained classes are:

- `golden_identical`
- `numerically_qualified_greedy_not_applicable`
- `numerically_qualified_greedy_identical`
- `numerically_qualified_greedy_divergent`
- `numerically_failed`

`numerically_qualified_greedy_not_applicable` requires
`greedy_applicability: not_applicable` and forbids greedy-identity evidence.
`numerically_qualified_greedy_identical` requires
`greedy_applicability: applicable` plus exact top-k and argmax identity
evidence. A changed applicable decision may be recorded as greedy-divergent
under teacher-forced validation; it can never be labeled not-applicable.

The invariant is implemented in the Rust runner evidence validator, canonical
JSON schema 1.2.0, and a duplicate-key-safe Python evidence validator. Both
positive and negative tests cover all reviewer-required combinations.

## R7-R10 reconciliation

R7, R8, R9, and R10 are reclassified from
`numerically_qualified_greedy_identical` to
`numerically_qualified_greedy_not_applicable`.

- R7 has no selection boundary.
- R8 retains exact routed IDs `[7, 6, 5, 4, 3, 2, 1, 0]`, but those are expert
  routing selections rather than a model-token greedy decision.
- R9 retains exact DSA/indexer selection evidence without conflating it with
  vocabulary argmax.
- R10 retains exact routed-expert IDs without conflating them with vocabulary
  argmax.

The frozen Tier-B thresholds and exact requirements are unchanged. Internal
router or indexer selection drift remains fail-closed numerical failure at
these boundaries.

## Numerical-payload proof

The deterministic reconciliation manifest is
`docs/architecture/reviews/evidence/f017-numerical-classification-reconciliation-v1.json`.
It compares each working artifact with baseline
`a572a2d560f5bc33f823e74c3bbc95ff2b164314`, permits only top-level
`classification` and `greedy_applicability` changes, and records matching
normalized numerical-payload hashes.

| Boundary | Old artifact SHA-256 | New artifact SHA-256 | Unchanged numerical-payload SHA-256 |
|---|---|---|---|
| R7 | `fb6d3399e47fbfa7445860c620ddf0d9a0e4c0be5522fa8b0051f259f2242e45` | `e7e87796aaa4f7ab94b8605dd2aab680d0a69c42978cedb0b5673696ac0d71c8` | `c0e42c98bd8f3f27ad496769eff0177463d0bfefc1fd81364fabbdc9853e7336` |
| R8 | `427a3f2caf76bcb8e54cb5d8a853c0e26e4ec5989cb8afb612e76c98644ac4e4` | `445e6015f275e0afc29a19db79cf0ec88e6445ea2cc975dece808d17ffb9152e` | `7d65d99cbd39a06be5f3f07e1e1d7b1276919f855c428fbc8406cc4ae042f216` |
| R9 | `b37a5b9705176d353e0ef3132954ff214d12fda25e2e6881628f665ade50c792` | `26b576cf21047982c6b0b09019ffcb0ec58f24d2ea50f64f959f5a87b1eebc1b` | `f44756739abd0c0a080530cc39aa01f8431ba931683c35dbc2c8724bd5ab22ea` |
| R10 | `c8ffaafc28b32592eed0c205bced51c83555fd8d507a0276a3a534652e84b34d` | `2aeb727fc86b3435bb77c3f362ca84fb4499858951b60a9445c27e87d8a8f2d1` | `d1e605fa363bcac7f7375a926a563d528ef4542f1c95b0c273390ebf9689db83` |

No metric, threshold, fixture datum, oracle datum, production output, dispatch
counter, fallback counter, or lifecycle counter changed.

## R11 readiness semantics

R11 is the first planned boundary where model-token greedy identity is
applicable. It may use `numerically_qualified_greedy_identical` only when:

- logits satisfy the frozen numerical contract,
- top-k IDs and ordering match exactly,
- argmax matches exactly, and
- the evidence records `greedy_applicability: applicable` plus both identity
  booleans.

Missing identity evidence or a changed decision fails closed.

## Review and downstream status

The underlying numerical review verdict is **GO WITH REQUIRED FIXES**. The
required code, schema, evidence, and prose repair passed GitHub Actions run
[`31521791761`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31521791761)
at `bc5922626df9eaed8d1e843d021b268ecf50579d`: the workspace baseline passed
in 2m06s and the Apple native MLX job passed in 5m28s. Native adapter and
R7-R10 numerical tests executed rather than skipping.

The review blocker is resolved. R7/R8 contract inheritance is accepted,
R9/R10 are promoted from pending numerical review, and checkpoint-free R11/R12
remain the next eligible gates. The real checkpoint and P1 remain blocked.
