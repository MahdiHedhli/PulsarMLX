# Bounded expert admission plan

1. Add a host-only `mlx-expert-ranges` workspace crate using the existing strict
   safetensors catalog, affine recipe resolution and anchored descriptor admission.
2. Cap all metadata inputs and selected payload bytes before allocating them.
   Preserve admitted descriptors and metadata stamps; expose only sealed plans
   and immutable owned selected bytes.
3. Generate tiny MIT synthetic fixtures at test runtime, including mixed roles,
   multiple experts and a sparse large-file decoy. Assert byte fidelity, read
   accounting, refusal phases and ownership after source destruction/movement.
4. Review exact source and contract independently; repair blockers. Run targeted
   and host workspace validation with no native prefixes and no model environment.
5. Run the reviewed metadata-only binding example on Studio. Emit a private
   receipt with exact source, metadata/selected-range plan and zero payload reads.
   Publish sanitized host evidence; keep real bytes outside Git.
6. Freeze the next gate: reviewed bounded selected load, independent real input
   domain/R1 admission, then a reviewed adapter into the accepted packed path.

The existing synthetic package and its budget/domain contract stay frozen. This
crate does not claim to be a replacement `Source` accepted by that candidate.
No full-model performance or generation run is admitted by these steps.
