# Data/state model v1
Descriptor: checkpoint_descriptor_id, graph_version, recipe_version (all explicit).
LayerPlan: ordered layer ID with KDA/sparse attention and dense/MoE FFN roles.
StepIdentity: descriptor triple, request ID, epoch, input position, count and
bounded context limit. Every context fixes this identity except position/count.
Context: start position, next position, epoch, revision, map of owned layer states.
KDAState: raw convolution suffix [K-1,2*Dk+Dv], recurrence [Dk,Dv] at this
mini-candidate boundary. Native adapter must transpose to [B,H,Dv,Dk].
SparseState: origin position, append-only tuples of absolute position, projected
index key, compression gate, attention key, value; full pools are recomputed in
the tiny harness. A production cache may materialize pools but must preserve
identical logical ownership, absolute positions, causal visibility and tail.
Proposal: private bounded computed states/outputs plus before identity/revision.
Commit: compare-and-swap exact before context, advance next position by count
once, revision +1; no partial layer commit. Cancel: retain before state, invalidate
proposal, no published output. Reset: all layers fresh, epoch +1, revision +1,
explicit new start; stale proposals fail. Contexts share no mutable state.
PackedTensorLease: opaque storage-owned token with sealed identity/extent;
this v1 seam is documentation-only. Model lane declares required roles; receipt
validation is deferred to the coordinator adapter, with storage physical proofs
remaining in the storage lane. state.py does not acquire or validate leases.
