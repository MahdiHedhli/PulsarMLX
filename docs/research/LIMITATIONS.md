# Feature 002 Research Limitations

**Status**: Methodology limitations only. No Feature 002 checkpoint experiment
has run, so this document contains no measured limitation disguised as a
result.

Normative boundaries and stop conditions remain in the [Feature 002
specification](../../specs/002-qwen-router-parity/spec.md) and [experiment
protocol](EXPERIMENT_PROTOCOL.md).

## Evidence-derived limitations

No Feature 002 model evidence exists, so there are zero evidence-derived
limitation entries.

## Predeclared methodology constraints

- Hosted CI does not receive the external checkpoint and is limited to
  committed fixtures, schemas, scripts, and publication boundaries.
- Feature 002 does not provide Linux/CUDA runtime validation. Inherited paths
  must remain preserved, but no Apple-only result can verify them.
- The protocol does not purge operating-system caches. A future new-process
  read is therefore labeled `first_read_new_process_os_cache_uncontrolled` and
  cannot be reported as a controlled cold-filesystem measurement.

## Unavailable observations

Feature 002 router-tensor admission, genuine `ffn_norm-0` captures, real CPU
oracle values, Apple router outputs, repeatability, latency, memory gauges,
model-work admission resources, power mode, thermal state, and interference
observations are all unavailable until their dependency-ordered tasks run.
Unavailable values are never encoded as measured zero.

## Unsupported interpretations

Even a future passing router record cannot establish expert MLP execution,
selected-expert aggregation, attention or prior-layer parity in PulsarMLX, a
complete transformer layer or model, language-model-head logits, tokens,
generation, serving, full or giant model inference, projected tokens per
second, custom Metal, Apple multi-device execution, broad Qwen compatibility,
or Linux/CUDA runtime parity.

## Open reproducibility constraints

- The external file must remain legally available and exactly match its frozen
  repository, revision, filename, size, and SHA-256.
- The pinned CPU callback must capture two distinct real rows twice with
  identical hashes and prove cancellation before router or expert execution.
- A clean-checkout real reproduction requires operator coordination and an
  acknowledged NTFY hardware window.
- Any real rank-8/rank-9 F32 tie, identity mismatch, resource failure, or
  non-reproducible output is a stop condition rather than permission to loosen
  the protocol.
