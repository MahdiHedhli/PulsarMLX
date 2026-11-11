//! Storage/orchestration equality on generated marker bytes.
mod residency_support;
mod support;
use backend::{step::*, *};
use mlx_expert_ranges::residency::*;
use residency_support::*;
use sha2::{Digest, Sha256};
use std::cell::Cell;

fn error(code: &'static str) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidStateTransition,
        code,
        "synthetic host fixture",
    )
}
fn identity() -> CheckpointIdentity {
    CheckpointIdentity::try_new(safetensors_catalog::hex(&CONTENT), "synthetic-packed").unwrap()
}
fn request() -> StepRequest {
    StepRequest {
        id: "fixture-step".into(),
        checkpoint: identity(),
        expected_position: 0,
        layers: vec![7],
        inputs: vec![RuntimeTensor {
            name: "activation".into(),
            shard: "fixture".into(),
            range: TensorRange {
                offset: 0,
                length: 1,
            },
            shape: vec![1],
            quantization: "u8".into(),
        }],
        scratch_bytes: 8,
        output_bytes: 32,
    }
}
struct Inputs(Cell<u64>);
impl TensorCatalog for Inputs {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok(request().inputs.into_iter().find(|t| t.name == name))
    }
}
impl HostTensorStore for Inputs {
    fn validate_range(&self, t: &RuntimeTensor) -> Result<(), ContractError> {
        if t == &request().inputs[0] {
            Ok(())
        } else {
            Err(error("range"))
        }
    }
}
impl TensorStore for Inputs {
    fn read_range(
        &self,
        _: &RuntimeTensor,
        out: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancel.check()?;
        self.0.set(self.0.get() + 1);
        out.copy_from_slice(&[17]);
        Ok(1)
    }
}
struct PackedExecutor {
    cache: CopiedResidency,
    staged: Option<(String, u8, [Demand; 6])>,
    output: Option<LayerOutput>,
    dispatches: usize,
    abort_during_consume: bool,
    fail_finish: bool,
}
impl HostLayerExecutor for PackedExecutor {
    fn working_bytes(&self) -> u64 {
        self.cache.working_bytes()
    }
    fn stage(
        &mut self,
        r: &StepRequest,
        inputs: &[LoadedTensor],
        _: &mut [u8],
        _: &CancellationToken,
    ) -> Result<(), ContractError> {
        CopiedResidency::check_workspace(
            (std::mem::size_of::<[Demand; 6]>() + std::mem::size_of::<Sha256>() + r.id.len() + 128)
                as u64,
        )
        .map_err(|_| error("workspace"))?;
        assert_eq!(inputs.len(), 1);
        assert_eq!(inputs[0].descriptor.name, "activation");
        let keys = [0, 1, 0, 2, 1, 0].map(|e| self.cache.demand(e).unwrap());
        self.staged = Some((r.id.clone(), inputs[0].bytes[0], keys));
        Ok(())
    }
    fn take_output(&mut self, _: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        self.output.take().ok_or(error("no_output"))
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.staged = None;
        self.output = None;
        if self.fail_finish {
            self.cache.quarantine();
            return Err(error("fixture_finish"));
        }
        self.cache.finish().map_err(|_| error("cache_finish"))
    }
}
impl LayerExecutor for PackedExecutor {
    fn execute_layer(
        &mut self,
        request: LayerRequest,
        token: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        self.dispatches += 1;
        let (id, activation, keys) = self.staged.as_ref().ok_or(error("missing_stage"))?;
        let mut h = Sha256::new();
        h.update([*activation]);
        let result = self.cache.consume(
            keys,
            || token.check().is_err(),
            |view| {
                for row in view.components {
                    for component in row {
                        h.update(component);
                    }
                }
                if self.abort_during_consume {
                    token.cancel();
                }
                Ok(())
            },
        );
        if result.is_err() {
            token.check()?;
            return Err(error("packed_cache"));
        }
        let bytes = h.finalize().to_vec();
        let buffer = RuntimeBuffer {
            slot_id: 0,
            byte_length: 32,
        };
        self.output = Some(LayerOutput {
            step_id: id.clone(),
            request,
            buffer,
            token: u32::from_le_bytes(bytes[..4].try_into().unwrap()),
            bytes,
        });
        Ok(buffer)
    }
}
fn host(
    cache: CopiedResidency,
    budget: u64,
    abort: bool,
    fail_finish: bool,
) -> StepCoordinator<PackedExecutor> {
    StepCoordinator::new(
        identity(),
        MemoryBudget::try_new(budget + 128, 128, budget).unwrap(),
        GenerationState::default(),
        PackedExecutor {
            cache,
            staged: None,
            output: None,
            dispatches: 0,
            abort_during_consume: abort,
            fail_finish,
        },
    )
    .unwrap()
}
#[test]
fn exact_once_admission_commit_and_replay_on_real_coordinator() {
    let (fixture, cache) = setup(true);
    let w = cache.working_bytes();
    let mut host = host(cache, w + 45, false, false);
    let store = Inputs(Cell::new(0));
    let mut req = request();
    let cancel = CancellationToken::new();
    let result = host
        .execute(&req, &store, &store, &cancel, |_| Err(error("delivery")))
        .unwrap();
    assert_eq!(result.delivery_error.unwrap().code(), "delivery");
    assert_eq!(host.state().position(), 1);
    let mut expected = Sha256::new();
    expected.update([17]);
    for expert in [0, 1, 0, 2, 1, 0] {
        for role in 0..3 {
            for part in 0..3 {
                expected.update(component(fixture.request.bits, expert, role, part));
            }
        }
    }
    assert_eq!(&result.committed.bytes[..], &expected.finalize()[..]);
    assert_eq!(host.peak_reservation_bytes(), w + 45);
    assert_eq!(host.active_reservation_bytes(), 0);
    assert_eq!(host.backend().cache.read_calls(), 36);
    let stats = host.backend().cache.stats();
    let replay = host
        .execute(&req, &store, &store, &cancel, |_| Ok(()))
        .unwrap();
    assert!(replay.replayed);
    assert!(std::sync::Arc::ptr_eq(&result.committed, &replay.committed));
    req.id = "changed".into();
    assert!(host
        .execute(&req, &store, &store, &cancel, |_| Ok(()))
        .is_err());
    assert_eq!(
        (
            host.state().position(),
            host.backend().dispatches,
            store.0.get()
        ),
        (1, 1, 1)
    );
    assert_eq!(host.backend().cache.stats(), stats);
    assert_eq!(host.backend().cache.read_calls(), 36);
    assert_eq!(host.backend().cache.working_bytes(), w);
    assert!(host.backend().staged.is_none() && host.backend().output.is_none());
}
#[test]
fn one_byte_short_stops_before_reads_dispatch_or_mutation() {
    let (_fixture, cache) = setup(false);
    let w = cache.working_bytes();
    let mut host = host(cache, w + 44, false, false);
    let io = Inputs(Cell::new(0));
    assert_eq!(
        host.execute(&request(), &io, &io, &CancellationToken::new(), |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_budget_exceeded"
    );
    assert_eq!(
        (
            io.0.get(),
            host.backend().cache.read_calls(),
            host.backend().dispatches
        ),
        (0, 0, 0)
    );
    assert_eq!(host.state().position(), 0);
}
#[test]
fn cancellation_and_failed_finish_preserve_primary_and_secondary_errors() {
    for fail in [false, true] {
        let (_fixture, cache) = setup(false);
        let w = cache.working_bytes();
        let mut host = host(cache, w + 45, true, fail);
        let io = Inputs(Cell::new(0));
        let e = host
            .execute(
                &request(),
                &io,
                &io,
                &CancellationToken::new(),
                |_| panic!(),
            )
            .unwrap_err();
        assert_eq!(e.error.code(), {
            let cancelled = CancellationToken::new();
            cancelled.cancel();
            cancelled.check().unwrap_err().code()
        });
        assert_eq!(
            e.cleanup_error.map(|e| e.code()),
            if fail { Some("fixture_finish") } else { None }
        );
        assert_eq!(host.state().position(), 0);
        assert_eq!(host.active_reservation_bytes(), 0);
        let b = host.backend();
        assert_eq!(b.cache.stats().consumed, 1);
        assert_eq!(b.cache.read_calls(), 18);
        assert_eq!(b.cache.working_bytes(), w);
        assert_eq!(b.cache.is_quarantined(), fail);
        assert!(b.staged.is_none() && b.output.is_none());
        if fail {
            assert_eq!(
                host.execute(
                    &request(),
                    &io,
                    &io,
                    &CancellationToken::new(),
                    |_| panic!()
                )
                .unwrap_err()
                .error
                .code(),
                "backend_cleanup_required"
            );
        }
    }
}
