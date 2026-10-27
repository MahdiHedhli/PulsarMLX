# Tiny routed CPU composition

Run the real CPU adapter and real `StepCoordinator`, with frozen independent
reference comparisons and a cancelled delivery retry:

```sh
CARGO_BUILD_JOBS=2 cargo run --locked --offline -p backend --example routed_host_lifecycle
python3 crates/backend/fixtures/routed_cpu_v1/reference.py --check
```

`routed_cpu::TinyMoeCpuBackend` computes projections, SiLU, selected softmax,
expert outputs, residuals and logits from bytes supplied through
`TensorCatalog`/`HostTensorStore`. `RoutingPlan` owns routing/aggregation semantics;
`LayerStepAdapter` invokes both layers. Fixed binary diagnostics own their bytes.
The backend never reads goldens, Python output or model files. The example and
test-only reference reader compare actual results to the frozen Decimal goldens.

`host_generation::HostGeneration` seeds once before coordinator ownership and
borrows all generated tokens/positions from that coordinator. `advance_fixture`
binds fresh embedding inputs to the previous committed token. Pending delivery
exposes the retained request and blocks advancing. Matching retries, including
cancelled ones, reuse the exact retained result; stop rules apply after delivery.
The low-level generic `advance` requires the caller to bind its own input source
to `next_input_token`; backends enforce their vocabulary/output contract.
If another backend violates that contract, the driver preserves its already
committed result and any pending delivery, then returns
`host_token_out_of_vocabulary` from stop/input/advance checks. It never silently
uses the invalid token for a new step or claims that the commit rolled back.
The bounded driver admits 1..8 new tokens; zero is refused. EOS takes precedence
when EOS and the maximum count coincide on the same delivered commit.

Two additive foundation helpers are necessary: `HostLayerExecutor::working_bytes`
declares a preflight-only bound for backend-owned payload, and
`StepCoordinator::retained_request` exposes a borrowed pending request. The old
executor default remains zero and existing execute/commit behavior is unchanged.
The CPU adapter declares a conservative 64 KiB working reservation, separate from
the coordinator's actual scratch Vec (`scratch_bytes=0` here). This covers decoded
weight copies, the fixed proposal/traces, math temporaries, route allocations,
serialization overlap and the tiny convenience caller's bounded request copy.
The coordinator additionally counts loaded inputs, output, retained output and
history. This is the logical working allowance in the prospective fixture spec;
it does not represent a second 64 KiB allocation. Fixed geometry, stack payloads
and request cardinalities remain bounded. Caller-owned fixture/result copies,
allocator capacity and physical RSS are outside the logical guarantee.

All 11 declared inputs are eagerly loaded. Experts are selected for computation,
not selected-only I/O. This is not a pager, native attachment, KV transaction,
attention model, production model, or Qwen/GLM architecture qualification. Outputs
remain owned after cleanup; a cleanup error quarantines the adapter and preserves
primary/secondary failures. Cancellation after the final check can lose to commit.

The prospective spec, independent generator, 80/100-digit stability check,
binary fixture and complete intermediate goldens live in `fixtures/routed_cpu_v1`.
Their comparison policy is unchanged by implementation. Backend code is std-only,
has no build script/native dependencies, and is the only new runnable package.
