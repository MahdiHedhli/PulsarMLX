//! A real, fixed-geometry CPU routed adapter. Tiny weights are eagerly resident;
//! this exercises selected computation, not expert paging or real model admission.
use crate::host_generation::HostGeneration;
use crate::step::{CommittedStep, StepFailure, StepOutcome};
use crate::step::{HostLayerExecutor, HostTensorStore, LayerOutput, LoadedTensor, StepRequest};
use crate::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, LayerExecutor,
    LayerRequest, RoutingPlan, RuntimeBuffer, RuntimeTensor, TensorCatalog, TensorRange,
    TensorStore,
};
use std::cell::Cell;

pub const FIXTURE_BYTES: usize = 3840;
pub const TRACE_BYTES: usize = 1016;
pub const CPU_WORKING_BYTES: u64 = 64 * 1024;
pub const FIXTURE_SHA256: &str = "cb25d125e2878086f5fd0edf6822979c76789d652ad35b1754104071736c9251";
pub const FIXTURE_WEIGHTS: &[u8; FIXTURE_BYTES] =
    include_bytes!("../fixtures/routed_cpu_v1/weights.bin");

pub fn fixture_identity() -> CheckpointIdentity {
    CheckpointIdentity::try_new(FIXTURE_SHA256, "routed-cpu-v1").expect("constant fixture identity")
}

fn descriptor(index: usize) -> RuntimeTensor {
    let (name, offset, shape, bytes) = match index {
        0 => ("embedding".to_owned(), 0, vec![8, 4], 256),
        9 => ("head".to_owned(), 3584, vec![8, 4], 256),
        10 => ("input_token".to_owned(), 3840, vec![1], 4),
        _ => {
            let layer = (index - 1) / 4;
            let part = (index - 1) % 4;
            let (kind, relative, shape, bytes) = match part {
                0 => ("router", 0, vec![4, 4], 128),
                1 => ("gate", 128, vec![4, 4, 4], 512),
                2 => ("up", 640, vec![4, 4, 4], 512),
                _ => ("down", 1152, vec![4, 4, 4], 512),
            };
            (
                format!("l{layer}.{kind}"),
                256 + layer as u64 * 1664 + relative,
                shape,
                bytes,
            )
        }
    };
    RuntimeTensor {
        name,
        shard: "routed-fixture-v1".into(),
        range: TensorRange {
            offset,
            length: bytes,
        },
        shape,
        quantization: if index == 10 { "u32-le" } else { "f64-le" }.into(),
    }
}

pub fn fixture_request(position: u64) -> StepRequest {
    StepRequest {
        id: format!("routed-step-{position}"),
        checkpoint: fixture_identity(),
        expected_position: position,
        inputs: (0..11).map(descriptor).collect(),
        layers: vec![0, 1],
        scratch_bytes: 0,
        output_bytes: TRACE_BYTES as u64,
    }
}

/// Bind each new input to the authoritative committed token. A delivery retry
/// uses the retained request; its store is never read by the coordinator.
pub fn advance_fixture<
    B: HostLayerExecutor,
    D: FnMut(&CommittedStep) -> Result<(), ContractError>,
>(
    driver: &mut HostGeneration<B>,
    fixture: &TinyFixture<'_>,
    cancel: &CancellationToken,
    deliver: D,
) -> Result<StepOutcome, StepFailure> {
    let (request, token) = if let Some(pending) = driver.pending_request() {
        (pending.clone(), 0)
    } else {
        (
            fixture_request(driver.coordinator().state().position()),
            driver.next_input_token()?,
        )
    };
    let input = fixture.inputs(token)?;
    driver.advance(&request, &input, &input, cancel, deliver)
}

/// Caller-owned immutable tiny fixture bytes. No checkpoint or file access.
pub struct TinyFixture<'a> {
    bytes: &'a [u8],
    reads: Cell<u64>,
}
impl<'a> TinyFixture<'a> {
    pub fn new(bytes: &'a [u8]) -> Result<Self, ContractError> {
        if bytes.len() != FIXTURE_BYTES {
            return Err(err("tiny_fixture_size"));
        }
        Ok(Self {
            bytes,
            reads: Cell::new(0),
        })
    }
    pub fn reads(&self) -> u64 {
        self.reads.get()
    }
    pub fn inputs(&self, token: u32) -> Result<TinyInputs<'_, 'a>, ContractError> {
        if token >= 8 {
            return Err(err("tiny_token_range"));
        }
        Ok(TinyInputs {
            fixture: self,
            token,
        })
    }
}
pub struct TinyInputs<'a, 'b> {
    fixture: &'a TinyFixture<'b>,
    token: u32,
}
impl TensorCatalog for TinyInputs<'_, '_> {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok((0..11).map(descriptor).find(|t| t.name == name))
    }
}
impl HostTensorStore for TinyInputs<'_, '_> {
    fn validate_range(&self, tensor: &RuntimeTensor) -> Result<(), ContractError> {
        let expected = self
            .tensor(&tensor.name)?
            .ok_or_else(|| err("tiny_descriptor"))?;
        if tensor != &expected || tensor.range.end()? > FIXTURE_BYTES as u64 + 4 {
            return Err(err("tiny_descriptor"));
        }
        Ok(())
    }
}
impl TensorStore for TinyInputs<'_, '_> {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        destination: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancel.check()?;
        self.validate_range(tensor)?;
        if destination.len() as u64 != tensor.range.length {
            return Err(err("tiny_destination"));
        }
        let count = self
            .fixture
            .reads
            .get()
            .checked_add(1)
            .ok_or_else(|| err("tiny_counter_overflow"))?;
        self.fixture.reads.set(count);
        if tensor.name == "input_token" {
            destination.copy_from_slice(&self.token.to_le_bytes());
        } else {
            let start = tensor.range.offset as usize;
            destination.copy_from_slice(&self.fixture.bytes[start..start + destination.len()]);
        }
        Ok(destination.len())
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct LayerTrace {
    pub input: [f64; 4],
    pub scores: [f64; 4],
    pub selected: [u32; 2],
    pub weights: [f64; 2],
    pub gate: [[f64; 4]; 2],
    pub up: [[f64; 4]; 2],
    pub silu: [[f64; 4]; 2],
    pub product: [[f64; 4]; 2],
    pub down: [[f64; 4]; 2],
    pub combined: [f64; 4],
    pub residual: [f64; 4],
}
#[derive(Debug, Clone, Default, PartialEq)]
pub struct RoutedTrace {
    pub input_token: u32,
    pub layers: [LayerTrace; 2],
    pub logits: [f64; 8],
}

impl RoutedTrace {
    fn encode(&self) -> Result<Vec<u8>, ContractError> {
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(TRACE_BYTES)
            .map_err(|_| err("tiny_output_allocation"))?;
        bytes.extend_from_slice(b"RCPU");
        bytes.extend_from_slice(&self.input_token.to_le_bytes());
        for layer in &self.layers {
            for x in layer.input.iter().chain(&layer.scores) {
                bytes.extend_from_slice(&x.to_le_bytes());
            }
            for id in layer.selected {
                bytes.extend_from_slice(&id.to_le_bytes());
            }
            for x in layer
                .weights
                .iter()
                .chain(layer.gate.iter().flatten())
                .chain(layer.up.iter().flatten())
                .chain(layer.silu.iter().flatten())
                .chain(layer.product.iter().flatten())
                .chain(layer.down.iter().flatten())
                .chain(&layer.combined)
                .chain(&layer.residual)
            {
                bytes.extend_from_slice(&x.to_le_bytes());
            }
        }
        for x in self.logits {
            bytes.extend_from_slice(&x.to_le_bytes());
        }
        debug_assert_eq!(bytes.len(), TRACE_BYTES);
        Ok(bytes)
    }
    pub fn decode(bytes: &[u8]) -> Result<Self, ContractError> {
        if bytes.len() != TRACE_BYTES || &bytes[..4] != b"RCPU" {
            return Err(err("tiny_trace_encoding"));
        }
        let mut offset = 4;
        fn word(bytes: &[u8], offset: &mut usize) -> u32 {
            let x = u32::from_le_bytes(
                bytes[*offset..*offset + 4]
                    .try_into()
                    .expect("bounded trace"),
            );
            *offset += 4;
            x
        }
        fn scalar(bytes: &[u8], offset: &mut usize) -> Result<f64, ContractError> {
            let x = f64::from_le_bytes(
                bytes[*offset..*offset + 8]
                    .try_into()
                    .expect("bounded trace"),
            );
            *offset += 8;
            finite(x)
        }
        let input_token = word(bytes, &mut offset);
        if input_token >= 8 {
            return Err(err("tiny_trace_token"));
        }
        let mut result = Self {
            input_token,
            ..Self::default()
        };
        for layer in &mut result.layers {
            for x in layer.input.iter_mut().chain(&mut layer.scores) {
                *x = scalar(bytes, &mut offset)?;
            }
            for id in &mut layer.selected {
                *id = word(bytes, &mut offset);
                if *id >= 4 {
                    return Err(err("tiny_trace_expert"));
                }
            }
            for x in layer
                .weights
                .iter_mut()
                .chain(layer.gate.iter_mut().flatten())
                .chain(layer.up.iter_mut().flatten())
                .chain(layer.silu.iter_mut().flatten())
                .chain(layer.product.iter_mut().flatten())
                .chain(layer.down.iter_mut().flatten())
                .chain(&mut layer.combined)
                .chain(&mut layer.residual)
            {
                *x = scalar(bytes, &mut offset)?;
            }
        }
        for x in &mut result.logits {
            *x = scalar(bytes, &mut offset)?;
        }
        debug_assert_eq!(offset, TRACE_BYTES);
        Ok(result)
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct CpuStats {
    pub stages: u64,
    pub layers: u64,
    pub routes: u64,
    pub experts: u64,
}
struct Proposal {
    id: String,
    position: u64,
    weights: [f64; 480],
    x: [f64; 4],
    trace: RoutedTrace,
    next_layer: u32,
    buffer: RuntimeBuffer,
    cancellation: CancellationToken,
}
#[derive(Default)]
pub struct TinyMoeCpuBackend {
    proposal: Option<Proposal>,
    stats: CpuStats,
    next_slot: u64,
}
impl TinyMoeCpuBackend {
    pub fn stats(&self) -> CpuStats {
        self.stats
    }
    pub fn has_staged_resources(&self) -> bool {
        self.proposal.is_some()
    }
}

impl HostLayerExecutor for TinyMoeCpuBackend {
    fn working_bytes(&self) -> u64 {
        CPU_WORKING_BYTES
    }
    fn stage(
        &mut self,
        request: &StepRequest,
        inputs: &[LoadedTensor],
        _scratch: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<(), ContractError> {
        cancel.check()?;
        if self.proposal.is_some()
            || request.layers != [0, 1]
            || request.output_bytes != TRACE_BYTES as u64
            || inputs.len() != 11
        {
            return Err(err("tiny_stage_shape"));
        }
        let mut weights = [0.0; 480];
        let mut cursor = 0;
        let mut token = 0;
        for (i, input) in inputs.iter().enumerate() {
            if input.descriptor != descriptor(i)
                || input.bytes.len() as u64 != input.descriptor.range.length
            {
                return Err(err("tiny_payload_descriptor"));
            }
            if i == 10 {
                token =
                    u32::from_le_bytes(input.bytes[..4].try_into().expect("validated token bytes"));
            } else {
                for chunk in input.bytes.chunks_exact(8) {
                    cancel.check()?;
                    weights[cursor] = finite(f64::from_le_bytes(
                        chunk.try_into().expect("validated f64 encoding"),
                    ))?;
                    cursor += 1;
                }
            }
        }
        if token >= 8 || cursor != 480 {
            return Err(err("tiny_token_range"));
        }
        let x = weights[token as usize * 4..token as usize * 4 + 4]
            .try_into()
            .expect("validated embedding");
        self.stats.stages = self
            .stats
            .stages
            .checked_add(1)
            .ok_or_else(|| err("tiny_counter_overflow"))?;
        self.proposal = Some(Proposal {
            id: request.id.clone(),
            position: request.expected_position,
            weights,
            x,
            trace: RoutedTrace {
                input_token: token,
                ..RoutedTrace::default()
            },
            next_layer: 0,
            buffer: RuntimeBuffer {
                slot_id: 0,
                byte_length: TRACE_BYTES as u64,
            },
            cancellation: cancel.clone(),
        });
        Ok(())
    }
    fn take_output(&mut self, buffer: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        let p = self
            .proposal
            .as_mut()
            .ok_or_else(|| err("tiny_not_staged"))?;
        if p.next_layer != 2 || p.buffer != buffer {
            return Err(err("tiny_output_order"));
        }
        p.trace.logits = project::<8>(&p.weights[448..480], &p.x, &p.cancellation)?;
        let mut token = 0;
        for i in 1..8 {
            if p.trace.logits[i] > p.trace.logits[token] {
                token = i;
            }
        }
        Ok(LayerOutput {
            step_id: p.id.clone(),
            request: LayerRequest {
                layer: 1,
                generation_position: p.position,
            },
            buffer,
            token: token as u32,
            bytes: p.trace.encode()?,
        })
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.proposal = None;
        Ok(())
    }
}
impl LayerExecutor for TinyMoeCpuBackend {
    fn execute_layer(
        &mut self,
        request: LayerRequest,
        cancel: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        cancel.check()?;
        let p = self
            .proposal
            .as_mut()
            .ok_or_else(|| err("tiny_not_staged"))?;
        if request.layer != p.next_layer
            || request.layer >= 2
            || request.generation_position != p.position
        {
            return Err(err("tiny_layer_order"));
        }
        let stats = CpuStats {
            stages: self.stats.stages,
            layers: self
                .stats
                .layers
                .checked_add(1)
                .ok_or_else(|| err("tiny_counter_overflow"))?,
            routes: self
                .stats
                .routes
                .checked_add(1)
                .ok_or_else(|| err("tiny_counter_overflow"))?,
            experts: self
                .stats
                .experts
                .checked_add(2)
                .ok_or_else(|| err("tiny_counter_overflow"))?,
        };
        let mut trace = LayerTrace {
            input: p.x,
            ..LayerTrace::default()
        };
        let start = 32 + request.layer as usize * 208;
        trace.scores = project::<4>(&p.weights[start..start + 16], &p.x, cancel)?;
        for a in trace.scores {
            for b in trace.scores {
                finite(a - b)?;
            }
        }
        let plan = RoutingPlan::try_softmax(&trace.scores, 1, 4, 2)?;
        for slot in 0..2 {
            cancel.check()?;
            let expert = plan.selected_expert_ids()[slot] as usize;
            trace.selected[slot] = expert as u32;
            trace.weights[slot] = plan.normalized_weights()[slot];
            let gate = start + 16 + expert * 16;
            let up = start + 80 + expert * 16;
            let down = start + 144 + expert * 16;
            trace.gate[slot] = project::<4>(&p.weights[gate..gate + 16], &p.x, cancel)?;
            trace.up[slot] = project::<4>(&p.weights[up..up + 16], &p.x, cancel)?;
            for i in 0..4 {
                cancel.check()?;
                let z = trace.gate[slot][i];
                let exponential = finite((-z).exp())?;
                trace.silu[slot][i] = finite(z / finite(1.0 + exponential)?)?;
                trace.product[slot][i] = finite(trace.silu[slot][i] * trace.up[slot][i])?;
            }
            trace.down[slot] =
                project::<4>(&p.weights[down..down + 16], &trace.product[slot], cancel)?;
        }
        let selected: [f64; 8] = std::array::from_fn(|i| trace.down[i / 4][i % 4]);
        trace.combined = plan
            .aggregate_selected_outputs(&selected, 4)?
            .try_into()
            .map_err(|_| err("tiny_mix_shape"))?;
        for i in 0..4 {
            trace.combined[i] = finite(trace.combined[i])?;
            trace.residual[i] = finite(p.x[i] + trace.combined[i])?;
        }
        let slot = self
            .next_slot
            .checked_add(1)
            .ok_or_else(|| err("tiny_counter_overflow"))?;
        p.x = trace.residual;
        p.trace.layers[request.layer as usize] = trace;
        p.next_layer += 1;
        p.buffer = RuntimeBuffer {
            slot_id: slot,
            byte_length: TRACE_BYTES as u64,
        };
        self.stats = stats;
        self.next_slot = slot;
        Ok(p.buffer)
    }
}
fn project<const N: usize>(
    matrix: &[f64],
    input: &[f64; 4],
    cancel: &CancellationToken,
) -> Result<[f64; N], ContractError> {
    let mut out = [0.0; N];
    for row in 0..N {
        cancel.check()?;
        for col in 0..4 {
            out[row] = finite(out[row] + finite(matrix[row * 4 + col] * input[col])?)?;
        }
    }
    Ok(out)
}
fn finite(value: f64) -> Result<f64, ContractError> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(err("tiny_non_finite"))
    }
}
fn err(code: &'static str) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidTensor,
        code,
        "tiny routed CPU computation refused",
    )
}

#[cfg(test)]
#[path = "routed_cpu_tests.rs"]
mod tests;
