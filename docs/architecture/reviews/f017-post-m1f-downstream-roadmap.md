# F017 Post-M1-F to P1 Checkpoint-Free Roadmap

## Disposition

`DOWNSTREAM_PREP_READY`

This is route-independent preparation only. It accessed zero checkpoint
payloads, leaves the real-payload ledger at `57`, and neither authorizes nor
executes M1-G, M1-H, P1, Q6_K, or Feature 018.

## Repository-derived gate sequence

The repository defines M1-A through M1-G as separately reviewed gates and
calls the separately reviewed one-P1 authorization/command gate M1-H. The
remaining sequence is therefore:

| Gate | Exact boundary | Dependency class | Current state |
|---|---|---|---|
| M1-F | one complete real layer-3 candidate | `ROUTE_DEPENDENT` | blocked on representative route and decoder gates |
| M1-G | real final RMSNorm, output-head logits, top-k, argmax | `REQUIRES_M1_F_ACCEPTANCE` | schema prepared; boundary not authorized |
| T017-141 | publish literal canonical P1 command | `REQUIRES_M1_F_ACCEPTANCE` | open until M1-A through M1-G review gates pass |
| M1-H | fresh independent review and one-P1 authorization | `REQUIRES_NEW_REAL_ACCESS` | blocked |
| P1 | one canonical real one-token production run | `REQUIRES_NEW_REAL_ACCESS` | blocked |

There is no separately named gate between M1-G and M1-H in the current plan or
task list. M1-G is not yet specified deeply enough to execute: it still needs
an independently frozen real final-hidden input boundary, real-byte Q4_K
output-head qualification, full `output.weight` payload/memory admission, and
a real-shape numerical contract derived from (but not silently equated with)
R11. This is now an explicit blocker rather than work hidden behind M1-F.

Feature 018 is not a dependency for the first F017 P1 and remains disabled.
Output-head residency experiments are also deferred; however, measured memory
admission for the actual output head remains mandatory.

## T017-141 and canonical P1 field audit

Known, but not assembled into a command:

- binary: `f017-glm52-runner`;
- tokens: `[9703]` (`P-MIN`, `Hello`);
- continuation: `--n-new 1`;
- expected golden token: `21615`;
- validation: `golden-strict`;
- numerical path: `production-mlx-tier-b`;
- environment kind: `production_reviewed`.

Still unresolved at publication time:

- reviewed executable identity;
- fresh M1-H authorization head and attempt number;
- symbolic checkpoint and environment manifest bindings;
- measured memory floor and reviewed stream mode;
- fresh evidence destination;
- accepted M1-F and M1-G evidence hashes.

The literal command remains intentionally unpublished. T017-141 cannot close
until M1-A through M1-G have each passed their review gates.

## Downstream admission scaffolding

The following route-independent objects are now present:

- typed M1-G/P1 execution-config schema:
  `specs/017-rust-native-inference-runtime/contracts/f017-downstream-execution-config-v1.schema.json`;
- M1-G/P1 evidence schema:
  `specs/017-rust-native-inference-runtime/contracts/f017-downstream-evidence-v1.schema.json`;
- prepared, unauthorized M1-G and P1 evidence templates under
  `docs/architecture/reviews/evidence/`;
- a fail-closed validator that requires repeat equality, zero in-flight/stale,
  zero fallback/errors, teardown, declared analytical retention, and
  public-safe paths before PASS.

M1-G retention predeclares a full logits/private-artifact identity, top-N
window, top-1/top-2 margin, token ranking, and tie-sensitive state. P1
predeclares token-choice margin, gate confidence, and failure-localization
summaries. Attempt numbers, authorization, budgets, and model identities remain
null and cannot be supplied through loose CLI overrides.

## Honest dense-prefix fallback

The provisional gate is:

`F017 M1-FPREP REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY`

It is not fixture generation. It executes the real token embedding and complete
dense transformer layers 0, 1, and 2, then captures the exact layer-3 entry
state. The precommitted checkpoint-independent input is the existing F016
`P-MIN` token `[9703]` at position zero. Position zero uses
`range_fill([0])`, so the DSA indexer payloads are not part of this exact
boundary.

Catalog-only derivation yields:

| Measure | Exact planning value |
|---|---:|
| Tensor payloads / positional reads | 40 / 40 |
| Shards | 1 (`00002-of-00006`) |
| Packed bytes | 1,431,263,232 |
| Decoded-f32 upper bound | 8,504,653,824 |
| Largest decoded tensor | 3,806,330,880 |
| Mechanically countable native projection calls | 28 |

The 28 projection calls are one embedding lookup plus nine large projections
per dense layer. It is a source-backed planning reconciliation, not a frozen
native dispatch budget: the candidate real dense-prefix path and residency plan
are not yet admitted.

| Family | Tensors | Packed bytes | Decoded bytes | Real-byte status |
|---|---:|---:|---:|---|
| F32 | 12 | 178,176 | 178,176 | qualified at M1-C |
| Q8_0 | 12 | 165,027,840 | 621,281,280 | qualified at M1-D |
| Q5_K | 12 | 544,997,376 | 3,170,893,824 | qualified by M1-F0 Q5_K evidence |
| Q6_K | 3 | 185,794,560 | 905,969,664 | `UNQUALIFIED_REAL_GATE` |
| Q4_K | 1 | 535,265,280 | 3,806,330,880 | `UNQUALIFIED_REAL_GATE` |

Thus the fallback needs both Q4_K and Q6_K real-byte qualification. Its oracle
is feasible in principle, but materially broader: independent embedding plus
three dense MLA/DSA+FFN layers, exact caches/state, and a repeat contract.

The exact 40-entry table is deterministically produced by
`dense_prefix_inventory()` from catalog SHA-256
`135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19`.
The public summary is
`docs/architecture/reviews/evidence/f017-dense-prefix-fallback-inventory-v1.json`.

## Source identities

| Source | SHA-256 |
|---|---|
| Feature tasks | `d499eaa68032ae9b600218b64d26ae5016d6a6703e481465d2ce85143104e995` |
| Feature plan | `74790975a4dac6dd9eb99b47c5f681e26a384b334dcd1db98e0ad76c2b05c7bc` |
| canonical CLI | `6ba83d39eceee721508dad45bc475e61019431e222da56935cb9b77479469b3d` |
| canonical evidence schema | `f55538f1929482df3db51cb6dffd1bcfad8b0a4a6b7a0fdd071013f0d5fb88ca` |
| R11 numerical contract | `754b67aa10235d958ddce09f9ec0bb82f22138a3c3e5227a694a585da1aebece` |
| production tensor map source | `ac796dfed9b752b55391b72b9755302bf8c7458536380f38bdab1821989c38db` |
| F016 experiment protocol | `b3c4847886313fe709358b8c6803288d6d8c004abd6d5012099e8d71e3b39d1a` |

## Exact next dependency

M1-F remains the next model gate. After it is accepted, M1-G must first freeze
its final-hidden provenance, Q4_K real-byte qualification, output-head memory
admission, exact access budget, and real-shape numerical contract. Only an
accepted M1-G permits T017-141 command publication and a separately reviewed
M1-H one-P1 authorization.
