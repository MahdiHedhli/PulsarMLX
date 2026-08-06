# Feature 002 Results

**Status**: Publication structure initialized; no real Feature 002 experiment
has run and there are no checkpoint correctness or timing results.

Only validated, committed raw evidence governed by the [Feature 002 evidence
contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md)
may populate model-backed result sections. Fixture-only methodology checks are
documented separately below and are never promoted as model results.

## Fixture-only publication validation

Three full-schema synthetic records exercise `passed`, `failed`, and `aborted`
experiment outcomes. They generate six frozen outputs: a [Markdown
summary](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.md),
[CSV summary](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.csv),
[bounded SVG](../../fixtures/research/router-v1/expected/figures/002-router-parity-median.svg),
and a source-provenance sidecar for each. The [reviewer
index](REVIEWER_INDEX.md) links the complete input and output set.

Fixture-only verification accepted three records and zero claims, regenerated
all six artifacts twice, and matched the two fresh runs byte-for-byte. A
separate detached clean-checkout reproduction at
`d6f5820050cdc59944a7b2af26b7b0c2c15767c6` matched every committed byte and
SHA-256. The displayed durations, errors, identities, and outcome states are
constructed contract-test values. They do not measure checkpoint routing,
latency, MLX execution, Apple GPU selection, memory, or inference. A synthetic
correctness field does not override a record's terminal failed or aborted
outcome.

## Correctness records

No real router records exist. Exact top-8 IDs/order, complete logits and
probabilities, normalized weights, numeric errors, device selection, and
fallback status are unobserved.

Future entries must link their raw evidence and measured source commit; report
the exact checkpoint, tensor, case, execution depth, comparison metrics, and
pass/fail state; and preserve failed or aborted outcomes. There are currently
zero entries.

## Model-backed repeatability

No real repetition record exists. Ten-run output identity and the required
clean-process replications have not been measured.

## Model-backed timing and resources

No real-checkpoint router timing has been collected. There are no first-process
OS-cache-uncontrolled, warm, minimally instrumented, stage-instrumented,
resource, power, or thermal results to publish.

Future timing entries must be generated from committed raw samples and keep
condition, instrumentation mode, case, batch, and process replication
separate. There are currently zero entries.

### Generated timing-mechanics validation

A model-free generated single-row router candidate executed on Apple MLX/GPU
from source commit `49183bd96b612a2090f472aba4dee089755bf730` and passed the
dedicated candidate validator. It retained exactly five warm-ups and thirty
measurements, one canonical actual output, 35 matching result records, one
identical complete-output SHA-256, synchronized/evaluated GPU selection, no
fallback, and no stage-sum claim. The validator independently recomputed the
actual output hashes and golden comparison, reproduced the two compatible
warm-up/measurement Type-7 groups, and bound admitted before/after environment
and worker-resource observations.

The candidate and validation report remain outside Git, identified in the
session log by SHA-256. Therefore this section intentionally publishes no
latency statistic from that external raw sample set. The run validates timing
mechanics only; it is not checkpoint routing, model inference, a throughput
measurement, or evidence for the model-backed sections above.

## Failed, aborted, and excluded attempts

No Feature 002 model attempt exists. Future unsuccessful attempts remain
append-only evidence and must appear here rather than being removed. Protocol
v1 admits no production exclusion rule; the separate excluded fixture is a
mutation expected to be rejected and is not part of the frozen expected-output
package.

## Claim boundary

There are currently zero Feature 002 claims-ledger rows and no model-backed
correctness or performance claim. Real checkpoint router parity is planned but
unverified. Expert execution, routed aggregation, complete-layer or model
inference, generation, serving, token throughput, giant-model performance,
custom Metal, and Linux/CUDA runtime parity are outside the evidence boundary
and unsupported by this feature.
