//! Serial host orchestration over the existing storage and layer contracts.
//!
//! The linearization point is the prepared generation-token commit followed immediately
//! by installing the already-owned retained result. No user code or fallible work
//! runs between those writes. This is single-owner, in-memory idempotency, not
//! crash durability or a transaction over native/KV backend effects.
//!
//! Only the most recent result is retained. Older positions return an explicit
//! already-committed error; they are never redispatched. Delivery may be repeated.
//! Logical payload reservations include owned inputs, scratch, outputs and token
//! history, not total process RSS or copies retained by callers after delivery.

use crate::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, GenerationState,
    LayerExecutor, LayerRequest, MemoryBudget, RuntimeBuffer, RuntimeTensor, TensorCatalog,
    TensorStore,
};
use std::cell::Cell;
use std::rc::Rc;
use std::sync::Arc;

pub const MAX_STEP_INPUTS: usize = 64;
pub const MAX_STEP_LAYERS: usize = 64;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StepRequest {
    pub id: String,
    pub checkpoint: CheckpointIdentity,
    pub expected_position: u64,
    pub inputs: Vec<RuntimeTensor>,
    pub layers: Vec<u32>,
    pub scratch_bytes: u64,
    pub output_bytes: u64,
}

/// Storage admission must validate the entire descriptor/range and physical
/// shard bounds without I/O. Immutable fixture sources are appropriate here.
/// Native checkpoint identity/custody remains a separately gated attachment.
pub trait HostTensorStore: TensorStore {
    fn validate_range(&self, tensor: &RuntimeTensor) -> Result<(), ContractError>;
}

#[derive(Debug)]
pub struct LoadedTensor {
    pub descriptor: RuntimeTensor,
    pub bytes: Vec<u8>,
}

#[derive(Debug)]
pub struct LayerOutput {
    pub step_id: String,
    pub request: LayerRequest,
    pub buffer: RuntimeBuffer,
    pub token: u32,
    /// Owned bytes, never a borrowed view into a released scratch slot.
    pub bytes: Vec<u8>,
}

/// Explicit future backend attachment: implementations must be stateless or own
/// a discardable proposal. `finish` must discard staged resources on every path.
/// Native/KV state is NOT qualified by implementing this host interface.
pub trait HostLayerExecutor: LayerExecutor {
    /// Additional bounded logical payload owned by the executor, beyond loaded
    /// inputs, the coordinator's scratch Vec and returned output. Preflight only:
    /// no I/O, allocation or mutation. Existing adapters retain their contract.
    fn working_bytes(&self) -> u64 {
        0
    }
    fn stage(
        &mut self,
        request: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<(), ContractError>;
    fn take_output(&mut self, buffer: RuntimeBuffer) -> Result<LayerOutput, ContractError>;
    fn finish(&mut self) -> Result<(), ContractError>;
}

/// Concrete adapter: binds real storage inputs, calls LayerExecutor for every
/// requested layer, and transfers an owned output. Cleanup runs even on failure.
pub struct LayerStepAdapter<B> {
    backend: B,
    ready: bool,
}

impl<B: HostLayerExecutor> LayerStepAdapter<B> {
    pub fn new(backend: B) -> Self {
        Self {
            backend,
            ready: true,
        }
    }
    pub fn backend(&self) -> &B {
        &self.backend
    }
    fn run(
        &mut self,
        request: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<LayerOutput, StepFailure> {
        if !self.ready {
            return Err(failure("backend_cleanup_required"));
        }
        let result = (|| {
            self.backend.stage(request, inputs, scratch, cancellation)?;
            cancellation.check()?;
            let mut last = None;
            for &layer in &request.layers {
                cancellation.check()?;
                let buffer = self.backend.execute_layer(
                    LayerRequest {
                        layer,
                        generation_position: request.expected_position,
                    },
                    cancellation,
                )?;
                cancellation.check()?;
                last = Some(buffer);
            }
            let buffer = last.ok_or_else(|| error("empty_step_layers"))?;
            let output = self.backend.take_output(buffer)?;
            if output.step_id != request.id
                || output.request.generation_position != request.expected_position
                || Some(output.request.layer) != request.layers.last().copied()
                || output.buffer != buffer
                || buffer.byte_length != request.output_bytes
                || output.bytes.len() as u64 != request.output_bytes
            {
                return Err(error("invalid_step_output"));
            }
            Ok(output)
        })();
        // An uncertain backend release poisons this adapter until it is replaced.
        let cleanup = self.backend.finish();
        if cleanup.is_err() {
            self.ready = false;
        }
        match (result, cleanup) {
            (Ok(output), Ok(())) => Ok(output),
            (Err(primary), cleanup) => Err(StepFailure {
                error: primary,
                cleanup_error: cleanup.err(),
            }),
            (Ok(_), Err(primary)) => Err(StepFailure {
                error: primary,
                cleanup_error: None,
            }),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommittedStep {
    pub id: String,
    pub previous_position: u64,
    pub position: u64,
    pub token: u32,
    pub bytes: Vec<u8>,
}

/// Every successful return reports COMMITTED, including delivery failure.
#[derive(Debug)]
pub struct StepOutcome {
    pub committed: Arc<CommittedStep>,
    pub replayed: bool,
    pub delivery_error: Option<ContractError>,
}

/// This error means no generation-state commit occurred. Preserve a secondary
/// cleanup failure alongside the primary failure; neither is silently replaced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StepFailure {
    pub error: ContractError,
    pub cleanup_error: Option<ContractError>,
}
impl From<ContractError> for StepFailure {
    fn from(error: ContractError) -> Self {
        Self {
            error,
            cleanup_error: None,
        }
    }
}
impl std::fmt::Display for StepFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.error)?;
        if let Some(cleanup) = &self.cleanup_error {
            write!(f, "; cleanup: {cleanup}")?;
        }
        Ok(())
    }
}
impl std::error::Error for StepFailure {}

#[derive(Default)]
struct Resources {
    bytes: Cell<u64>,
    leases: Cell<u64>,
    peak: Cell<u64>,
}
struct Reservation {
    resources: Rc<Resources>,
}
impl Drop for Reservation {
    fn drop(&mut self) {
        self.resources.bytes.set(0);
        self.resources.leases.set(0);
    }
}

pub struct StepCoordinator<B> {
    checkpoint: CheckpointIdentity,
    memory: MemoryBudget,
    state: GenerationState,
    adapter: LayerStepAdapter<B>,
    retained: Option<(StepRequest, Arc<CommittedStep>)>,
    resources: Rc<Resources>,
}

impl<B: HostLayerExecutor> StepCoordinator<B> {
    pub fn new(
        checkpoint: CheckpointIdentity,
        memory: MemoryBudget,
        state: GenerationState,
        backend: B,
    ) -> Result<Self, ContractError> {
        CheckpointIdentity::try_new(
            &checkpoint.checkpoint_set_sha256,
            &checkpoint.immutable_revision,
        )?;
        MemoryBudget::try_new(
            memory.host_total_bytes,
            memory.safety_reserve_bytes,
            memory.max_resident_bytes,
        )?;
        Ok(Self {
            checkpoint,
            memory,
            state,
            adapter: LayerStepAdapter::new(backend),
            retained: None,
            resources: Rc::default(),
        })
    }
    pub fn state(&self) -> &GenerationState {
        &self.state
    }
    pub fn backend(&self) -> &B {
        self.adapter.backend()
    }
    pub fn active_reservation_bytes(&self) -> u64 {
        self.resources.bytes.get()
    }
    pub fn active_reservations(&self) -> u64 {
        self.resources.leases.get()
    }
    pub fn peak_reservation_bytes(&self) -> u64 {
        self.resources.peak.get()
    }
    pub fn retained(&self) -> Option<&Arc<CommittedStep>> {
        self.retained.as_ref().map(|(_, output)| output)
    }

    /// Borrow the exact retained request for a pending-delivery protocol. This
    /// avoids another owning request/history copy in a generation driver.
    pub fn retained_request(&self) -> Option<&StepRequest> {
        self.retained.as_ref().map(|(request, _)| request)
    }

    /// Run one host step. `deliver` is a post-commit hook for transport and/or
    /// telemetry; any returned hook error is reported with retained COMMITTED
    /// output. It never converts the completed step into a precommit failure.
    pub fn execute<
        C: TensorCatalog,
        S: HostTensorStore,
        D: FnMut(&CommittedStep) -> Result<(), ContractError>,
    >(
        &mut self,
        request: &StepRequest,
        catalog: &C,
        store: &S,
        cancellation: &CancellationToken,
        mut deliver: D,
    ) -> Result<StepOutcome, StepFailure> {
        // Replay precedes cancellation: a committed step is never rewound or
        // recomputed, even if its original request has since been cancelled.
        if let Some((previous, output)) = &self.retained {
            if request.id == previous.id && request.expected_position == previous.expected_position
            {
                if request != previous {
                    return Err(failure("step_identity_mismatch"));
                }
                let output = Arc::clone(output);
                let delivery_error = deliver(&output).err();
                return Ok(StepOutcome {
                    committed: output,
                    replayed: true,
                    delivery_error,
                });
            }
        }
        if request.expected_position < self.state.position() {
            return Err(failure("step_already_committed"));
        }
        cancellation.check()?;
        let reservation_bytes = self.preflight(request, catalog, store)?;
        cancellation.check()?;
        self.resources.bytes.set(reservation_bytes);
        self.resources.leases.set(1);
        self.resources
            .peak
            .set(self.resources.peak.get().max(reservation_bytes));
        let reservation = Reservation {
            resources: Rc::clone(&self.resources),
        };
        let mut inputs = Vec::new();
        inputs
            .try_reserve_exact(request.inputs.len())
            .map_err(|_| allocation_error())?;
        let mut scratch = buffer(request.scratch_bytes)?;
        for descriptor in &request.inputs {
            cancellation.check()?;
            let mut bytes = buffer(descriptor.range.length)?;
            let actual = store.read_range(descriptor, &mut bytes, cancellation)?;
            if actual != bytes.len() {
                return Err(failure("step_short_read"));
            }
            cancellation.check()?;
            inputs.push(LoadedTensor {
                descriptor: descriptor.clone(),
                bytes,
            });
        }
        let proposal = self
            .adapter
            .run(request, &inputs, &mut scratch, cancellation)?;
        // Rust-owned scratch releases are infallible; backend finish already
        // completed successfully. Output bytes have independent ownership.
        drop(inputs);
        drop(scratch);
        let committed = Arc::new(CommittedStep {
            id: request.id.clone(),
            previous_position: request.expected_position,
            position: request
                .expected_position
                .checked_add(1)
                .ok_or_else(|| error("generation_position_overflow"))?,
            token: proposal.token,
            bytes: proposal.bytes,
        });
        let retained_request = request.clone();
        if self.state.position() != request.expected_position {
            return Err(failure("step_position_mismatch"));
        }
        let next_position = self.state.prepare_next_token()?;
        cancellation.check()?;
        // LINEARIZATION POINT: capacity/arithmetic are already prepared. Neither
        // this state transition nor installing the owned retained result can fail.
        self.state
            .commit_prepared_token(committed.token, next_position);
        self.retained = Some((retained_request, Arc::clone(&committed)));
        drop(reservation);
        let delivery_error = deliver(&committed).err();
        Ok(StepOutcome {
            committed,
            replayed: false,
            delivery_error,
        })
    }

    fn preflight<C: TensorCatalog, S: HostTensorStore>(
        &self,
        request: &StepRequest,
        catalog: &C,
        store: &S,
    ) -> Result<u64, ContractError> {
        if !self.adapter.ready {
            return Err(error("backend_cleanup_required"));
        }
        identifier(&request.id)?;
        if request.checkpoint != self.checkpoint {
            return Err(error("step_checkpoint_mismatch"));
        }
        if request.expected_position != self.state.position() {
            return Err(error("step_position_mismatch"));
        }
        request
            .expected_position
            .checked_add(1)
            .ok_or_else(|| error("generation_position_overflow"))?;
        if request.inputs.is_empty()
            || request.inputs.len() > MAX_STEP_INPUTS
            || request.layers.is_empty()
            || request.layers.len() > MAX_STEP_LAYERS
            || request.output_bytes == 0
        {
            return Err(error("invalid_step_shape"));
        }
        let mut bytes = checked_sum(request.scratch_bytes, request.output_bytes)?;
        bytes = checked_sum(bytes, self.adapter.backend.working_bytes())?;
        let history = (self.state.tokens().len() as u64)
            .checked_add(1)
            .and_then(|n| n.checked_mul(4))
            .ok_or_else(|| error("step_size_overflow"))?;
        bytes = checked_sum(bytes, history)?;
        if let Some((_, result)) = &self.retained {
            bytes = checked_sum(bytes, result.bytes.len() as u64)?;
        }
        for (index, tensor) in request.inputs.iter().enumerate() {
            identifier(&tensor.name)?;
            identifier(&tensor.shard)?;
            identifier(&tensor.quantization)?;
            if request.inputs[..index]
                .iter()
                .any(|t| t.name == tensor.name)
            {
                return Err(error("duplicate_step_input"));
            }
            if tensor.range.length == 0 || tensor.shape.is_empty() || tensor.shape.len() > 8 {
                return Err(error("invalid_step_tensor"));
            }
            tensor.range.end()?;
            let mut elements = 1_u64;
            for &dim in &tensor.shape {
                if dim == 0 {
                    return Err(error("invalid_step_tensor"));
                }
                elements = elements
                    .checked_mul(dim)
                    .ok_or_else(|| error("step_shape_overflow"))?;
            }
            if catalog.tensor(&tensor.name)?.as_ref() != Some(tensor) {
                return Err(error("step_tensor_mismatch"));
            }
            store.validate_range(tensor)?;
            bytes = checked_sum(bytes, tensor.range.length)?;
        }
        for (index, layer) in request.layers.iter().enumerate() {
            if request.layers[..index].contains(layer) {
                return Err(error("duplicate_step_layer"));
            }
        }
        // Allocation lengths must be representable, even under a forged budget.
        for size in [request.scratch_bytes, request.output_bytes]
            .into_iter()
            .chain(request.inputs.iter().map(|t| t.range.length))
        {
            if size > isize::MAX as u64 {
                return Err(allocation_error());
            }
        }
        if !self.memory.admits(bytes) {
            return Err(ContractError::new(
                ErrorCategory::ResourceLimit,
                "step_budget_exceeded",
                "step exceeds logical host reservation",
            ));
        }
        Ok(bytes)
    }
}

fn identifier(value: &str) -> Result<(), ContractError> {
    if value.is_empty()
        || value.len() > 256
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
    {
        return Err(error("invalid_step_identifier"));
    }
    Ok(())
}
fn checked_sum(a: u64, b: u64) -> Result<u64, ContractError> {
    a.checked_add(b).ok_or_else(|| error("step_size_overflow"))
}
fn allocation_error() -> ContractError {
    ContractError::new(
        ErrorCategory::ResourceLimit,
        "step_allocation_denied",
        "host buffer allocation refused",
    )
}
fn buffer(bytes: u64) -> Result<Vec<u8>, ContractError> {
    let size = usize::try_from(bytes).map_err(|_| allocation_error())?;
    let mut buffer = Vec::new();
    buffer
        .try_reserve_exact(size)
        .map_err(|_| allocation_error())?;
    buffer.resize(size, 0);
    Ok(buffer)
}
fn error(code: &'static str) -> ContractError {
    let category = if code.ends_with("_overflow") {
        ErrorCategory::ArithmeticOverflow
    } else {
        ErrorCategory::InvalidStateTransition
    };
    ContractError::new(category, code, "host step refused")
}
fn failure(code: &'static str) -> StepFailure {
    error(code).into()
}

/// Deterministic CPU fixture computation: sum little-endian u32 inputs, then
/// add each requested layer ID. Its proposal is discarded by finish; this is
/// orchestration evidence, not a model, logits oracle, or native backend.
#[derive(Default)]
pub struct U32FixtureBackend {
    staged: Option<(String, u32, LayerRequest, RuntimeBuffer)>,
    next_slot: u64,
    dispatches: u64,
}
impl U32FixtureBackend {
    pub fn dispatches(&self) -> u64 {
        self.dispatches
    }
    pub fn has_staged_resources(&self) -> bool {
        self.staged.is_some()
    }
}
impl LayerExecutor for U32FixtureBackend {
    fn execute_layer(
        &mut self,
        request: LayerRequest,
        cancellation: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        cancellation.check()?;
        let staged = self
            .staged
            .as_mut()
            .ok_or_else(|| error("fixture_not_staged"))?;
        let value = staged
            .1
            .checked_add(request.layer)
            .ok_or_else(|| error("fixture_value_overflow"))?;
        let slot = self
            .next_slot
            .checked_add(1)
            .ok_or_else(|| error("fixture_slot_overflow"))?;
        let dispatches = self
            .dispatches
            .checked_add(1)
            .ok_or_else(|| error("fixture_dispatch_overflow"))?;
        self.next_slot = slot;
        self.dispatches = dispatches;
        staged.1 = value;
        staged.2 = request;
        staged.3 = RuntimeBuffer {
            slot_id: slot,
            byte_length: 4,
        };
        Ok(staged.3)
    }
}
impl HostLayerExecutor for U32FixtureBackend {
    fn stage(
        &mut self,
        request: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<(), ContractError> {
        cancellation.check()?;
        if self.staged.is_some() || request.output_bytes != 4 || scratch.len() < 4 {
            return Err(error("invalid_fixture_workspace"));
        }
        let mut value = 0_u32;
        for input in inputs {
            if input.descriptor.quantization != "fixture-u32-le" || input.bytes.len() % 4 != 0 {
                return Err(error("invalid_fixture_encoding"));
            }
            for bytes in input.bytes.chunks_exact(4) {
                value = value
                    .checked_add(u32::from_le_bytes(
                        bytes
                            .try_into()
                            .map_err(|_| error("invalid_fixture_encoding"))?,
                    ))
                    .ok_or_else(|| error("fixture_value_overflow"))?;
            }
        }
        scratch[..4].copy_from_slice(&value.to_le_bytes());
        self.staged = Some((
            request.id.clone(),
            value,
            LayerRequest {
                layer: 0,
                generation_position: request.expected_position,
            },
            RuntimeBuffer {
                slot_id: 0,
                byte_length: 4,
            },
        ));
        Ok(())
    }
    fn take_output(&mut self, buffer: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        let (id, token, request, actual) = self
            .staged
            .as_ref()
            .ok_or_else(|| error("fixture_not_staged"))?;
        if *actual != buffer {
            return Err(error("fixture_buffer_mismatch"));
        }
        Ok(LayerOutput {
            step_id: id.clone(),
            request: *request,
            buffer,
            token: *token,
            bytes: token.to_le_bytes().to_vec(),
        })
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.staged = None;
        Ok(())
    }
}
