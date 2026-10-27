use super::*;
use crate::host_generation::{HostGeneration, HostStop};
use crate::step::StepCoordinator;
use crate::{GenerationState, MemoryBudget};
use std::rc::Rc;
use std::sync::Arc;
#[path = "../tests/support/routed_goldens.rs"]
mod reference;

fn memory() -> MemoryBudget {
    MemoryBudget::try_new(200_000, 10_000, 100_000).unwrap()
}
fn driver<B: HostLayerExecutor>(
    backend: B,
    seed: u32,
    max: u32,
    eos: Option<u32>,
) -> HostGeneration<B> {
    HostGeneration::new(fixture_identity(), memory(), backend, seed, 8, max, eos).unwrap()
}
fn clean<B: HostLayerExecutor>(host: &HostGeneration<B>) {
    assert_eq!(host.coordinator().active_reservations(), 0);
    assert_eq!(host.coordinator().active_reservation_bytes(), 0);
}

#[test]
fn independent_intermediates_routes_ties_max_and_eos() {
    for (case, seed, eos, expected, stop) in [
        (
            "max",
            0,
            None,
            vec![1, 2, 3, 4, 5, 6, 7, 0],
            HostStop::MaxTokens,
        ),
        ("eos", 5, Some(7), vec![6, 7], HostStop::Eos),
    ] {
        let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
        let mut host = driver(TinyMoeCpuBackend::default(), seed, 8, eos);
        let mut routes = std::collections::BTreeSet::new();
        for (step, token) in expected.iter().enumerate() {
            let result =
                advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(()))
                    .unwrap();
            reference::compare(case, &result.committed).unwrap();
            assert_eq!(result.committed.token, *token);
            assert!(!result.replayed);
            assert_eq!(host.coordinator().state().position(), step as u64 + 2);
            assert_eq!(host.generated_tokens(), &expected[..=step]);
            let trace = RoutedTrace::decode(&result.committed.bytes).unwrap();
            routes.insert(trace.layers[0].selected);
            if case == "max" && step == 0 {
                assert_eq!(trace.layers[0].selected, [0, 1]);
                assert_eq!(trace.layers[0].weights, [0.5, 0.5]);
            }
            if case == "max" && step == 7 {
                assert_eq!(trace.logits, [0.0; 8]);
                assert_eq!(result.committed.token, 0);
            }
            clean(&host);
            assert!(!host.coordinator().backend().has_staged_resources());
        }
        assert_eq!(host.stop(), Some(stop));
        assert_eq!(fixture.reads(), expected.len() as u64 * 11);
        assert_eq!(
            host.coordinator().backend().stats(),
            CpuStats {
                stages: expected.len() as u64,
                layers: expected.len() as u64 * 2,
                routes: expected.len() as u64 * 2,
                experts: expected.len() as u64 * 4
            }
        );
        if case == "max" {
            assert!(routes.len() >= 2);
        }
        assert_eq!(
            host.next_input_token().unwrap_err().code(),
            "host_generation_stopped"
        );
    }
}

#[test]
fn pending_delivery_replays_cancelled_exact_result_and_blocks_conflicts() {
    let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
    let mut host = driver(TinyMoeCpuBackend::default(), 0, 8, None);
    let first = advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| {
        Err(err("telemetry_offline"))
    })
    .unwrap();
    assert_eq!(first.delivery_error.unwrap().code(), "telemetry_offline");
    assert_eq!(
        host.next_input_token().unwrap_err().code(),
        "host_delivery_pending"
    );
    let mut conflict = host.pending_request().unwrap().clone();
    conflict.output_bytes += 1;
    let input = fixture.inputs(0).unwrap();
    let before = host.coordinator().backend().stats();
    let reads = fixture.reads();
    assert_eq!(
        host.advance(
            &conflict,
            &input,
            &input,
            &CancellationToken::new(),
            |_| Ok(())
        )
        .unwrap_err()
        .error
        .code(),
        "host_delivery_pending"
    );
    let cancel = CancellationToken::new();
    cancel.cancel();
    let retry = advance_fixture(&mut host, &fixture, &cancel, |_| Ok(())).unwrap();
    assert!(retry.replayed);
    assert!(Arc::ptr_eq(&first.committed, &retry.committed));
    assert_eq!(retry.committed.bytes, first.committed.bytes);
    assert_eq!(host.generated_tokens(), [1]);
    assert_eq!(host.coordinator().state().position(), 2);
    assert_eq!(fixture.reads(), reads);
    assert_eq!(host.coordinator().backend().stats(), before);
    assert!(host.pending_request().is_none());
    clean(&host);
    let next = advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
    reference::compare("max", &next.committed).unwrap();
    assert_eq!(host.generated_tokens(), [1, 2]);
    let mut old = fixture_request(1);
    old.id = "double-commit-attempt".into();
    assert_eq!(
        host.advance(&old, &input, &input, &CancellationToken::new(), |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_already_committed"
    );
    assert_eq!(host.generated_tokens(), [1, 2]);
}

#[test]
fn pending_delivery_is_explicit_at_both_stop_boundaries() {
    for (seed, max, eos, stop) in [
        (0, 1, None, HostStop::MaxTokens),
        (6, 8, Some(7), HostStop::Eos),
        (6, 1, Some(7), HostStop::Eos),
    ] {
        let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
        let mut host = driver(TinyMoeCpuBackend::default(), seed, max, eos);
        advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| {
            Err(err("delivery_offline"))
        })
        .unwrap();
        assert_eq!(host.stop(), None);
        assert!(host.pending_request().is_some());
        advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
        assert_eq!(host.stop(), Some(stop));
        assert_eq!(host.generated_tokens().len(), 1);
        assert_eq!(fixture.reads(), 11);
    }
}

// The fault source is only a test injector around production fixture bytes.
struct Source<'a> {
    bytes: &'a [u8],
    tensors: Vec<RuntimeTensor>,
    token: u32,
    reads: Cell<u64>,
    fail_read: Option<u64>,
}
impl TensorCatalog for Source<'_> {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok(self.tensors.iter().find(|t| t.name == name).cloned())
    }
}
impl HostTensorStore for Source<'_> {
    fn validate_range(&self, t: &RuntimeTensor) -> Result<(), ContractError> {
        if t.range.end()? > 3844 {
            Err(err("injected_invalid_later_range"))
        } else {
            Ok(())
        }
    }
}
impl TensorStore for Source<'_> {
    fn read_range(
        &self,
        t: &RuntimeTensor,
        out: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancel.check()?;
        self.validate_range(t)?;
        let n = self.reads.get() + 1;
        self.reads.set(n);
        if self.fail_read == Some(n) {
            return Err(err("injected_read"));
        }
        if t.name == "input_token" {
            out.copy_from_slice(&self.token.to_le_bytes());
        } else {
            let start = t.range.offset as usize;
            out.copy_from_slice(&self.bytes[start..start + out.len()]);
        }
        Ok(out.len())
    }
}
fn source(bytes: &[u8]) -> Source<'_> {
    Source {
        bytes,
        tensors: fixture_request(1).inputs,
        token: 0,
        reads: Cell::new(0),
        fail_read: None,
    }
}
fn refused(
    host: &mut HostGeneration<TinyMoeCpuBackend>,
    req: &StepRequest,
    s: &Source<'_>,
    code: &str,
    reads: u64,
) {
    let failure = host
        .advance(req, s, s, &CancellationToken::new(), |_| {
            panic!("must not deliver")
        })
        .unwrap_err();
    assert_eq!(failure.error.code(), code);
    assert!(failure.cleanup_error.is_none());
    assert_eq!(s.reads.get(), reads);
    assert!(host.generated_tokens().is_empty());
    assert!(!host.coordinator().backend().has_staged_resources());
    clean(host);
}

#[test]
fn descriptors_ranges_encoding_and_budget_refuse_with_exact_read_effects() {
    let req = fixture_request(1);
    for mutation in 0..3 {
        let mut bad = req.clone();
        match mutation {
            0 => bad.inputs[0].shape = vec![8, 3],
            1 => bad.inputs[0].quantization = "f64-be".into(),
            _ => bad.inputs[0].shard = "other".into(),
        };
        let s = source(FIXTURE_WEIGHTS);
        refused(
            &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
            &bad,
            &s,
            "step_tensor_mismatch",
            0,
        );
    }
    let mut s = source(FIXTURE_WEIGHTS);
    s.tensors[9].range.offset = 3840;
    let mut late = req.clone();
    late.inputs = s.tensors.clone();
    refused(
        &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
        &late,
        &s,
        "injected_invalid_later_range",
        0,
    );
    for mutation in 0..2 {
        let mut s = source(FIXTURE_WEIGHTS);
        if mutation == 0 {
            s.tensors[0].shape = vec![8, 3];
        } else {
            s.tensors[0].quantization = "f64-be".into();
        }
        let mut bad = req.clone();
        bad.inputs = s.tensors.clone();
        refused(
            &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
            &bad,
            &s,
            "tiny_payload_descriptor",
            11,
        );
    }
    let s = source(FIXTURE_WEIGHTS);
    let mut host = HostGeneration::new(
        fixture_identity(),
        MemoryBudget::try_new(200_000, 10_000, 65_536).unwrap(),
        TinyMoeCpuBackend::default(),
        0,
        8,
        8,
        None,
    )
    .unwrap();
    refused(&mut host, &req, &s, "step_budget_exceeded", 0);
}

#[test]
fn non_finite_payload_and_finite_overflow_refuse_before_commit() {
    for (offset, value) in [(256, f64::NAN), (256, f64::INFINITY)] {
        let mut bytes = FIXTURE_WEIGHTS.to_vec();
        bytes[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        let s = source(&bytes);
        refused(
            &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
            &fixture_request(1),
            &s,
            "tiny_non_finite",
            11,
        );
    }
    let mut bytes = FIXTURE_WEIGHTS.to_vec();
    for offset in (0..32).step_by(8) {
        bytes[offset..offset + 8].copy_from_slice(&f64::MAX.to_le_bytes());
    }
    for offset in (256..384).step_by(8) {
        bytes[offset..offset + 8].copy_from_slice(&f64::MAX.to_le_bytes());
    }
    let s = source(&bytes);
    refused(
        &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
        &fixture_request(1),
        &s,
        "tiny_non_finite",
        11,
    );
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Fault {
    None,
    Early,
    Late,
    MidCancel,
    FinalCancel,
    Cleanup,
    LateCleanup,
    ExpertSwap,
    SlotMismatch,
    OriginalLayerTwo,
    SkipLayer,
    Logits,
}
struct Injected {
    inner: TinyMoeCpuBackend,
    fault: Rc<Cell<Fault>>,
    cancellation: Option<CancellationToken>,
}
impl Injected {
    fn new(fault: Rc<Cell<Fault>>) -> Self {
        Self {
            inner: TinyMoeCpuBackend::default(),
            fault,
            cancellation: None,
        }
    }
}
impl HostLayerExecutor for Injected {
    fn working_bytes(&self) -> u64 {
        CPU_WORKING_BYTES + 4096
    }
    fn stage(
        &mut self,
        r: &StepRequest,
        i: &[LoadedTensor],
        s: &mut [u8],
        c: &CancellationToken,
    ) -> Result<(), ContractError> {
        self.cancellation = Some(c.clone());
        if self.fault.get() == Fault::ExpertSwap {
            let mut changed: Vec<_> = i
                .iter()
                .map(|x| LoadedTensor {
                    descriptor: x.descriptor.clone(),
                    bytes: x.bytes.clone(),
                })
                .collect();
            for index in [2, 3, 4] {
                for byte in 0..128 {
                    changed[index].bytes.swap(byte, 128 + byte);
                }
            }
            self.inner.stage(r, &changed, s, c)
        } else {
            self.inner.stage(r, i, s, c)
        }
    }
    fn take_output(&mut self, b: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        let mut output = self.inner.take_output(b)?;
        if self.fault.get() == Fault::Logits {
            let mut trace = RoutedTrace::decode(&output.bytes)?;
            trace.logits[0] += 0.25;
            output.bytes = trace.encode()?;
        }
        Ok(output)
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        if matches!(self.fault.get(), Fault::Cleanup | Fault::LateCleanup) {
            return Err(err("injected_cleanup"));
        }
        self.inner.finish()?;
        if self.fault.get() == Fault::FinalCancel {
            self.cancellation.as_ref().unwrap().cancel();
        }
        Ok(())
    }
}
impl LayerExecutor for Injected {
    fn execute_layer(
        &mut self,
        r: LayerRequest,
        c: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        let f = self.fault.get();
        if f == Fault::Early && r.layer == 0 {
            return Err(err("injected_early_layer"));
        }
        if matches!(f, Fault::Late | Fault::LateCleanup) && r.layer == 1 {
            return Err(err("injected_late_layer"));
        }
        if f == Fault::OriginalLayerTwo && r.layer == 1 {
            let p = self.inner.proposal.as_mut().unwrap();
            p.x = p.trace.layers[0].input;
        }
        if f == Fault::SkipLayer && r.layer == 1 {
            // Isolated mutant: actually omit the second execute call while
            // forging completion metadata, so the numerical oracle must catch it.
            let p = self.inner.proposal.as_mut().unwrap();
            p.next_layer = 2;
            p.trace.layers[1] = LayerTrace::default();
            return Ok(p.buffer);
        }
        let b = self.inner.execute_layer(r, c)?;
        if f == Fault::MidCancel && r.layer == 0 {
            c.cancel();
        }
        if f == Fault::SlotMismatch && r.layer == 0 {
            let p = self.inner.proposal.as_mut().unwrap();
            let t = &mut p.trace.layers[0];
            for j in 0..4 {
                t.combined[j] = t.weights[1] * t.down[0][j] + t.weights[0] * t.down[1][j];
                t.residual[j] = t.input[j] + t.combined[j];
            }
            p.x = t.residual;
        }
        Ok(b)
    }
}

#[test]
fn precommit_faults_preserve_prefix_and_cleanup_or_quarantine() {
    for (fault, code, secondary, quarantined) in [
        (Fault::Early, "injected_early_layer", None, false),
        (Fault::Late, "injected_late_layer", None, false),
        (Fault::MidCancel, "cancelled", None, false),
        (Fault::FinalCancel, "cancelled", None, false),
        (Fault::Cleanup, "injected_cleanup", None, true),
        (
            Fault::LateCleanup,
            "injected_late_layer",
            Some("injected_cleanup"),
            true,
        ),
    ] {
        let mode = Rc::new(Cell::new(Fault::None));
        let mut host = driver(Injected::new(mode.clone()), 0, 8, None);
        let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
        let first =
            advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
        mode.set(fault);
        let failure = advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| {
            panic!("precommit failure delivered")
        })
        .unwrap_err();
        assert_eq!(failure.error.code(), code);
        assert_eq!(failure.cleanup_error.as_ref().map(|e| e.code()), secondary);
        assert_eq!(host.generated_tokens(), [1]);
        assert_eq!(host.coordinator().state().position(), 2);
        assert_eq!(
            host.coordinator().backend().inner.has_staged_resources(),
            quarantined
        );
        clean(&host);
        reference::compare("max", &first.committed).unwrap();
        mode.set(Fault::None);
        if quarantined {
            let reads = fixture.reads();
            assert_eq!(
                advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(()))
                    .unwrap_err()
                    .error
                    .code(),
                "backend_cleanup_required"
            );
            assert_eq!(fixture.reads(), reads);
        } else {
            advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
            assert_eq!(host.generated_tokens(), [1, 2]);
        }
    }
}

#[test]
fn cancellation_before_reads_and_read_failure_preserve_prefix() {
    let mut host = driver(TinyMoeCpuBackend::default(), 0, 8, None);
    let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
    advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
    let cancel = CancellationToken::new();
    cancel.cancel();
    assert_eq!(
        advance_fixture(&mut host, &fixture, &cancel, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "cancelled"
    );
    assert_eq!(fixture.reads(), 11);
    let mut s = source(FIXTURE_WEIGHTS);
    s.token = 1;
    s.fail_read = Some(3);
    let request = fixture_request(2);
    assert_eq!(
        host.advance(&request, &s, &s, &CancellationToken::new(), |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "injected_read"
    );
    assert_eq!(s.reads.get(), 3);
    assert_eq!(host.generated_tokens(), [1]);
    assert!(!host.coordinator().backend().has_staged_resources());
    clean(&host);
}

#[test]
fn differential_controls_detect_specific_computation_mutants() {
    for fault in [
        Fault::ExpertSwap,
        Fault::SlotMismatch,
        Fault::OriginalLayerTwo,
        Fault::SkipLayer,
        Fault::Logits,
    ] {
        let mode = Rc::new(Cell::new(Fault::None));
        let mut host = driver(Injected::new(mode.clone()), 0, 8, None);
        let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
        // Position 2 has asymmetric selected probabilities; a slot mismatch is visible.
        advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
        mode.set(fault);
        let result =
            advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| Ok(())).unwrap();
        let mismatch = reference::compare("max", &result.committed).unwrap_err();
        assert!(mismatch.contains("differs"), "{mismatch}");
        assert_eq!(
            host.coordinator().backend().inner.stats().layers,
            if fault == Fault::SkipLayer { 3 } else { 4 }
        );
        clean(&host);
    }
}

#[test]
fn repeated_requests_release_reservations_and_own_output_after_finish() {
    let mut state = GenerationState::default();
    state.push_token(0).unwrap();
    let mut host = StepCoordinator::new(
        fixture_identity(),
        memory(),
        state,
        TinyMoeCpuBackend::default(),
    )
    .unwrap();
    let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
    let mut first = None;
    for position in 1..=64 {
        let token = *host.state().tokens().last().unwrap();
        let inputs = fixture.inputs(token).unwrap();
        let result = host
            .execute(
                &fixture_request(position),
                &inputs,
                &inputs,
                &CancellationToken::new(),
                |_| Ok(()),
            )
            .unwrap();
        if position == 1 {
            first = Some(result.committed.clone());
        }
        assert_eq!(host.state().position(), position + 1);
        assert_eq!(host.active_reservations(), 0);
        assert_eq!(host.active_reservation_bytes(), 0);
        assert!(!host.backend().has_staged_resources());
    }
    assert_eq!(fixture.reads(), 64 * 11);
    assert_eq!(host.backend().stats().layers, 128);
    assert!(host.peak_reservation_bytes() < 100_000);
    reference::compare("max", &first.unwrap()).unwrap();
}

#[test]
fn malformed_token_payload_and_trace_encoding_are_rejected() {
    let mut s = source(FIXTURE_WEIGHTS);
    s.token = 8;
    refused(
        &mut driver(TinyMoeCpuBackend::default(), 0, 8, None),
        &fixture_request(1),
        &s,
        "tiny_token_range",
        11,
    );
    assert_eq!(
        RoutedTrace::decode(&[]).unwrap_err().code(),
        "tiny_trace_encoding"
    );
    let mut encoded = RoutedTrace::default().encode().unwrap();
    encoded[0] = 0;
    assert_eq!(
        RoutedTrace::decode(&encoded).unwrap_err().code(),
        "tiny_trace_encoding"
    );
}

#[test]
fn driver_configuration_and_executor_working_overflow_refuse_before_io() {
    for (seed, vocabulary, max, eos) in [
        (8, 8, 1, None),
        (0, 0, 1, None),
        (0, 8, 0, None),
        (0, 8, 9, None),
        (0, 8, 1, Some(8)),
    ] {
        assert!(HostGeneration::new(
            fixture_identity(),
            memory(),
            TinyMoeCpuBackend::default(),
            seed,
            vocabulary,
            max,
            eos
        )
        .is_err());
    }
    struct Overflow;
    impl LayerExecutor for Overflow {
        fn execute_layer(
            &mut self,
            _: LayerRequest,
            _: &CancellationToken,
        ) -> Result<RuntimeBuffer, ContractError> {
            panic!("must refuse before execute")
        }
    }
    impl HostLayerExecutor for Overflow {
        fn working_bytes(&self) -> u64 {
            u64::MAX
        }
        fn stage(
            &mut self,
            _: &StepRequest,
            _: &[LoadedTensor],
            _: &mut [u8],
            _: &CancellationToken,
        ) -> Result<(), ContractError> {
            panic!("must refuse before stage")
        }
        fn take_output(&mut self, _: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
            panic!("must refuse before output")
        }
        fn finish(&mut self) -> Result<(), ContractError> {
            panic!("must refuse before cleanup")
        }
    }
    let fixture = TinyFixture::new(FIXTURE_WEIGHTS).unwrap();
    let mut host = driver(Overflow, 0, 8, None);
    assert_eq!(
        advance_fixture(&mut host, &fixture, &CancellationToken::new(), |_| panic!(
            "must refuse before delivery"
        ))
        .unwrap_err()
        .error
        .code(),
        "step_size_overflow"
    );
    assert_eq!(fixture.reads(), 0);
    assert!(host.generated_tokens().is_empty());
    clean(&host);
}
