# Contract v3 population: 41 cases

Inherit the two full-shape positives and 13 mutations from population-v2.md,
with identical original input and all nine payload components per positive.
Inherit all 24 refusal cases. Add two host framing refusals, applied to the
full-shape positive A header before any numerical import:

- `framing-missing-scope`: remove the top-level scope; strict keys must refuse.
- `framing-wrong-scope`: replace it with `numerically qualified`; exact scope
  predicate must refuse.

Every positive snapshot includes the original capture writer's top-level scope
literal. Counts are 2 positives, 26 refusals, 13 mutations, total41. All case IDs
and edits are frozen in the generated manifest and source review descriptor.
Native work remains9QMM plus12activation calls. These extra host controls make
no native calls. This document supersedes only framing and counts in v2; fixed
budgets, analytical positive proofs, nonzero signal and mutation predicates are
unchanged. Small actual-writer compatibility tests establish schema agreement,
not full-shape admission or numerical qualification.
