# Option C: source-compatible base and literal failure/accounting design

Recommend exact base adda03ad9097372fe7e9d8fa59d2853281af6c1f, not the older
bff720bd4ddc83fcf6c41ed4c58a938d8c2c33ef. Read-only git comparison shows current
head descends from bff; no changed-path overlap with either frozen prep branch;
shared Python candidate.py dependency is byte-identical. It imports only stdlib.
This preserves reviewed Feature020 history. No merge is performed or certified.
Frozen model bd7078054d92373bedb1759dfbab533d0fde1a23 and storage
316c82627a04b0c21669ffb1a8237d1ca323b1db remain untouched. Recommend THIS sole
native owner, sequentially, in a new isolated worktree only after explicit approval.

StepV2 fields, exactly: checkpoint_descriptor_id,graph_version,recipe_version,
request,epoch,revision,origin,capacity,endpoint,position,count. First three equal
the model descriptor tuple and storage(checkpoint,graph,recipe) componentwise.
Capacity1..8, origin0..2^31-9, model integer intersection, identities1..64 chars;
checked endpoint=origin+capacity, count>0, position+count<=endpoint.
Origin13/capacity8 means tokens[13,21), next-position up to21. Reset recomputes
endpoint from its new origin. Refuse noncanonical layer labels except0,3,4,7.

Only synthetic preprojected TOKEN operands: KDA10 binary64 scalars/token (7,2,1),
sparse16 (2,2,2,1,3,3,3). Little-endian binary64, ascending layer/token order,
scalar partitions are bare floats, no header/trailing bytes, finite |x|<=8.
Geometry checked before reserve, content after admission before dispatch.
Trunk is authored16-byte provenance-only, no token decode/no weights. Registry
is object-identity under trusted-caller assumptions, not a security boundary.
Required provenance set includes trunk; operand subset excludes it. Bind both to
proposal, immutable copies and acknowledge wrappers (token/generation/selection/
StepV2/revision/dispatch-ID). No substitute completion from another lease.

## Whole-set preflight and ordering

Serial sole owner, no unaccounted external mutation between precheck/reservation.
Validate ALL sources/selections/identities/steps/geometry first, slot count next,
then category and aggregate budget. cap_i=8*ceil(length_i/8), scratch_i fixed8.
Require live_slots+n<=4, checked cap_i<=4096, and checked proposed vector
 L' = L + sum(category_i+=cap_i, scratch+=8, io+=cap_i)
within every category limit and sum(L')<=total. Include already retained trunk
and pending resource charges; no double subtraction for future planned refunds.
Adapter logical-capacity preflight below occurs before any storage reservation.
Reserve KDA, sparse, trunk order; read all fully, then admit KDA,sparse,TRUNK LAST;
validate immutable copied content; pin each; dispatch KDA,sparse,trunk. No runtime
adapter is written here. Unexpected faults after successful aggregate precheck
use sibling cleanup; the precheck does not make individual fixture operations
transactional. Never retry the step or silently reselect a mutated source.

Literal canonical population uses one token, layers(0,3), payload K80/S128/T16,
zero baseline, limits=(16,256,0,24,224,0), total472, slots4. Ledger order:
(trunk,experts,state,scratch,io,overhead). Model context is adapter-owned, so
storage state stays0. Slot generations start(0,0,0,0); successful reserves
increment slots0,1,2 respectively, to(1,1,1,0). Eviction never rolls them back.

| Event | Storage ledger | Live slots |
|---|---|---|
| start/preflight | (0,0,0,0,0,0) |0|
| reserve K |(0,80,0,8,80,0)|1|
| reserve S |(0,208,0,16,208,0)|2|
| reserve T; read all |(16,208,0,24,224,0)|3|
| admit K |(16,208,0,24,144,0)|3|
| admit S |(16,208,0,24,16,0)|3|
| admit T; copy/decode; pin/dispatch all |(16,208,0,24,0,0)|3|
| acknowledge K completed |(16,208,0,16,0,0)|3|
| acknowledge S completed |(16,208,0,8,0,0)|3|
| acknowledge T completed |(16,208,0,0,0,0)|3|
| unpin+release K |(16,208,0,0,0,0)|3|
| evict K |(16,128,0,0,0,0)|2|
| unpin+release+evict S |(16,0,0,0,0,0)|1|
| unpin+release T |(16,0,0,0,0,0)|1|
| close -> Owner; evict T -> Protected |(16,0,0,0,0,0)|1|

Every table is literal DESIGN expectation checked against source, not an observed
adapter trace. No storage or model module is executed in this task. Tests below
check public accounting arithmetic only. No native lifetime proof is inferred.

## Failure traces (model context/output unchanged unless noted)

Preflight slot5 with trunk+four layers: reject before any reserve; ledger0,slots0,
generations0. Category refusal: limits.experts207 for K+S; scratch refusal23 for
K+S+T; aggregate refusal total471 with default limits; all reject before reserve,
ledger/slots/generations unchanged. Integer overflow/invalid source also pre-reserve.

Reserve S stale after K reserved (injected source mutation, not a concurrency
claim): ledger(0,80,0,8,80,0),slots1,generations(1,0,0,0). cancel K ->ledger0
but slot remains1; release+evict ->slots0. Generation remains1. A later per-lease
Budget/Slots fault contrary to preflight is terminal internal-invariant refusal,
with identical cleanup of successful siblings; never alter limits to continue.

After reserve-all, begin_read K fault=error auto-cancels K: ledger
(16,128,0,16,144,0),slots3. cancel S ->(16,0,0,8,16,0);
cancel T ->0. release/evict all ->slots0, generations(1,1,1,0).
Read S I/O/short-read/stale/count/interrupt-limit failure after K read_complete:
S auto-cancels ->(16,80,0,16,96,0); cancel K ->(16,0,0,8,16,0);
cancel T ->0; release/evict all ->slots0. If sibling reading has pending read,
cancel then call read to acknowledge cancellation BEFORE release/evict.
Admission S fault after K admitted: ->(16,80,0,16,16,0);
cancel K (unprotected/unpinned) ->(16,0,0,8,16,0); cancel unpublished T ->0;
release/evict all ->slots0. Admission T fault after K/S admitted:
->(0,208,0,16,0,0); cancel K ->(0,128,0,8,0,0); cancel S ->0;
release/evict all ->slots0. A read/admit cancellation uses the same quiescent
refund rules. All successful sibling reserves leave advanced generations.

After T publication, any content refusal before pins: cancel K/S refunds experts
and their scratch; release T refunds its scratch, retains T16. Final ledger
(16,0,0,0,0,0),slots1, no dispatch/model commit. Terminal instance close->Owner.
Trunk-last avoids retention on earlier layer admission failures, not on later ones.

Dispatch S fault=error after all pins and K submitted: S phase cancelled, its
scratch refunded but pin retains128; ledger(16,208,0,16,0,0). K pending:
acknowledge completed ->(16,208,0,8,0,0). Unpin/release/evict K ->
(16,128,0,8,0,0). Unpin S drops cancelled capacity ->(16,0,0,8,0,0);
release/evict S. T was not dispatched: unpin/release T ->(16,0,0,0,0,0),slots1.
Dispatch T fault after K/S submitted: T cancellation refunds scratch but retains
protected capacity; acknowledge K/S, then unpin/release/evict experts and unpin/
release T; same terminal T16. Dispatch K failure is the same cleanup template
with no outstanding successful dispatch. Exact prefix ledgers derive from table
and scratch refund8; pins prevent any capacity refund until unpin.

Engine.prepare failure AFTER all dispatches: no proposal handle exists, no commit.
Acknowledge K/S/T completed, giving scratch16,8,0 as table, then normal unpin/
release/evict expert cleanup, retained T16. Adapter output/copy/decode/proposal
reservations return to baseline. Injected failure after a model layer transition
must leave model context unchanged (frozen prepare accumulates privately). Mutant
that publishes/commits or leaves any sibling reservation fails the literal oracle.

## Cancellation, reset, once-only output

Unprotected pending read/dispatch: cancel marks pending only, ledger unchanged;
read/acknowledge then refunds transients; pinned capacity survives until unpin.
Protected unpublished: cancel similarly, eventual refund; published-ready:
no storage cancel/evict allowed, never dispatch after cancellation/reset, release
keeps cap. Protected-dispatched: wait completed acknowledge, then discard proposal,
unpin/release and retain cap. No synthetic cancelled receipt for Protected.
Reset invalidates intent by epoch/revision; quiescent cleanup above is required
before another step. Example origin13->20 with capacity8 gives endpoint28,
epoch0->1, revision+1. A stale old-Step dispatch must refuse at adapter boundary.

Only after all matching completions and exact before-context CAS may commit
happen once. Output slot is reserved BEFORE any storage work. It retains commit
ID and immutable outputs even on delivery failure. Delivery retry returns same
bits/ID without prepare/commit. While occupied, next-step/reset refuse, ledgers
unchanged. Explicit delivery ack or abandonment frees output slot; abandonment
does not roll back committed context. Retried evicted ID returns expired. Reset
then starts new epoch; delayed old receipts cannot advance it. Post-commit cancel
cannot undo context. Crash durability and concurrency remain unqualified.

## Adapter ledger and literal capacity trace

Separate logical-capacity ledger A=(state/proposal,output,copies,decoded), not
Python heap/physical RSS. State/proposal cap65536; baseline reservation16384
supports two live contexts; output32768 for one slot; copies8192; decoded8192.
Only one step outstanding. Payload observation copies are additional objects,
so DO charge them separately from storage resident capacity; decoding duplicates
numeric payload representation and is charged again. Hold both through dispatch
and prepare; free only at quiescence after proposal no longer needs operands.
Source-authored bytes and control metadata are fixed harness inputs, bounded by
four sources<=4096 each plus finite registry; not included in these payload caps
and never represented as a global memory bound. Actual Python object overhead
and native pools require separate measurement before any physical-cap claim.

Canonical sizes for these logical reservations: binary64 scalars8bytes, integer
coordinates8bytes, strings u16 byte-length+UTF8 (<=256 bytes for64 codepoints),
collection counts8bytes. Context header <=1080, each layer<=752 (sparse8 entries
with one position+10 scalars, metadata; KDA20 scalars), hence each context<=4096.
At most2 live contexts, one pending after-context and one independent saved
before-context require<=16384 canonical bytes;65536 reserve also covers bounded
proposal/control encoding slack, not new unbounded copies. Layer outputs up to
four layers*eight tokens*(3binary64+8indices*8+count8)+headers<4096, held in output
reservation32768 from creation. Copies: max4*4096=16384 for unrestricted source
lengths would EXCEED8192, so first-slice geometry restricts each layer to<=1024
and trunk16: at most4096 per four slots, decoded<=4096. Any extra copy/decoding
allocation beyond one of each per lease refuses under the declared cap.
No implicit payload-copy duplication is free. Oversized geometry rejected before
reservation, independently of source MAX_BYTES4096.

A trace: idle(16384,0,0,0); aggregate preflight/reserve
(65536,32768,8192,8192); copy/decode/dispatch/prepare same reserved vector;
abort/prepare-failure quiescent cleanup ->(16384,0,0,0);
success after commit+quiescence ->(16384,32768,0,0);
publish failure/retry/backpressure/reset-refusal unchanged; delivery ack or
abandon ->(16384,0,0,0). Charges are reserved capacities, not measured occupancy.
Storage and A are reconciled as separate ownership columns; never call their
sum process memory. All slots/ledger changes are asserted exactly, alongside
model state, provenance-set equality, unique dispatch/commit IDs and generations.

Mutations: undercount aggregate scratch/io, omit a sibling cleanup, undo generation,
dispatch stale/reset or invalid decode, mismatch receipt/token/selection, omit
trunk provenance, reuse completed lease, unpin before quiescence, commit after
prepare failure, rerun output delivery, omit copy/decoded charge, falsely free
protected trunk, accept close despite retained entry. Each must contradict a
literal expectation above. Frozen original16+16 model and29 storage tests remain
required later; none ran here. No production adapter or model execution now.

## Explicit scope restriction after review

The canonical trunk-bearing design supports ONE STEP PER STORAGE INSTANCE and
at most THREE token layers with four slots; the literal success trace uses two.
After delivery acknowledgement/reset, a next trunk-bearing step still refuses
aggregate admission: retained trunk16 exhausts its category. Reset does not
reclaim it. Output backpressure and reset traces describe state/ownership rules,
not a promise that storage can execute a second step. A four-layer context plus
trunk needs five slots and always refuses. Reusable protected residency/teardown
and four-layer slot policy require a separately versioned/reviewed design before
approval of any multi-step scope. This proposal requests only bounded single-step
host preparation; it is not a production integration milestone.

Category convention: reserve(category='experts') for synthetic token operands is
an explicit adapter mapping to the only available non-trunk category of frozen
storage v1. The experts column here measures TOKEN-OPERAND CAPACITY, not expert
weight residency. A future versioned adapter addendum must retain that label
qualification; no storage category extension or weight semantics is assumed.

## Implementation authorization adaptation
The current user authorization supersedes the plan-only and sequential-owner text above solely for this isolated host implementation. All literal semantic and execution boundaries remain normative.

Constitution-compliance check: PASS for this bounded specification, under .specify/memory/constitution.md Governance lines166–168 and principles I, III, VIII, X, XI, XII. Only additive stdlib host synthetic code is planned; no production/native claim, weights, shared metadata or frozen-source modification. Tests, exact independent reviews, failures and commands remain explicit. No Rust changes; workspace/native checks are outside this slice.

## Frozen host API v1 (prospective; resolves pre-review F1/F2/F4/F5/F7)

New files carry MIT headers and PulsarMLX modification attribution; inherited upstream licensing is unchanged. Python API uses the shared canonical module imports scripts.research.glm53_flash.native_preparation_storage_v1.fixture and native_preparation_model_state_v1.state; tests use the same module objects. No dynamic duplicate fixture import.

`Adapter(descriptor: tuple[str,str,str], storage: StorageFixture, *, caps=(65536,32768,8192,8192))`. Storage is exclusively owned by this adapter under the trusted serial caller rule. Construction refuses a used storage instance (any prior generations/dispatches/live slots); nonzero allowed baseline charges still count in preflight. Constructor checks strict descriptor labels and cap tuple of four nonnegative integers; lower caps are allowed for refusal tests, no cap can exceed the declared ceilings. Idle state reservation must fit. No replacement storage API; one step only. A second Adapter cannot obtain a spent instance even if entries were evicted, because generations remain advanced. Simultaneous owners are forbidden by the trusted-caller contract, not a concurrency claim.

Public immutable dataclass `StepV2` fields/types exactly:
checkpoint_descriptor_id:str, graph_version:str, recipe_version:str, request:str,
epoch:int, revision:int, origin:int, capacity:int, endpoint:int, position:int, count:int.
Strict integers exclude bool. epoch/revision/position/count/endpoint in0..2**31-1; origin/capacity intersection above. Strings strict str,1..64 codepoints, UTF8 encoding must succeed (reject lone surrogates).

Opaque Grant, Intent and Completion classes have no public fields. Authority is membership by object identity in this adapter's private registry. Equal/copied objects confer no authority. Registries contain at most4 grants,1 active intent,4 lease records,4 completion records,1 output. After termination, retain only the last intent token for idempotent cancellation, monotonic issued commit-ID high water and at most1 retained output. IDs are positive strict integers local to the adapter; first commitID1, no reuse. Dispatch IDs are monotonically assigned1..4 in layer/trunk order; never reused. No cross-adapter ID authority is asserted; call the originating adapter.

API signatures and effects:
- `create(request, layers, *, origin=0, capacity=8, initial=None)`: create up to2 frozen Engine contexts; sorted unique model labels only; initial is the frozen (2x3 recurrence,2x7 suffix) pair. Maximum4 context layers is permitted only to test slot5 refusal; executable maximum3. Must be idle before any storage attempt.
- `snapshot(request) -> Context`: immutable frozen snapshot.
- `step(request, count) -> StepV2`: construct from current context; does not authorize execution or compute output.
- `seal(source: SyntheticSource, selection: Selection, shape: tuple[int,...]) -> Grant`: validate exact source/latest selection, canonical identity and checked extent; capture source/selection object identity, source generation, identity and shape. At most4 sources, all distinct. No reselect/reseal or grant cloning. No storage effects. After a valid grant its captured record is immutable.
- `intent(step: StepV2, grants: tuple[Grant,...]) -> Intent`: validate Step against exact before-context, source authority, sorted exact layer coverage and required trunk, geometry; whole-set slot/category/total and adapter cap preflight. Validation is zero-effect. On success reserve the single output slot and logical pre-reserve vector, retain captured before-context and issue the one intent. No storage reservation or computed output yet. Four layers+trunk input can be supplied as five grants only through a test fault seam to prove slot5 refusal; normal registry admission limits4 and refuses the fifth even earlier. Both paths have zero storage effects.
- `reserve(intent)`: reserve all layer leases ascending then trunk. First successful reserve spends this storage instance even on failure. Never retry partial work. Record each real ledger boundary, including failure before cleanup.
- `begin_read(intent,index)` then `read(intent,index)->bool`: ascending indices; repeated read calls permitted only until completion. Actual storage read completion establishes quiescence. `admit(intent,index)` requires all reads complete, ascending admissions with trunk LAST.
- `capture(intent)`: only after all admissions, obtains exactly one immutable observation copy per lease; decodes each layer once. All content validated before pin/dispatch. Private per-lease capture flag refuses a second call with CopyOnce even when spare bytes fit the numeric cap. A single decode construction per layer is also guarded. No extra full observation/decode copies are permitted. The reserved capacities cover transient scalar decoding workspace, not an authorization to duplicate observations.
- `pin(intent)`, `dispatch(intent)`: each all leases ascending; dispatch requires all pinned and valid captured bytes/current context/source/token bindings. No completed->ready or second dispatch. Intent validation is repeated against live epoch/revision immediately before dispatch.
- `prepare(intent)`: require every lease dispatched and pending, immutable decode/provenance exact; invoke private frozen Engine.prepare exactly once. Returns no proposal/output to caller. Private proposal record binds full required proof tuple and consumed layer subset. No public unbound Engine path.
- `complete(intent,index)->Completion`: adapter calls storage.acknowledge itself, then seals returned receipt and exact per-lease proof in registry. Require proposal exists, lease not already acknowledged, real pending dispatch. Arbitrary completion ordering permitted. Wrong/duplicate/forged caller receipts never acknowledge anything.
- `commit(intent, completions: tuple[Completion,...])->int`: require exact unique complete set, successful quiescence, all proof identities and current before-context/revision; CAS once through Engine.commit, then retain immutable output and new commit ID in the pre-reserved slot within the same serial operation. No external callbacks between CAS and retention. Clean up leases/copies and reduce logical ledger to success. Invalid completion set refuses without commit; terminal abort discards the proposal and drains remaining operations. A matching set must be provided on the first commit call; no speculative partial commit API.
- `deliver(commit_id, sink=None)->outputs`: look up retained ID. Optional test sink receives immutable outputs; a sink exception propagates but retains ID/bits/charges. Calling again returns same object/bits without any model/storage work.
- `ack(commit_id)` and `abandon(commit_id)`: discard retained output only, keep committed context, logical idle. Already issued but absent ID raises Expired; never issued ID raises UnknownOutput. No tombstone collection; high-water1 suffices in this single-step adapter.
- `cancel(intent)`: idempotent invalidation before commit, cancel only unprotected or unpublished storage entries. Pending cancellation retains charges until read/ack. Published protected entries are never cancelled. Does not invent completion or unpin pending leases. After commit/termination same last intent cancellation is a no-op. Foreign intent refuses.
- `drain(intent)`: finish cancelled reads through storage.read; acknowledge submitted dispatches normally for an operational failure, or cancelled for explicitly cancelled unprotected dispatches. Protected submitted dispatches always acknowledge completed. Cancel nonpending unprotected/unpublished siblings; unpin only after no pending; release; evict only unprotected/unpublished. Free proposal/copies/output reservation after quiescence. No generation edits. Used instance stays terminal.
- `reset(request, *, origin=0)`: output occupied refuses first. Validate reset domain before mutation. If active, cancel intent; reset frozen context epoch/revision immediately; cleanup pending resources with drain before return. Other context unchanged. Reset does not enable another storage step or reclaim published trunk.
- `run(intent)->commit_id`: convenience invokes above stages in order and complete for each index. Tests also use individual phases. Stage failures record failure and terminally drain before propagation, except explicit cancel which deliberately exposes pending state until drain. No recovery retries.
- `ledger`, `events`, `prepare_calls`, `commit_calls`: bounded read-only observations. Events are at most128 phase snapshots (no per-byte-read events), with event label, storage ledger/live slots/generations and adapter ledger. Reaching event capacity refuses before another operation. Tests may inspect frozen entries under the same trusted fault-seam assumption.

A per-lease frozen proof contains Grant authority object, source and selection objects plus captured selection fields (identity,generation,offset,length,logical_bytes), shape, owner, opaque lease token, slot and slot generation, StepV2 and before revision, unique dispatchID, SHA256 of the sole immutable payload observation, and the exact immutable decoded object for layer sources (None for trunk). Required tuple includes trunk, consumed tuple excludes it. Completion wrapper registry binds proof and storage Receipt object/status. The proposal captures these tuples after dispatch. Commit compares exact set/identity, not merely digest or Step equality, and revalidates live token/source generation. Digest means provenance only, never a numerical oracle.

Canonical storage identities are synthetic identities, not production tensor roles:
- Token layer L in{'0','3','4','7'}: Identity(checkpoint, 'tokens/'+L, 'token-operands', L, 'none', recipe, graph). Shape=(count,10) for0/4 or(count,16) for3/7; exact logical_bytes=length=8*product(shape). Extent may have a checked nonzero offset, must fit source; no other unsealed bytes consumed.
- Trunk: Identity(checkpoint, 'trunk', 'trunk-provenance', 'trunk', 'none', recipe, graph). Shape=(16,), logical_bytes=length16. 'trunk' is the sole non-layer label exception and never maps to a model layer. The explicit 'none' sentinel adapts documentation-null expert to the frozen storage nonempty-string domain; no semantic expert is introduced.

Adapter errors use `AdapterRefusal(code)` (separate from frozen Refusal.code). Stable codes: Identity (type/string/canonical role etc), Geometry (shape/extent/length/layer coverage), Step (canonical arithmetic/context equality), Authority (unknown/cloned grant/intent/completion/proof mismatch), Busy (active/outbox), Used (spent storage), Phase (stage order/rearm), CopyOnce (second capture/decode), LogicalBudget, Slots, Budget (whole-set storage), Completion (missing/duplicate/unsuccessful set), CAS (before-context changed), Expired, UnknownOutput. Unexpected post-preflight per-reserve Budget/Slots are wrapped Invariant after sibling cleanup; never an assert. Other frozen errors propagate unchanged after cleanup, preserving their original code. Model prepare error propagates after cleanup; model commit CAS failure maps to CAS. Precedence: Busy/Used, strict Step/context, grant authority/identity, geometry, slots, logical caps, category/aggregate budget. Tests isolate one invalid condition unless testing precedence expressly.

Storage audit/asserts may be additional diagnostics only. ALL new enforcement uses explicit exceptions and ALL new oracle checks use unittest assertions (or explicit comparisons raising independently of optimization), never Python assert or StorageFixture.audit() as sole evidence. Storage29 runs normal only because its inherited mutation test deliberately expects an assert; model16 and new adapter population run normal and -O.

Idle reservation16384 is deliberately conservative: covers at most2 current contexts plus headroom for one saved-before and pending-after canonical context (4*4096), even when only2 currently exist. During a step reserve65536 for all state/proposal/control encoding. Per-category caps are configurable only downward; caps=(65535,32768,8192,8192) constructs idle successfully but intent raises LogicalBudget, storage remains allzero. The copy-once rule is a separate cardinality invariant, not inferred from spare capacity.

Tolerance for NEW independent floating calculations: abs(actual-expected) <= 1e-12 + 1e-12*abs(expected); integer/ledger/ID checks exact, redelivery bytes exact. Frozen model tests retain their existing tolerances unchanged (including rtol1e-10). This stricter tiny-case oracle does not revise production or frozen acceptance. Zero mixed KDA analytic fixture has ZERO convolution suffix and nonzero recurrent state. The two-context case creates A and B in ONE adapter, steps only A, resets/invalidate A as phase permits, and verifies B byte-for-byte unchanged; it never runs a second storage step.

Fault injection is test-only through unittest.mock.patch.object on the private Engine.prepare/commit or canonical module transition function and StorageFixture subclass overriding reserve/begin_read/admit/dispatch to call frozen methods with their existing fault argument. Post-first-reserve subclass may mutate S source or raise frozen Refusal('Budget'/'Slots') before second reservation. CAS failure injects a changed private before-context immediately before adapter commit verification; oracle checks no proposal commit occurred and the injected context is preserved. These serial fault seams confer no native/concurrency authority.

## Cleanup/event/test-seam precision (pre-review02 G1–G5 repairs)

Every individual phase method (reserve, begin_read, read, admit, capture, pin, dispatch, prepare, complete and commit) owns terminal cleanup on an operational failure after an active intent exists: invalidate the intent, cancel/discard any model proposal, record the failure state, call drain exactly once, then propagate the original refusal/error. `run` does not drain again after an individual method already did. Pure method-authority/phase checks before any operation reject without touching an unrelated active intent. Missing/wrong completion set in commit invalidates and drains its own active intent. No successful partial reservation is retried. The caller need not clean up reserve-S failure.

Operational-failure invalidation is distinct from explicit `cancel`: it does NOT mark already-submitted operations cancelled. Explicit cancel loops ascending entries and calls storage.cancel on every unprotected or unpublished entry (including already-completed unprotected entries); skips published protected entries; pending operations retain charges. Already-cancelled entries are skipped. Explicit cancel returns without drain to expose the literal pending boundary. Reset validates input first, calls explicit cancel then changes model coordinates, then drains synchronously before returning.

Drain has EXACTLY two ascending passes:
1. Quiesce each lease. If pending read: mark cancellation if not already marked, then call actual storage.read until cancellation completion (one call for an already marked read). If pending dispatch: call actual storage.acknowledge exactly once; status is cancelled only if explicit cancel previously marked that unprotected entry; otherwise completed, including every protected published dispatch. Record real receipt status, never fabricate it. For a NONpending entry: cancel it only if neither completed nor already cancelled AND it is not protected-published. Completed entries from normal acknowledgement are NOT storage-cancelled. Entries explicitly cancelled earlier stay cancelled.
2. For EACH lease in order, fully perform unpin if pinned, then release if owned, then evict unless protected-published, before proceeding to the next lease. Never group all unpins before evictions. Hence dispatch-S failure: K ack -> scratch8, K unpin/release -> unchanged, K evict ->experts128, S unpin ->experts0, S release/evict, then T unpin/release ->scratch0. Normal K completed bytes stay retained until its evict. Generations never change during cleanup. Protected T release is terminal; no evict or close call is hidden inside cleanup.
After both passes, release logical copy/decode/proposal reservations and uncommitted output reservation; committed outbox reservation persists. Retain terminal intent token only; expire grant/receipt/proposal registries. A second drain of that terminal token is a no-op. Source transfer into a foreign owner is a refusal fault seam, not permission to reclaim foreign-owned bytes: transfer tests validate stale capability refusal and use the rightful test owner for cleanup; no adapter claims successful cleanup of externally stolen authority.

Observation schema: event tuple `(label,storage_ledger,live_slots,generations,adapter_ledger)`; generations tuple includes all configured slots. Labels EXACTLY: `intent`, `reserve:i`, `begin_read:i`, `read_complete:i`, `admit:i`, `capture`, `pin:i`, `dispatch:i`, `prepare`, `ack:i:status`, `commit`, `cancel:i`, `drain_read:i`, `drain_ack:i:status`, `unpin:i`, `release:i`, `evict:i`, `idle`, `output_ack`, `output_abandon`, `reset`, and `error:phase:i` (index -1 for whole-set operations). Emit after successful listed storage calls; error event after the failing call's own refunds but BEFORE adapter cleanup. No event for unsuccessful/incomplete `read` iterations or pure query/refusal. Emit read_complete only when read returnsTrue. During explicit cancel emit cancel:i only when storage.cancel was actually invoked. Drain cancellation uses same cancel:i label. Normal completion uses ack:i:completed; drain uses drain_ack labels. Postcommit cleanup uses the same unpin/release/evict labels; commit event is after successful CAS and retained-output installation, before cleanup; idle event observes the resulting idle or success logical reservation. No observed event implies a native operation.

Event capacity is checked before a phase that could emit and before cleanup begins: reserve enough for all its possible events plus a fixed64-event cleanup tail; at most64 forward/explicit-cancel events, at most64 cleanup/reset/output events. Fixed one-step phase ordering and at most4 leases yield fewer than these maxima. Read retry loops emit nothing until completion, so chunk1 or chunk5 remains bounded. No trace truncation is permitted. Queries, expired-ID checks and idempotent terminal operations emit nothing, preventing unbounded retries from filling the log. Failure because capacity was deliberately corrupted by a test refuses BEFORE the next storage operation; the reserved cleanup tail remains available.

Literal successful sources all use `chunk=5, actions=()` explicitly. Read-failure S cases change ONLY S actions: short=(0,), IO=('io',), count=('oversize',), interruption=('interrupt',)*5. A stale-read case mutates source generation after begin_read and before read. Other sources retain chunk5/actionsempty. Begin/admit/dispatch fault='error' passed through frozen method subclass seam. All lease indices refer to ascending model layers followed by trunk, starting0.

`Invariant` is added to the stable AdapterRefusal code taxonomy for a per-reserve Budget/Slots contradiction after aggregate preflight; preserve the original frozen refusal as chained cause. No assert enforcement.

Fifth seal ALWAYS refuses AdapterRefusal('Slots') before issuing authority or modifying the registry. P03's public path creates the four layer grants, then attempting trunk seal refuses Slots, with storageledger/generations/slotszero. The prospective whole-set slot5 test uses this explicit test-only private-registry seam: temporarily remove one already valid grant record, seal the valid trunk as fourth, then restore the original record. Supply all five already canonical authorities to intent; whole-set slot check refuses Slots before logical/storage effects. This is a deliberate bounded fault population, NOT a supported five-grant public API; the normal registry remains at most4. Tests must assert no reservation calls.

Retain the approved same-selection/distinct-token receipt case explicitly: create a SECOND independent standalone StorageFixture in the test, reserve the exact SAME SyntheticSource and SAME Selection objects at the same storage Step under the same owner, read/admit/pin/dispatch/ack there to obtain a distinct opaque token and real same-Step completed receipt. The main adapter still has its original pending/proposal lease. At the private test-only completion registry seam substitute a wrapper record carrying this alien token/storage-instance proof (source/selection/digest/Step can equal). Commit must refuse Authority/Completion before model commit and drain the original set. The standalone foreign fixture is cleaned by its own test owner. The original adapter never accepts two same-source grants; this test is a counterfeit provenance witness, not a second model step or source-selection domain extension. Related A-for-B tests substitute one legitimately acknowledged adapter completion for another at the same Step; incomplete/dedup checks must catch it. Wrapper object identity and exact token/lease-set binding are independent requirements.

A dispatchID is assigned/consumed only immediately AFTER a successful storage.dispatch. A refused dispatch never creates a usable proof or Completion. Successful earlier IDs remain spent during cleanup and are never rolled back. Numerical zero KDA outputs use arithmetic equality, not a required zero sign; signed-zero decode and retained-redelivery bits are separately checked exactly.

## Active-intent refusal classification (pre-review03 H1 repair)

The following precedence/classification is normative for both `run` and individual phase calls; it removes any discretion in the phrase operational failure.

PURE PRE-OPERATION checks (no ledger, context, event, registry or liveness change):
1. Foreign/forged intent token: Authority. Last terminated intent: Phase for all phase methods, except cancel/drain which are idempotent no-ops. Do not drain an unrelated active intent.
2. On the exact active token, wrong phase or out-of-order call: Phase. This includes dispatch-before-pin, repeated dispatch/rearm, complete-before-prepare, duplicate complete for an already-acknowledged index, and begin_read(i+1) before read(i) completes.
3. Wrong index type/range in begin_read/read/admit/complete: Geometry. Passing a Completion object as the complete index is therefore Geometry, not an acknowledgement.
4. Repeated capture after any successful capture: CopyOnce, checked before generic phase order. It is PURE even after pin/dispatch; no second payload read/decode, no refunds. The original intent remains usable in its correct next phase. A second capture after termination is Phase by rule1.
5. Busy/Used and other pre-intent/seal/create/output-domain refusals as already specified are pure. No active resources are invalidated by a rejected attempt to start another intent. Output-occupied reset Busy is pure. Invalid reset origin/revision/epoch bound is Step and pure before cancel/reset.

TERMINAL checks/failures (invalidate OWN active intent, emit the error boundary, cancel proposal if present, drain ONCE with the operational-failure two-pass policy, then propagate):
1. Content/decode refusal during first capture: Geometry (nonfinite/out-of-bound numeric content is part of the synthetic operand geometry domain), error:capture:-1. After trunk publication the exact terminal trace retainsT16; no dispatch/modelprepare.
2. Once correct phase is established, live context mismatch immediately before dispatch/prepare: Step, error:dispatch:-1 or error:prepare:-1. Source/selection mismatch at these boundaries preserves frozen Stale; lease/proof mismatch Authority. These are terminal, not pure phase refusals. No stale dispatch may be attempted.
3. Any exception from an actual storage phase operation or private Engine.prepare: record error:phase:i (whole-set index-1) and drain; preserve its code/type except post-preflight reserve Budget/Slots→Invariant. Unexpected decode computation exception also terminal. Successful earlier dispatches acknowledge normally for operational failure; only an earlier EXPLICIT cancel marks them cancelled.
4. commit: missing/duplicate/incomplete/unsuccessful completion set→Completion; unknown/forged completion capability or alien/mismatched proof/token/selection/digest/lease-set→Authority; changed current before-context or private Engine.commit CAS error→CAS. All emit error:commit:-1 and terminally drain. The first mismatched check in this sequence determines code: count/duplicates, authority/proofs, statuses/quiescence, CAS. No partial-commit retry. A foreign intent remains pure Authority by rule1 even when receipts are invalid.
5. Explicit cancel invalidates but does not emit error or drain; reset follows its separately specified cancel/change-context/drain sequence. Calling further phase methods on this cancelled-but-undrained token refuses Phase purely; drain remains permitted. Resources are still pending until true completion.

Literal H1 cases:
- After capture/pin canonical ledger(16,208,0,24,0,0),slots3,g1110,Apre-reserve: repeated capture CopyOnce leaves EVERYTHING unchanged (including events). Dispatch-before-pin Phase similarly leaves its ready unpinned ledger unchanged. After dispatch-all, repeated dispatch Phase leaves dispatches3 and ledger/scratch/pins unchanged. After completeK, duplicate completeK Phase leaves(16,208,0,16,0,0),slots3,g1110 and its receipt authority intact.
- Inject changed context revision after pins (no storage effect); correct-phase dispatch refuses Step BEFORE storage.dispatch, emits error:dispatch:-1 at(16,208,0,24,0,0); drain cancels K→(16,208,0,16,0,0), S→(16,208,0,8,0,0), no cancelT; unpinK drops80→experts128; release/evictK; unpinS drops128→experts0; release/evictS; unpin/releaseT refunds scratch8. FinalT16slot1,g1110,Aidle,dispatch0,prepare0,commit0. Preserve the externally injected context without further mutation. Cancellation/reset stale-token tests also check pure Phase once token is terminal; neither path can dispatch.
- Terminated/foreign phase calls add no events/refunds/state changes. Missing completion set before all acks: terminal Completion, remaining submitted operations acknowledge completed in drain, then terminalT16; no model commit. Unknown wrapper or alien-token wrapper with correct set length: terminal Authority, same quiescent cleanup. Tests assert these exact codes rather than Authority/Completion alternatives.

Additional prospective API precision: StepV2 is a plain immutable dataclass and its constructor does NOT validate. `step()` validates its count/canonical constructed Step (Step refusal), even for a spent adapter; it computes metadata only. `intent()` independently validates all fields and context. P02 constructs malformed StepV2 with dataclasses.replace; P11 can patch only the relevant validator for a mutant. No invalid construction alone authorizes storage.

The fixed owner string is `host-adapter-v1` (strict nonempty str). Adapter accepts StorageFixture subclasses, as required for controlled fault injection; only synthetic fixtures, never native storage. Reads are sequential by index: begin_read0, read0 untilTrue, begin_read1, read1 untilTrue, etc. No next begin_read until previous completion; every admission waits for ALL reads complete. Same-selection alien-receipt tests use the fixed owner and a separate standalone storage, not a replacement adapter storage.

Constitution-compliance check: these prospective pure/terminal rules and literals repair principle I/III ambiguity without weakening any gate or extending execution scope; Governance lines166–168 check retained. Independent review remains required before implementation.

## Final-review01 repairs and clarified observations

Lost external authority is per-lease, never a reason to abandon still-owned siblings. Cleanup catches only Stale/Owner lookup refusals, records `(index,code)` in bounded read-only `cleanup_refusals`, emits `orphan:i:code`, skips that lease in both passes, and continues normal sibling cleanup. The skipped foreign lease remains charged; no fake cancellation/completion or foreign-owner reclaim occurs. The adapter then clears its own proposal/copies/registries, terminates the intent, and returns its logical ledger to idle. Operational failure still propagates the ORIGINAL exception. A different unexpected cleanup exception is retained as a chained cause and bounded cleanup_errors observation; no cleanup success is claimed in that case.

Literal transferred-ready K case: before=(16,208,0,24,0,0),slots3,g1110,Aactive. K old token Stale is recorded and skipped; cancelS→(16,80,0,16,0,0); S release/evict removes its slot; T release→(16,80,0,8,0,0),slots2,g1110,Aidle. Context unchanged, commit0, intent terminal; cleanup_refusals=((0,'Stale'),). Only the rightful external K owner may then cancel/release/evict its transferred token, yieldingT16slot1. The test never impersonates the adapter owner to clean S/T. This preserves the custody boundary while satisfying sibling cleanup; it is not a physical/native lifetime claim.

Every mutant assertion is now paired with an unmodified control. Only explicit unittest OracleFailure mismatches count as detection; a frozen internal plain AssertionError is not a witness. Missing completion after only K acknowledgement is directly checked: Completion; error:commit:-1; real completed drain acks S/T; no commit; unchanged context; terminalT16slot1,g1110,Aidle. Token/storage/slot tests consistently substitute all private proof aliases, so identity shortcuts cannot mask a removed individual field comparison. Their three mutants remove ONLY the corresponding comparison. Required-set omission and altered digest use separate check seams rather than the same blanket validator stub.

The canonical success test now compares the complete ordered34-event sequence, including every ledger, slot count, generation vector and adapter-ledger column. It checks unpin/release rows explicitly. A spy verifies that the actual frozen Engine.prepare is invoked only after all three real mock dispatches are pending and pinned, with the exact literal operands.

Event capacity admission accounts the entire bounded graph before intent's logical reservation: existing events+56 must fit the64-event normal envelope, with a separate128 hard cap. Drain verifies room for a conservative32-event cleanup bound before mutation. Eight prior metadata resets allow a step; nine refuse LogicalBudget at intent with zero storage effects and idle adapter ledger. This prevents a late event-budget failure from wedging admitted work. Repeated pure refusals/queries emit nothing.

`reset(request)` is explicitly a global serialized barrier for this ONE-active-intent adapter: it cancels/drains any outstanding intent even if the target request differs, resets only the named context, and leaves the other model context unchanged. This is conservative host-only behavior, not independent concurrent scheduling. Unknown snapshot/step/reset requests preserve the frozen ValueError('UNKNOWN_CONTEXT') boundary; source/model constructor validators likewise remain their frozen bounded ValueError refusals. They do not mutate state/storage. No implicit numerical or context-domain extension is introduced.

Constitution-compliance check: these repairs address final-review01 F1–F3 and advisories within the owned addendum, retaining original frozen source, bounds and gates. Exact renewed source/test/build review remains mandatory before commit.
