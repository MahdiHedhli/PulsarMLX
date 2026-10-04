# Native full-model/state interface v1
Preparation addendum to immutable integration-contract-v1.md, not a revision.

## Text graph and dispatch
Input validated token IDs -> embedding [vocab,hidden] -> broadcast four mHC
streams -> all 45 ordered decoder layers -> mean streams -> weighted RMSNorm
-> untied lm_head [vocab,hidden] -> logits. Each layer: attention mHC collapse,
input RMSNorm, selected attention, mHC expand; FFN mHC collapse, post RMSNorm,
selected FFN, mHC expand. Norm weights must not silently default to ones.
Layers 0,1,2 are dense clamped MLP. Layers 3..44 combine eight routed experts
and one shared MLP; shared output is added once, not multiplied by router scores.
Use pinned explicit attention list (34 KDA, 11 sparse), not Qwen or GLM5.2 logic.

KDA: q/k/v projection -> depthwise causal conv -> SiLU -> q,k L2 normalization
(q also /sqrt(Dk)) -> vector forget gate and beta -> decayed delta recurrence
-> gated RMSNorm -> output projection. KDA state and conv suffix commit together.
Sparse: q_a/norm/q_b; kv_a/norm latent; indexer query, key/norm, compression gate
and APE -> visible pooled-key selection plus tail; MLA embed_q/unembed_out and
causal attention -> o_proj. Preserve separate attention and indexer positions.
Tiny harness accepts preprojected inputs and does not qualify these projections.

## Transaction boundary
Step carries checkpoint descriptor ID, graph version, recipe version, request ID,
epoch, input_position, count, context_limit. Must equal retained context; count
1..8, contiguous, no overflow past start+limit. All layer states refer to the
same next position. Compute into a private proposal; commit publishes outputs
and all states once. Stale revision/epoch, changed identity, wrong layer set,
invalid operands or cancelled proposal refuses without state change. Cancellation
retains the previous state and consumes the proposal. Repeated cancellation is
idempotent; cancellation after commit cannot undo published state. Reset creates
a new epoch and explicitly selected origin, with zero recurrence/suffix and empty
sparse history. No implicit prefix reuse, sliding window, padding or eviction.

## PackedTensorLease seam (documentation-only in v1)
This section is a future integration requirement. No executable receipt validation
is present in the tiny model/state harness; that belongs to the coordinator adapter.
Model requests sealed tensor ID, role, layer, expert (null for trunk), checkpoint
and recipe identity, logical shape and required extent. Storage supplies an
opaque ownership token and generation with checked [begin,end) byte extent,
reservation_bytes >= extent, in_flight/pinned status and explicit release.
Model may consume only a live matching generation/identity/shape/extent. No raw
paths, mmap, pointers, allocations or eviction policy here. Stale-generation
refusal, physical extent proof, reservation/release and idempotent cancellation
are storage-lane obligations. The model harness does not fabricate lease proof.
A future coordinator adapter must couple lease validity with proposal commit;
cancel releases acquired resources without rolling back already committed work.
Budget reports separate resident trunk, experts, model state, scratch, I/O staging,
runtime overhead; synthetic element bounds are not measured process/Metal memory.

## Tokenizer/output boundary and unresolved production components
Pinned EOS IDs 154820,154827,154829; pad ID 154820 overlaps EOS and is not itself
permission to stop a padded request. Tokenizer files, byte normalization, chat
serialization, BOS/special tokens, padding mask, detokenization and stop policy
need separately pinned verification. Tiny integer IDs do not qualify tokenization.
EOS decision is after committed generation; cancellation publishes neither token
nor logits. Sampling, beam/speculative decoding and MTP are unimplemented.
Open: real tensor census/shapes/dtypes/quant companions, affine numerical proof,
all projections/norms at production dimensions, native graph execution and
mHC precision, exact source tie policy, masked/batched KDA behavior, sparse cache
layout/quantization/position handling and long-context memory, lease adapter,
GPU scheduling/cancellation fences, budget measurement, real logits parity,
embedding/output head loading, full tokenizer integration, vision/projector,
MTP (config declares one nextn layer without this package proving weights),
sanitize/remapping (separate q/k/v conv concatenation, mHC renaming, forget-gate
relocation, protected FP32 preservation), num_logits_to_keep output slicing,
input_embeds admission, and any performance target. No GLM5.2, Qwen, CUDA or DeepSeek semantic fallback.
