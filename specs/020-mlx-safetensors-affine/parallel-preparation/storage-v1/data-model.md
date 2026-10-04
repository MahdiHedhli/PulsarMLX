# Data and state model

`Identity`: opaque checkpoint, tensor, role, layer, expert, recipe and graph version.
`Selection`: source-sealed object, descriptor generation, checked u64 extent,
logical bytes independent of extent. The fixture is not a catalog parser. It
retains only its latest selection; a second select invalidates the earlier
selection. This is a fixture simplification, not a restriction on the accepted
ExpertPlan interface or a proposed real adapter.
`Step`: request ID, checkpoint, graph, recipe, epoch, position, count, context limit.
`Boundary`: explicit caller-owned request/epoch/position; storage checks equality and
position+count<=context, does not mutate it.
`PackedTensorLease`: opaque object capability bound to manager, slot generation and
exclusive owner revision. Transfer invalidates previous token. Copying references
is aliasing the same owner, not acquiring another lease.
`Entry`: reserved -> reading -> read_complete -> ready -> dispatched -> completed,
or cancelled; reserved/read_complete/ready/completed/cancelled -> released ->
explicit evict. A cancel-tolerant read acknowledges cancelling -> cancelled. Cancellation while read/dispatch is
pending marks cancelling; acknowledgement cleans staging/scratch, retains pinned
resident bytes until unpin. Terminal cancelled entries retain bounded slot
metadata until explicit eviction; pinned or published protected bytes remain
charged under their explicit lifetime rules; no unbounded token history.
`Ledger`: baseline trunk/state/overhead plus active entry resident expert/trunk,
scratch and I/O staging obligations. Each term has a category cap; aggregate cap
covers all six. Capacity is reserved before materialization; resident capacity
of published storage remains charged after owner release. Release of a never-
published entry returns its unused resident reservation immediately, including
reserved/read_complete/unpublished-cancelled entries. Terminal acknowledgement returns transient
charges exactly once. Protected trunk entries refuse eviction while resident.

Publication is explicit: resident copy remains unpublished until admission
passes its post-copy descriptor check and cancellation barrier. Failed/cancelled
unpublished copies always return capacity, including protected trunk copies.
Protected retention applies only after successful publication.
