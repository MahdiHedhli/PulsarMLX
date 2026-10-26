use backend::step::*;
use backend::*;
use std::cell::Cell;
use std::sync::Arc;

fn err(code: &'static str) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidStateTransition,
        code,
        "injected host fault",
    )
}
fn identity() -> CheckpointIdentity {
    CheckpointIdentity::try_new("a".repeat(64), "synthetic-v1").unwrap()
}
fn tensor(name: &str, offset: u64, length: u64) -> RuntimeTensor {
    RuntimeTensor {
        name: name.into(),
        shard: "fixture".into(),
        range: TensorRange { offset, length },
        shape: vec![length / 4],
        quantization: "fixture-u32-le".into(),
    }
}
fn request() -> StepRequest {
    StepRequest {
        id: "step-0".into(),
        checkpoint: identity(),
        expected_position: 0,
        inputs: vec![tensor("a", 0, 4), tensor("b", 4, 4)],
        layers: vec![1, 2],
        scratch_bytes: 4,
        output_bytes: 4,
    }
}
struct Catalog {
    tensors: Vec<RuntimeTensor>,
    cancel: Option<CancellationToken>,
}
impl TensorCatalog for Catalog {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        if let Some(token) = &self.cancel {
            token.cancel();
        }
        Ok(self.tensors.iter().find(|t| t.name == name).cloned())
    }
}
#[derive(Clone, Copy)]
enum ReadFault {
    None,
    Error,
    Short,
    Cancel,
    Overreport,
}
struct Store {
    calls: Cell<usize>,
    fault: ReadFault,
}
impl HostTensorStore for Store {
    fn validate_range(&self, t: &RuntimeTensor) -> Result<(), ContractError> {
        if t.shard != "fixture"
            || t.range.end()? > 8
            || t.quantization != "fixture-u32-le"
            || t.shape.iter().product::<u64>().checked_mul(4) != Some(t.range.length)
        {
            return Err(err("fixture_range"));
        }
        Ok(())
    }
}
impl TensorStore for Store {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        bytes: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        self.calls.set(self.calls.get() + 1);
        match self.fault {
            ReadFault::Error => return Err(err("fixture_read_error")),
            ReadFault::Short => return Ok(bytes.len() - 1),
            ReadFault::Overreport => return Ok(bytes.len() + 1),
            ReadFault::Cancel => cancellation.cancel(),
            ReadFault::None => {}
        }
        let payload = [7_u32.to_le_bytes(), 11_u32.to_le_bytes()].concat();
        let start = tensor.range.offset as usize;
        bytes.copy_from_slice(&payload[start..start + tensor.range.length as usize]);
        Ok(bytes.len())
    }
}
#[derive(Clone, Copy, Default)]
enum Fault {
    #[default]
    None,
    Stage,
    Backend,
    StaleId,
    StalePosition,
    StaleLayer,
    WrongSize,
    WrongHandle,
    CancelBackend,
    Cleanup,
    BackendAndCleanup,
}
struct Backend {
    inner: U32FixtureBackend,
    fault: Fault,
    stages: usize,
    finishes: usize,
}
impl Backend {
    fn new(fault: Fault) -> Self {
        Self {
            inner: U32FixtureBackend::default(),
            fault,
            stages: 0,
            finishes: 0,
        }
    }
}
impl LayerExecutor for Backend {
    fn execute_layer(
        &mut self,
        req: LayerRequest,
        token: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        if matches!(self.fault, Fault::Backend | Fault::BackendAndCleanup) {
            return Err(err("fixture_backend_error"));
        }
        let result = self.inner.execute_layer(req, token)?;
        if matches!(self.fault, Fault::CancelBackend) {
            token.cancel();
        }
        Ok(result)
    }
}
impl HostLayerExecutor for Backend {
    fn stage(
        &mut self,
        req: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        token: &CancellationToken,
    ) -> Result<(), ContractError> {
        self.stages += 1;
        self.inner.stage(req, inputs, scratch, token)?;
        if matches!(self.fault, Fault::Stage) {
            return Err(err("fixture_stage_error"));
        }
        Ok(())
    }
    fn take_output(&mut self, buffer: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        let mut output = self.inner.take_output(buffer)?;
        match self.fault {
            Fault::StaleId => output.step_id = "other".into(),
            Fault::StalePosition => output.request.generation_position += 1,
            Fault::StaleLayer => output.request.layer += 1,
            Fault::WrongSize => output.bytes.push(0),
            Fault::WrongHandle => output.buffer.slot_id += 1,
            _ => {}
        }
        Ok(output)
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.finishes += 1;
        self.inner.finish()?;
        if matches!(self.fault, Fault::Cleanup | Fault::BackendAndCleanup) {
            return Err(err("fixture_cleanup_error"));
        }
        Ok(())
    }
}
struct FinishCancellation {
    inner: Backend,
    token: CancellationToken,
}
impl LayerExecutor for FinishCancellation {
    fn execute_layer(
        &mut self,
        req: LayerRequest,
        token: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        self.inner.execute_layer(req, token)
    }
}
impl HostLayerExecutor for FinishCancellation {
    fn stage(
        &mut self,
        req: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        token: &CancellationToken,
    ) -> Result<(), ContractError> {
        self.inner.stage(req, inputs, scratch, token)
    }
    fn take_output(&mut self, buffer: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        self.inner.take_output(buffer)
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.inner.finish()?;
        self.token.cancel();
        Ok(())
    }
}
fn catalog(req: &StepRequest) -> Catalog {
    Catalog {
        tensors: req.inputs.clone(),
        cancel: None,
    }
}
fn store(fault: ReadFault) -> Store {
    Store {
        calls: Cell::new(0),
        fault,
    }
}
fn coordinator(fault: Fault, budget: u64) -> StepCoordinator<Backend> {
    StepCoordinator::new(
        identity(),
        MemoryBudget::try_new(4096, 1024, budget).unwrap(),
        GenerationState::default(),
        Backend::new(fault),
    )
    .unwrap()
}
fn no_leases<B: HostLayerExecutor>(coordinator: &StepCoordinator<B>) {
    assert_eq!(
        (
            coordinator.active_reservations(),
            coordinator.active_reservation_bytes()
        ),
        (0, 0)
    );
}

#[test]
fn actual_coordinator_success_next_step_and_replay_commit_once_each() {
    let mut host = coordinator(Fault::None, 128);
    let mut req = request();
    let fixture = catalog(&req);
    let input = store(ReadFault::None);
    let token = CancellationToken::new();
    let first = host
        .execute(&req, &fixture, &input, &token, |out| {
            assert_eq!(out.token, 21);
            assert_eq!(out.position, 1);
            Ok(())
        })
        .unwrap();
    assert_eq!(first.committed.bytes, 21_u32.to_le_bytes());
    assert_eq!(host.state().tokens(), [21]);
    assert_eq!(host.state().position(), 1);
    assert_eq!(
        (
            host.backend().inner.dispatches(),
            host.backend().stages,
            host.backend().finishes
        ),
        (2, 1, 1)
    );
    assert!(!host.backend().inner.has_staged_resources());
    no_leases(&host);
    let replay = host
        .execute(&req, &fixture, &input, &token, |_| Ok(()))
        .unwrap();
    assert!(replay.replayed);
    assert!(Arc::ptr_eq(&first.committed, &replay.committed));
    assert_eq!(input.calls.get(), 2);
    req.expected_position = 1; // Same token and same textual ID at a NEW position is valid.
    let second = host
        .execute(&req, &fixture, &input, &token, |_| Ok(()))
        .unwrap();
    assert!(!second.replayed);
    assert_eq!(host.state().tokens(), [21, 21]);
    assert_eq!(host.state().position(), 2);
    assert_eq!(host.backend().inner.dispatches(), 4);
    req.expected_position = 0;
    assert_eq!(
        host.execute(&req, &fixture, &input, &token, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_already_committed"
    );
    assert_eq!(host.backend().inner.dispatches(), 4);
    no_leases(&host);
}

#[test]
fn full_preflight_failures_have_zero_reads_dispatches_and_state_changes() {
    for case in 0..12 {
        let mut req = request();
        let mut cat = catalog(&req);
        let mut budget = 128;
        let code = match case {
            0 => {
                req.expected_position = 1;
                "step_position_mismatch"
            }
            1 => {
                cat.tensors.pop();
                "step_tensor_mismatch"
            }
            2 => {
                req.inputs[1].range.offset = 8;
                cat = catalog(&req);
                "fixture_range"
            }
            3 => {
                budget = 19;
                "step_budget_exceeded"
            }
            4 => {
                req.inputs[1].range.offset = u64::MAX;
                cat = catalog(&req);
                "tensor_range_overflow"
            }
            5 => {
                req.scratch_bytes = u64::MAX;
                "step_size_overflow"
            }
            6 => {
                req.inputs[1].shape = vec![u64::MAX, 2];
                cat = catalog(&req);
                "step_shape_overflow"
            }
            7 => {
                req.id = "../private".into();
                "invalid_step_identifier"
            }
            8 => {
                req.layers = vec![1, 1];
                "duplicate_step_layer"
            }
            9 => {
                req.checkpoint.immutable_revision = "other".into();
                "step_checkpoint_mismatch"
            }
            10 => {
                req.inputs[1] = req.inputs[0].clone();
                "duplicate_step_input"
            }
            _ => {
                req.output_bytes = 0;
                "invalid_step_shape"
            }
        };
        let mut host = coordinator(Fault::None, budget);
        let initial = host.state().clone();
        let source = store(ReadFault::None);
        let failure = host
            .execute(&req, &cat, &source, &CancellationToken::new(), |_| {
                panic!("no precommit delivery")
            })
            .unwrap_err();
        assert_eq!(failure.error.code(), code, "case {case}");
        assert_eq!(source.calls.get(), 0, "case {case}");
        assert_eq!(host.backend().stages, 0);
        assert_eq!(host.backend().inner.dispatches(), 0);
        assert_eq!(host.state(), &initial);
        assert!(host.retained().is_none());
        no_leases(&host);
    }
}

#[test]
fn cancellation_before_io_after_read_and_during_backend_never_commits() {
    for when in 0..4 {
        let req = request();
        let token = CancellationToken::new();
        let mut cat = catalog(&req);
        let source = store(if when == 2 {
            ReadFault::Cancel
        } else {
            ReadFault::None
        });
        let mut host = coordinator(
            if when == 3 {
                Fault::CancelBackend
            } else {
                Fault::None
            },
            128,
        );
        if when == 0 {
            token.cancel();
        }
        if when == 1 {
            cat.cancel = Some(token.clone());
        }
        let failure = host
            .execute(&req, &cat, &source, &token, |_| panic!("no delivery"))
            .unwrap_err();
        assert_eq!(failure.error.code(), "cancelled");
        assert_eq!(host.state(), &GenerationState::default());
        assert!(!host.backend().inner.has_staged_resources());
        assert_eq!(
            source.calls.get(),
            if when < 2 {
                0
            } else if when == 2 {
                1
            } else {
                2
            }
        );
        no_leases(&host);
    }
}

#[test]
fn cancellation_at_final_precommit_boundary_discards_owned_output() {
    let req = request();
    let token = CancellationToken::new();
    let backend = FinishCancellation {
        inner: Backend::new(Fault::None),
        token: token.clone(),
    };
    let mut host = StepCoordinator::new(
        identity(),
        MemoryBudget::try_new(4096, 1024, 128).unwrap(),
        GenerationState::default(),
        backend,
    )
    .unwrap();
    let error = host
        .execute(
            &req,
            &catalog(&req),
            &store(ReadFault::None),
            &token,
            |_| panic!("no delivery"),
        )
        .unwrap_err();
    assert_eq!(error.error.code(), "cancelled");
    assert_eq!(host.state(), &GenerationState::default());
    assert_eq!(host.backend().inner.finishes, 1);
    assert!(!host.backend().inner.inner.has_staged_resources());
    assert!(host.retained().is_none());
    no_leases(&host);
}

#[test]
fn exact_read_failures_and_backend_faults_release_every_reservation() {
    let req = request();
    for (fault, code) in [
        (ReadFault::Error, "fixture_read_error"),
        (ReadFault::Short, "step_short_read"),
        (ReadFault::Overreport, "step_short_read"),
    ] {
        let mut host = coordinator(Fault::None, 128);
        let source = store(fault);
        let failure = host
            .execute(
                &req,
                &catalog(&req),
                &source,
                &CancellationToken::new(),
                |_| panic!("no delivery"),
            )
            .unwrap_err();
        assert_eq!(failure.error.code(), code);
        assert_eq!(host.state(), &GenerationState::default());
        assert_eq!(host.backend().stages, 0);
        assert_eq!(source.calls.get(), 1);
        no_leases(&host);
    }
    for (fault, code) in [
        (Fault::Stage, "fixture_stage_error"),
        (Fault::Backend, "fixture_backend_error"),
        (Fault::StaleId, "invalid_step_output"),
        (Fault::StalePosition, "invalid_step_output"),
        (Fault::StaleLayer, "invalid_step_output"),
        (Fault::WrongSize, "invalid_step_output"),
        (Fault::WrongHandle, "invalid_step_output"),
        (Fault::Cleanup, "fixture_cleanup_error"),
    ] {
        let mut host = coordinator(fault, 128);
        let failure = host
            .execute(
                &req,
                &catalog(&req),
                &store(ReadFault::None),
                &CancellationToken::new(),
                |_| panic!("no delivery"),
            )
            .unwrap_err();
        assert_eq!(failure.error.code(), code);
        assert_eq!(host.state(), &GenerationState::default());
        assert_eq!(host.backend().finishes, 1);
        assert!(!host.backend().inner.has_staged_resources());
        no_leases(&host);
    }
}

#[test]
fn cleanup_failure_preserves_primary_error_and_poisoned_backend_is_not_redispatched() {
    let req = request();
    let mut host = coordinator(Fault::BackendAndCleanup, 128);
    let first = host
        .execute(
            &req,
            &catalog(&req),
            &store(ReadFault::None),
            &CancellationToken::new(),
            |_| Ok(()),
        )
        .unwrap_err();
    assert_eq!(first.error.code(), "fixture_backend_error");
    assert_eq!(first.cleanup_error.unwrap().code(), "fixture_cleanup_error");
    assert!(!host.backend().inner.has_staged_resources());
    assert_eq!(
        host.execute(
            &req,
            &catalog(&req),
            &store(ReadFault::None),
            &CancellationToken::new(),
            |_| Ok(())
        )
        .unwrap_err()
        .error
        .code(),
        "backend_cleanup_required"
    );
    assert_eq!(host.backend().stages, 1);
    assert_eq!(host.state(), &GenerationState::default());
    no_leases(&host);
}

#[test]
fn delivery_failure_is_committed_retained_and_retry_never_redispatches() {
    let req = request();
    let mut host = coordinator(Fault::None, 128);
    let source = store(ReadFault::None);
    let token = CancellationToken::new();
    let first = host
        .execute(&req, &catalog(&req), &source, &token, |_| {
            token.cancel();
            Err(err("delivery_failed"))
        })
        .unwrap();
    assert_eq!(first.delivery_error.unwrap().code(), "delivery_failed");
    assert!(!first.replayed);
    assert_eq!(host.state().tokens(), [21]);
    assert_eq!(host.state().position(), 1);
    assert!(Arc::ptr_eq(host.retained().unwrap(), &first.committed));
    let second = host
        .execute(&req, &catalog(&req), &source, &token, |out| {
            assert_eq!(out.bytes, 21_u32.to_le_bytes());
            Ok(())
        })
        .unwrap();
    assert!(second.replayed);
    assert!(second.delivery_error.is_none());
    assert!(Arc::ptr_eq(&first.committed, &second.committed));
    assert_eq!(host.backend().inner.dispatches(), 2);
    assert_eq!(source.calls.get(), 2);
    assert_eq!(host.state().position(), 1);
    let mut changed = req.clone();
    changed.layers = vec![3];
    assert_eq!(
        host.execute(&changed, &catalog(&req), &source, &token, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_identity_mismatch"
    );
    no_leases(&host);
}

#[test]
fn independent_request_cancellation_and_repeated_steps_do_not_leak_slots() {
    let mut host = coordinator(Fault::None, 2048);
    let mut req = request();
    let cat = catalog(&req);
    let source = store(ReadFault::None);
    let cancelled = CancellationToken::new();
    cancelled.cancel();
    assert_eq!(
        host.execute(&req, &cat, &source, &cancelled, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "cancelled"
    );
    for position in 0..100 {
        req.expected_position = position;
        req.id = format!("step-{position}");
        host.execute(&req, &cat, &source, &CancellationToken::new(), |_| Ok(()))
            .unwrap();
        assert_eq!(host.state().position(), position + 1);
        assert_eq!(host.state().tokens().len() as u64, position + 1);
        assert!(!host.backend().inner.has_staged_resources());
        no_leases(&host);
    }
    assert_eq!(host.backend().inner.dispatches(), 200);
    assert!(host.peak_reservation_bytes() <= 2048);
}

#[test]
fn retained_output_and_growing_token_history_are_part_of_next_reservation() {
    let mut host = coordinator(Fault::None, 20);
    let first = request();
    let source = store(ReadFault::None);
    let cat = catalog(&first);
    let token = CancellationToken::new();
    host.execute(&first, &cat, &source, &token, |_| Ok(()))
        .unwrap();
    let before = host.state().clone();
    let mut next = first.clone();
    next.expected_position = 1;
    assert_eq!(
        host.execute(&next, &cat, &source, &token, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_budget_exceeded"
    );
    assert_eq!(host.state(), &before);
    assert_eq!(source.calls.get(), 2);
    assert_eq!(host.backend().inner.dispatches(), 2);
    assert!(
        host.execute(&first, &cat, &source, &token, |_| Ok(()))
            .unwrap()
            .replayed
    );
    no_leases(&host);
}

#[test]
fn postcommit_telemetry_error_is_reported_with_retained_committed_output() {
    struct FailedTelemetry;
    impl TelemetrySink for FailedTelemetry {
        fn record(&mut self, _: RuntimeTelemetryEvent) -> Result<(), ContractError> {
            Err(err("telemetry_failed"))
        }
    }
    let req = request();
    let mut host = coordinator(Fault::None, 128);
    let mut telemetry = FailedTelemetry;
    let outcome = host
        .execute(
            &req,
            &catalog(&req),
            &store(ReadFault::None),
            &CancellationToken::new(),
            |out| {
                telemetry.record(RuntimeTelemetryEvent {
                    category: TelemetryCategory::Compute,
                    scope: TelemetryScope {
                        layer: Some(2),
                        expert: None,
                    },
                    elapsed: std::time::Duration::ZERO,
                    bytes: out.bytes.len() as u64,
                    requests: 2,
                })
            },
        )
        .unwrap();
    assert_eq!(outcome.delivery_error.unwrap().code(), "telemetry_failed");
    assert_eq!(host.state().position(), 1);
    assert_eq!(host.state().tokens(), [21]);
    assert!(Arc::ptr_eq(host.retained().unwrap(), &outcome.committed));
    no_leases(&host);
}
