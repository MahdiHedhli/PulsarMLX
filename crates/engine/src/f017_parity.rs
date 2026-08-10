use backend::{MemoryBudget, RoutingPlan};
use quant::decode_q8_0_matrix;
use sha2::{Digest, Sha256};
use std::fmt;
use std::time::Duration;
use stream::{RuntimeTelemetry, TelemetryBucket, TelemetrySnapshot, ValidationClassification};

pub const PROJECTION_SOURCE_COMMIT: &str = "60145f8f18531e169e9fbfb676d1754efbfc4873";
pub const PROJECTION_FIXTURE_VERSION: &str = "glm52-runtime-projection-q8-0-v1";
pub const PROJECTION_TENSOR_NAME: &str = "synthetic.blk.0.attn_q_b.weight";
pub const PROJECTION_TENSOR_SHARD: &str = "synthetic-trunk-00001";
pub const PROJECTION_ROWS: usize = 2;
pub const PROJECTION_COLUMNS: usize = 32;
pub const PROJECTION_QUANTIZATION: &str = "Q8_0";
pub const PROJECTION_DTYPE: &str = "f32";
pub const ROUTER_FIXTURE_VERSION: &str = "glm52-runtime-router-v1";
pub const ROUTER_TENSOR_NAME: &str = "synthetic.blk.0.ffn_gate_inp.weight";
pub const ROUTER_TENSOR_SHARD: &str = "synthetic-trunk-00001";
pub const ROUTER_TOKEN_COUNT: u64 = 2;
pub const ROUTER_EXPERT_COUNT: u64 = 4;
pub const ROUTER_TOP_K: u64 = 2;
const PROJECTION_ENCODED_SHA256: &str =
    "f49f515968e7229c1939529f1569b3ad2e61f43373a5f4ba5b2a862388b654c1";
const PROJECTION_INPUT_SHA256: &str =
    "dab8e4da31ccc32b7c3bd0b5e405347b1593429bad47b767327519eab6fbc588";
const PROJECTION_REFERENCE_OUTPUT_SHA256: &str =
    "f05588d152f98331a25df1d2efe2ad97fcc66e8e047ad567edf9c5c0bd182bfc";
const ROUTER_SCORES_SHA256: &str =
    "bde55fc1851c0d669532ee9faa681100c971dea54db974db57d804737dec4ba5";
const ROUTER_IDS_SHA256: &str = "dfe9b3c36426d5beb760e4b14e6135cdc4a2a1d2bf9c76536ed32cbc308fedd0";
const ROUTER_WEIGHTS_SHA256: &str =
    "99595b232fc7412fbef687c1ef0aa742753f3a2d8116225d10f6340ce0276435";
const ROUTER_OUTPUT_SHA256: &str =
    "b50abdcbc770e9d10ab438dbb6137a6ef9046fc753f9587b85cb4cdba963a55b";
pub const EXPERT_FIXTURE_VERSION: &str = "glm52-runtime-expert-q8-0-v1";
pub const EXPERT_GATE_TENSOR_NAME: &str = "synthetic.blk.0.ffn_gate_exps.weight";
pub const EXPERT_UP_TENSOR_NAME: &str = "synthetic.blk.0.ffn_up_exps.weight";
pub const EXPERT_DOWN_TENSOR_NAME: &str = "synthetic.blk.0.ffn_down_exps.weight";
pub const EXPERT_TENSOR_SHARD: &str = "synthetic-trunk-00001";
pub const EXPERT_ROWS: usize = 32;
pub const EXPERT_COLUMNS: usize = 32;
const EXPERT_GATE_SHA256: &str = "ebeadb4a76f33fd37d3c3aa358f0684d255798c911e6a73557aa38c2608216d3";
const EXPERT_UP_SHA256: &str = "d21f5321c74829bd43c697064d290c9d7d84b3739186a6420d57c4f05be8613a";
const EXPERT_DOWN_SHA256: &str = "2d0eb3dc83f2500e248c26c8413d1182c4dc6a3ca1cfcdf366763176fcf682b4";
const EXPERT_INPUT_SHA256: &str =
    "dab8e4da31ccc32b7c3bd0b5e405347b1593429bad47b767327519eab6fbc588";
const EXPERT_REFERENCE_OUTPUT_SHA256: &str =
    "7f0358e45119a98e862eda497e4f443a65d6447240afcbb3e598a7160369d5f6";
const M2_MAX_TOTAL_BYTES: u64 = 64 * 1024 * 1024 * 1024;
const M2_MAX_SAFETY_RESERVE_BYTES: u64 = 24 * 1024 * 1024 * 1024;
const M2_MAX_REQUIRED_MARGIN_BYTES: u64 = 4 * 1024 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProjectionDispatch {
    ExplicitReference,
    QualifiedDirect,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProjectionParityError {
    InvalidFixture(&'static str),
    HashMismatch(&'static str),
    MemoryRejected,
    UnexpectedDispatch {
        expected: ProjectionDispatch,
        actual: ProjectionDispatch,
    },
    Decoder(String),
    Telemetry(String),
}

impl fmt::Display for ProjectionParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidFixture(field) => write!(formatter, "invalid projection fixture: {field}"),
            Self::HashMismatch(field) => {
                write!(formatter, "projection fixture hash mismatch: {field}")
            }
            Self::MemoryRejected => {
                formatter.write_str("projection fixture rejected by memory budget")
            }
            Self::UnexpectedDispatch { expected, actual } => write!(
                formatter,
                "unexpected projection dispatch: expected {expected:?}, got {actual:?}"
            ),
            Self::Decoder(error) => write!(formatter, "projection decoder failed: {error}"),
            Self::Telemetry(error) => write!(formatter, "projection telemetry failed: {error}"),
        }
    }
}

impl std::error::Error for ProjectionParityError {}

#[derive(Debug, Clone, PartialEq)]
pub struct ProjectionFixture {
    pub source_commit: &'static str,
    pub fixture_version: &'static str,
    pub tensor_name: &'static str,
    pub tensor_shard: &'static str,
    pub dimensions: [usize; 2],
    pub quantization: &'static str,
    pub dtype: &'static str,
    pub encoded: Vec<u8>,
    pub activation: Vec<f32>,
}

impl ProjectionFixture {
    pub fn synthetic_q8_0() -> Self {
        let mut encoded = Vec::with_capacity(PROJECTION_ROWS * 34);
        for row in 0..PROJECTION_ROWS {
            encoded.extend_from_slice(&0x3c00_u16.to_le_bytes());
            for index in 0..PROJECTION_COLUMNS {
                let value = index + 1;
                let quant = if row == 1 && index % 2 == 0 {
                    -(value as i8)
                } else {
                    value as i8
                };
                encoded.push(quant as u8);
            }
        }
        let activation = (0..PROJECTION_COLUMNS)
            .map(|index| 1.0 + (index % 8) as f32 * 0.125)
            .collect();
        Self {
            source_commit: PROJECTION_SOURCE_COMMIT,
            fixture_version: PROJECTION_FIXTURE_VERSION,
            tensor_name: PROJECTION_TENSOR_NAME,
            tensor_shard: PROJECTION_TENSOR_SHARD,
            dimensions: [PROJECTION_ROWS, PROJECTION_COLUMNS],
            quantization: PROJECTION_QUANTIZATION,
            dtype: PROJECTION_DTYPE,
            encoded,
            activation,
        }
    }

    pub fn input_sha256(&self) -> String {
        hash_f32(&self.activation)
    }

    pub fn encoded_sha256(&self) -> String {
        hash_bytes(&self.encoded)
    }

    pub fn validate(&self) -> Result<(), ProjectionParityError> {
        if self.source_commit != PROJECTION_SOURCE_COMMIT {
            return Err(ProjectionParityError::InvalidFixture("source_commit"));
        }
        if self.fixture_version != PROJECTION_FIXTURE_VERSION {
            return Err(ProjectionParityError::InvalidFixture("fixture_version"));
        }
        if self.tensor_name != PROJECTION_TENSOR_NAME
            || self.tensor_shard != PROJECTION_TENSOR_SHARD
            || self.dimensions != [PROJECTION_ROWS, PROJECTION_COLUMNS]
            || self.quantization != PROJECTION_QUANTIZATION
            || self.dtype != PROJECTION_DTYPE
        {
            return Err(ProjectionParityError::InvalidFixture("tensor identity"));
        }
        if self.activation.len() != PROJECTION_COLUMNS {
            return Err(ProjectionParityError::InvalidFixture("activation length"));
        }
        if self.encoded_sha256() != PROJECTION_ENCODED_SHA256 {
            return Err(ProjectionParityError::HashMismatch("encoded"));
        }
        if self.input_sha256() != PROJECTION_INPUT_SHA256 {
            return Err(ProjectionParityError::HashMismatch("activation"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectionParityResult {
    pub classification: ValidationClassification,
    pub dispatch: ProjectionDispatch,
    pub memory_admitted: bool,
    pub telemetry: TelemetrySnapshot,
    pub reference_output_sha256: String,
}

pub fn run_projection_fixture(
    fixture: &ProjectionFixture,
    expected_dispatch: ProjectionDispatch,
) -> Result<ProjectionParityResult, ProjectionParityError> {
    fixture.validate()?;
    let memory = MemoryBudget::try_new(
        M2_MAX_TOTAL_BYTES,
        M2_MAX_SAFETY_RESERVE_BYTES,
        M2_MAX_TOTAL_BYTES - M2_MAX_SAFETY_RESERVE_BYTES - M2_MAX_REQUIRED_MARGIN_BYTES,
    )
    .map_err(|_| ProjectionParityError::MemoryRejected)?;
    let requested_bytes = fixture.encoded.len() as u64
        + (fixture.activation.len() * std::mem::size_of::<f32>()) as u64
        + (PROJECTION_ROWS * std::mem::size_of::<f32>()) as u64;
    if !memory.admits(requested_bytes) {
        return Err(ProjectionParityError::MemoryRejected);
    }
    let actual_dispatch = ProjectionDispatch::ExplicitReference;
    if actual_dispatch != expected_dispatch {
        return Err(ProjectionParityError::UnexpectedDispatch {
            expected: expected_dispatch,
            actual: actual_dispatch,
        });
    }

    let mut telemetry = RuntimeTelemetry::new();
    telemetry
        .record_storage_read(Duration::from_nanos(1), 1, fixture.encoded.len() as u64)
        .map_err(|error| ProjectionParityError::Telemetry(format!("{error:?}")))?;
    let mut decoded = vec![0.0_f32; PROJECTION_ROWS * PROJECTION_COLUMNS];
    decode_q8_0_matrix(
        &fixture.encoded,
        PROJECTION_ROWS,
        PROJECTION_COLUMNS,
        &mut decoded,
    )
    .map_err(|error| ProjectionParityError::Decoder(error.to_string()))?;
    telemetry
        .record_stage(TelemetryBucket::Decode, Duration::from_nanos(1), 1)
        .map_err(|error| ProjectionParityError::Telemetry(format!("{error:?}")))?;

    let reference_decoded = reference_decode(&fixture.encoded);
    if decoded
        .iter()
        .zip(reference_decoded.iter())
        .any(|(actual, expected)| actual.to_bits() != expected.to_bits())
    {
        return Err(ProjectionParityError::InvalidFixture("decode parity"));
    }
    telemetry
        .record_stage(
            TelemetryBucket::BufferMaterialization,
            Duration::from_nanos(1),
            1,
        )
        .map_err(|error| ProjectionParityError::Telemetry(format!("{error:?}")))?;
    let actual_output = project(&decoded, &fixture.activation);
    let reference_output = project(&reference_decoded, &fixture.activation);
    if actual_output
        .iter()
        .zip(reference_output.iter())
        .any(|(actual, expected)| actual.to_bits() != expected.to_bits())
    {
        return Err(ProjectionParityError::InvalidFixture("projection parity"));
    }
    telemetry
        .record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 1)
        .map_err(|error| ProjectionParityError::Telemetry(format!("{error:?}")))?;
    let reference_output_sha256 = hash_f32(&reference_output);
    if reference_output_sha256 != PROJECTION_REFERENCE_OUTPUT_SHA256 {
        return Err(ProjectionParityError::HashMismatch("reference output"));
    }
    Ok(ProjectionParityResult {
        classification: ValidationClassification::GoldenIdentical,
        dispatch: actual_dispatch,
        memory_admitted: true,
        telemetry: telemetry
            .snapshot()
            .map_err(|error| ProjectionParityError::Telemetry(format!("{error:?}")))?,
        reference_output_sha256,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct RouterFixture {
    pub source_commit: &'static str,
    pub fixture_version: &'static str,
    pub tensor_name: &'static str,
    pub tensor_shard: &'static str,
    pub dimensions: [u64; 2],
    pub quantization: &'static str,
    pub dtype: &'static str,
    pub scores: Vec<f64>,
    pub selected_outputs: Vec<f64>,
}

impl RouterFixture {
    pub fn synthetic() -> Self {
        Self {
            source_commit: PROJECTION_SOURCE_COMMIT,
            fixture_version: ROUTER_FIXTURE_VERSION,
            tensor_name: ROUTER_TENSOR_NAME,
            tensor_shard: ROUTER_TENSOR_SHARD,
            dimensions: [ROUTER_TOKEN_COUNT, ROUTER_EXPERT_COUNT],
            quantization: "F32",
            dtype: "f64",
            scores: vec![1.0, 3.0, 3.0, -1.0, 2.0, 3.0, 1.0, 4.0],
            selected_outputs: vec![3.0, 2.0, 1.0, 2.0, 5.75, 3.5, -0.5, 5.5],
        }
    }

    pub fn validate(&self) -> Result<(), RouterParityError> {
        if self.source_commit != PROJECTION_SOURCE_COMMIT {
            return Err(RouterParityError::InvalidFixture("source_commit"));
        }
        if self.fixture_version != ROUTER_FIXTURE_VERSION {
            return Err(RouterParityError::InvalidFixture("fixture_version"));
        }
        if self.tensor_name != ROUTER_TENSOR_NAME
            || self.tensor_shard != ROUTER_TENSOR_SHARD
            || self.dimensions != [ROUTER_TOKEN_COUNT, ROUTER_EXPERT_COUNT]
            || self.quantization != "F32"
            || self.dtype != "f64"
        {
            return Err(RouterParityError::InvalidFixture("tensor identity"));
        }
        if self.scores.len() != (ROUTER_TOKEN_COUNT * ROUTER_EXPERT_COUNT) as usize {
            return Err(RouterParityError::InvalidFixture("score cardinality"));
        }
        if self.selected_outputs.len() != (ROUTER_TOKEN_COUNT * ROUTER_TOP_K * 2) as usize {
            return Err(RouterParityError::InvalidFixture(
                "selected output cardinality",
            ));
        }
        if hash_f64(&self.scores) != ROUTER_SCORES_SHA256 {
            return Err(RouterParityError::HashMismatch("scores"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RouterParityError {
    InvalidFixture(&'static str),
    HashMismatch(&'static str),
    MemoryRejected,
    UnexpectedDispatch {
        expected: ProjectionDispatch,
        actual: ProjectionDispatch,
    },
    Routing(String),
    Telemetry(String),
}

impl fmt::Display for RouterParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidFixture(field) => write!(formatter, "invalid router fixture: {field}"),
            Self::HashMismatch(field) => write!(formatter, "router fixture hash mismatch: {field}"),
            Self::MemoryRejected => formatter.write_str("router fixture rejected by memory budget"),
            Self::UnexpectedDispatch { expected, actual } => write!(
                formatter,
                "unexpected router dispatch: expected {expected:?}, got {actual:?}"
            ),
            Self::Routing(error) => write!(formatter, "router contract failed: {error}"),
            Self::Telemetry(error) => write!(formatter, "router telemetry failed: {error}"),
        }
    }
}

impl std::error::Error for RouterParityError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterParityResult {
    pub classification: ValidationClassification,
    pub dispatch: ProjectionDispatch,
    pub memory_admitted: bool,
    pub telemetry: TelemetrySnapshot,
    pub selected_ids_sha256: String,
    pub weights_sha256: String,
    pub output_sha256: String,
}

pub fn run_router_fixture(
    fixture: &RouterFixture,
    expected_dispatch: ProjectionDispatch,
) -> Result<RouterParityResult, RouterParityError> {
    fixture.validate()?;
    let memory = MemoryBudget::try_new(
        M2_MAX_TOTAL_BYTES,
        M2_MAX_SAFETY_RESERVE_BYTES,
        M2_MAX_TOTAL_BYTES - M2_MAX_SAFETY_RESERVE_BYTES - M2_MAX_REQUIRED_MARGIN_BYTES,
    )
    .map_err(|_| RouterParityError::MemoryRejected)?;
    let requested_bytes = (fixture.scores.len() * std::mem::size_of::<f64>()) as u64
        + (fixture.selected_outputs.len() * std::mem::size_of::<f64>()) as u64;
    if !memory.admits(requested_bytes) {
        return Err(RouterParityError::MemoryRejected);
    }
    let actual_dispatch = ProjectionDispatch::ExplicitReference;
    if actual_dispatch != expected_dispatch {
        return Err(RouterParityError::UnexpectedDispatch {
            expected: expected_dispatch,
            actual: actual_dispatch,
        });
    }

    let mut telemetry = RuntimeTelemetry::new();
    telemetry
        .record_storage_read(
            Duration::from_nanos(1),
            1,
            (fixture.scores.len() * std::mem::size_of::<f64>()) as u64,
        )
        .map_err(|error| RouterParityError::Telemetry(format!("{error:?}")))?;
    let plan = RoutingPlan::try_softmax(
        &fixture.scores,
        ROUTER_TOKEN_COUNT,
        ROUTER_EXPERT_COUNT,
        ROUTER_TOP_K,
    )
    .map_err(|error| RouterParityError::Routing(error.to_string()))?;
    let expected_ids = [1_u64, 2, 3, 1];
    if plan.selected_expert_ids() != expected_ids {
        return Err(RouterParityError::InvalidFixture("selected expert IDs"));
    }
    let ids_sha256 = hash_u64(plan.selected_expert_ids());
    if ids_sha256 != ROUTER_IDS_SHA256 {
        return Err(RouterParityError::HashMismatch("selected expert IDs"));
    }
    telemetry
        .record_stage(
            TelemetryBucket::BufferMaterialization,
            Duration::from_nanos(1),
            1,
        )
        .map_err(|error| RouterParityError::Telemetry(format!("{error:?}")))?;
    let expected_weights: [f64; 4] = [0.5, 0.5, 0.7310585786300049, 0.2689414213699952];
    if plan
        .normalized_weights()
        .iter()
        .zip(expected_weights.iter())
        .any(|(actual, expected)| (actual - expected).abs() > 1.0e-12)
    {
        return Err(RouterParityError::InvalidFixture("routing weights"));
    }
    let weights_sha256 = hash_f64(&expected_weights);
    if weights_sha256 != ROUTER_WEIGHTS_SHA256 {
        return Err(RouterParityError::HashMismatch("routing weights"));
    }
    let output = plan
        .aggregate_selected_outputs(&fixture.selected_outputs, 2)
        .map_err(|error| RouterParityError::Routing(error.to_string()))?;
    let expected_output: [f64; 4] = [2.0, 2.0, 4.06911611643753, 4.03788284273999];
    if output
        .iter()
        .zip(expected_output.iter())
        .any(|(actual, expected)| (actual - expected).abs() > 1.0e-12)
    {
        return Err(RouterParityError::InvalidFixture("aggregated output"));
    }
    let output_sha256 = hash_f64(&expected_output);
    if output_sha256 != ROUTER_OUTPUT_SHA256 {
        return Err(RouterParityError::HashMismatch("aggregated output"));
    }
    telemetry
        .record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 1)
        .map_err(|error| RouterParityError::Telemetry(format!("{error:?}")))?;
    Ok(RouterParityResult {
        classification: ValidationClassification::NumericallyQualifiedGreedyIdentical,
        dispatch: actual_dispatch,
        memory_admitted: true,
        telemetry: telemetry
            .snapshot()
            .map_err(|error| RouterParityError::Telemetry(format!("{error:?}")))?,
        selected_ids_sha256: ids_sha256,
        weights_sha256,
        output_sha256,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExpertFixture {
    pub source_commit: &'static str,
    pub fixture_version: &'static str,
    pub tensor_names: [&'static str; 3],
    pub tensor_shard: &'static str,
    pub dimensions: [usize; 2],
    pub quantization: &'static str,
    pub dtype: &'static str,
    pub gate_encoded: Vec<u8>,
    pub up_encoded: Vec<u8>,
    pub down_encoded: Vec<u8>,
    pub activation: Vec<f32>,
}

impl ExpertFixture {
    pub fn synthetic() -> Self {
        Self {
            source_commit: PROJECTION_SOURCE_COMMIT,
            fixture_version: EXPERT_FIXTURE_VERSION,
            tensor_names: [
                EXPERT_GATE_TENSOR_NAME,
                EXPERT_UP_TENSOR_NAME,
                EXPERT_DOWN_TENSOR_NAME,
            ],
            tensor_shard: EXPERT_TENSOR_SHARD,
            dimensions: [EXPERT_ROWS, EXPERT_COLUMNS],
            quantization: PROJECTION_QUANTIZATION,
            dtype: PROJECTION_DTYPE,
            gate_encoded: expert_matrix(0),
            up_encoded: expert_matrix(1),
            down_encoded: expert_matrix(2),
            activation: (0..EXPERT_COLUMNS)
                .map(|index| 1.0 + (index % 8) as f32 * 0.125)
                .collect(),
        }
    }

    pub fn validate(&self) -> Result<(), ExpertParityError> {
        if self.source_commit != PROJECTION_SOURCE_COMMIT {
            return Err(ExpertParityError::InvalidFixture("source_commit"));
        }
        if self.fixture_version != EXPERT_FIXTURE_VERSION {
            return Err(ExpertParityError::InvalidFixture("fixture_version"));
        }
        if self.tensor_names
            != [
                EXPERT_GATE_TENSOR_NAME,
                EXPERT_UP_TENSOR_NAME,
                EXPERT_DOWN_TENSOR_NAME,
            ]
            || self.tensor_shard != EXPERT_TENSOR_SHARD
            || self.dimensions != [EXPERT_ROWS, EXPERT_COLUMNS]
            || self.quantization != PROJECTION_QUANTIZATION
            || self.dtype != PROJECTION_DTYPE
        {
            return Err(ExpertParityError::InvalidFixture("tensor identity"));
        }
        let encoded_len = EXPERT_ROWS * 34;
        if self.gate_encoded.len() != encoded_len
            || self.up_encoded.len() != encoded_len
            || self.down_encoded.len() != encoded_len
            || self.activation.len() != EXPERT_COLUMNS
        {
            return Err(ExpertParityError::InvalidFixture("shape"));
        }
        if hash_bytes(&self.gate_encoded) != EXPERT_GATE_SHA256 {
            return Err(ExpertParityError::HashMismatch("gate bytes"));
        }
        if hash_bytes(&self.up_encoded) != EXPERT_UP_SHA256 {
            return Err(ExpertParityError::HashMismatch("up bytes"));
        }
        if hash_bytes(&self.down_encoded) != EXPERT_DOWN_SHA256 {
            return Err(ExpertParityError::HashMismatch("down bytes"));
        }
        if hash_f32(&self.activation) != EXPERT_INPUT_SHA256 {
            return Err(ExpertParityError::HashMismatch("activation"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExpertParityError {
    InvalidFixture(&'static str),
    HashMismatch(&'static str),
    MemoryRejected,
    UnexpectedDispatch {
        expected: ProjectionDispatch,
        actual: ProjectionDispatch,
    },
    Decoder(String),
    NumericalMismatch(&'static str),
    Telemetry(String),
}

impl fmt::Display for ExpertParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidFixture(field) => write!(formatter, "invalid expert fixture: {field}"),
            Self::HashMismatch(field) => write!(formatter, "expert fixture hash mismatch: {field}"),
            Self::MemoryRejected => formatter.write_str("expert fixture rejected by memory budget"),
            Self::UnexpectedDispatch { expected, actual } => write!(
                formatter,
                "unexpected expert dispatch: expected {expected:?}, got {actual:?}"
            ),
            Self::Decoder(error) => write!(formatter, "expert decoder failed: {error}"),
            Self::NumericalMismatch(stage) => {
                write!(formatter, "expert numerical mismatch: {stage}")
            }
            Self::Telemetry(error) => write!(formatter, "expert telemetry failed: {error}"),
        }
    }
}

impl std::error::Error for ExpertParityError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExpertParityResult {
    pub classification: ValidationClassification,
    pub dispatch: ProjectionDispatch,
    pub memory_admitted: bool,
    pub telemetry: TelemetrySnapshot,
    pub output_sha256: String,
}

pub fn run_expert_fixture(
    fixture: &ExpertFixture,
    expected_dispatch: ProjectionDispatch,
) -> Result<ExpertParityResult, ExpertParityError> {
    fixture.validate()?;
    let memory = MemoryBudget::try_new(
        M2_MAX_TOTAL_BYTES,
        M2_MAX_SAFETY_RESERVE_BYTES,
        M2_MAX_TOTAL_BYTES - M2_MAX_SAFETY_RESERVE_BYTES - M2_MAX_REQUIRED_MARGIN_BYTES,
    )
    .map_err(|_| ExpertParityError::MemoryRejected)?;
    let requested_bytes =
        (fixture.gate_encoded.len() + fixture.up_encoded.len() + fixture.down_encoded.len()) as u64
            + (EXPERT_ROWS * EXPERT_COLUMNS * std::mem::size_of::<f32>() * 3) as u64;
    if !memory.admits(requested_bytes) {
        return Err(ExpertParityError::MemoryRejected);
    }
    let actual_dispatch = ProjectionDispatch::ExplicitReference;
    if actual_dispatch != expected_dispatch {
        return Err(ExpertParityError::UnexpectedDispatch {
            expected: expected_dispatch,
            actual: actual_dispatch,
        });
    }

    let mut telemetry = RuntimeTelemetry::new();
    telemetry
        .record_storage_read(
            Duration::from_nanos(1),
            3,
            (fixture.gate_encoded.len() + fixture.up_encoded.len() + fixture.down_encoded.len())
                as u64,
        )
        .map_err(|error| ExpertParityError::Telemetry(format!("{error:?}")))?;

    let mut gate = vec![0.0_f32; EXPERT_ROWS * EXPERT_COLUMNS];
    let mut up = vec![0.0_f32; EXPERT_ROWS * EXPERT_COLUMNS];
    let mut down = vec![0.0_f32; EXPERT_ROWS * EXPERT_COLUMNS];
    for (encoded, decoded, name) in [
        (&fixture.gate_encoded, &mut gate, "gate"),
        (&fixture.up_encoded, &mut up, "up"),
        (&fixture.down_encoded, &mut down, "down"),
    ] {
        decode_q8_0_matrix(encoded, EXPERT_ROWS, EXPERT_COLUMNS, decoded)
            .map_err(|error| ExpertParityError::Decoder(format!("{name}: {error}")))?;
        telemetry
            .record_stage(TelemetryBucket::Decode, Duration::from_nanos(1), 1)
            .map_err(|error| ExpertParityError::Telemetry(format!("{error:?}")))?;
        telemetry
            .record_stage(
                TelemetryBucket::BufferMaterialization,
                Duration::from_nanos(1),
                1,
            )
            .map_err(|error| ExpertParityError::Telemetry(format!("{error:?}")))?;
    }

    let reference_gate = reference_decode_matrix(&fixture.gate_encoded);
    let reference_up = reference_decode_matrix(&fixture.up_encoded);
    let reference_down = reference_decode_matrix(&fixture.down_encoded);
    if gate != reference_gate || up != reference_up || down != reference_down {
        return Err(ExpertParityError::NumericalMismatch("matrix decode"));
    }

    let gate_output = matvec_f32(&gate, &fixture.activation);
    let up_output = matvec_f32(&up, &fixture.activation);
    let hidden = gate_output
        .iter()
        .zip(up_output.iter())
        .map(|(gate_value, up_value)| silu_f32(*gate_value) * up_value)
        .collect::<Vec<_>>();
    let output = matvec_f32(&down, &hidden);
    let reference_gate_output = reference_matvec(&reference_gate, &fixture.activation);
    let reference_up_output = reference_matvec(&reference_up, &fixture.activation);
    let reference_hidden = reference_gate_output
        .iter()
        .zip(reference_up_output.iter())
        .map(|(gate_value, up_value)| reference_silu(*gate_value) * up_value)
        .collect::<Vec<_>>();
    let reference_output = reference_matvec(&reference_down, &reference_hidden);
    if gate_output != reference_gate_output
        || up_output != reference_up_output
        || hidden != reference_hidden
        || output != reference_output
    {
        return Err(ExpertParityError::NumericalMismatch("expert execution"));
    }
    let output_sha256 = hash_f32(&reference_output);
    if output_sha256 != EXPERT_REFERENCE_OUTPUT_SHA256 {
        return Err(ExpertParityError::HashMismatch("reference output"));
    }
    telemetry
        .record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 4)
        .map_err(|error| ExpertParityError::Telemetry(format!("{error:?}")))?;
    Ok(ExpertParityResult {
        classification: ValidationClassification::GoldenIdentical,
        dispatch: actual_dispatch,
        memory_admitted: true,
        telemetry: telemetry
            .snapshot()
            .map_err(|error| ExpertParityError::Telemetry(format!("{error:?}")))?,
        output_sha256,
    })
}

fn expert_matrix(kind: u8) -> Vec<u8> {
    let mut encoded = Vec::with_capacity(EXPERT_ROWS * 34);
    for row in 0..EXPERT_ROWS {
        encoded.extend_from_slice(&0x3c00_u16.to_le_bytes());
        for column in 0..EXPERT_COLUMNS {
            let value = match kind {
                0 => ((row * 3 + column * 5) % 31 + 1) as isize,
                1 => ((row * 7 + column * 11) % 29 + 1) as isize,
                _ if row == column => 2_isize,
                _ => ((row * 13 + column * 3) % 17) as isize - 8,
            };
            encoded.push((value as i8) as u8);
        }
    }
    encoded
}

fn reference_decode_matrix(encoded: &[u8]) -> Vec<f32> {
    let mut decoded = Vec::with_capacity(EXPERT_ROWS * EXPERT_COLUMNS);
    for row in 0..EXPERT_ROWS {
        let start = row * 34;
        for column in 0..EXPERT_COLUMNS {
            decoded.push(encoded[start + 2 + column] as i8 as f32);
        }
    }
    decoded
}

fn matvec_f32(matrix: &[f32], vector: &[f32]) -> Vec<f32> {
    (0..EXPERT_ROWS)
        .map(|row| {
            (0..EXPERT_COLUMNS)
                .map(|column| matrix[row * EXPERT_COLUMNS + column] * vector[column])
                .fold(0.0_f32, |sum, value| sum + value)
        })
        .collect()
}

fn reference_matvec(matrix: &[f32], vector: &[f32]) -> Vec<f32> {
    let mut output = Vec::with_capacity(EXPERT_ROWS);
    for row in 0..EXPERT_ROWS {
        let mut sum = 0.0_f32;
        for column in 0..EXPERT_COLUMNS {
            sum += matrix[row * EXPERT_COLUMNS + column] * vector[column];
        }
        output.push(sum);
    }
    output
}

fn silu_f32(value: f32) -> f32 {
    value / (1.0_f32 + (-value).exp())
}

fn reference_silu(value: f32) -> f32 {
    let denominator = 1.0_f32 + (-value).exp();
    value / denominator
}

fn reference_decode(encoded: &[u8]) -> Vec<f32> {
    let mut decoded = Vec::with_capacity(PROJECTION_ROWS * PROJECTION_COLUMNS);
    for row in 0..PROJECTION_ROWS {
        let start = row * 34;
        for index in 0..PROJECTION_COLUMNS {
            decoded.push(encoded[start + 2 + index] as i8 as f32);
        }
    }
    decoded
}

fn project(matrix: &[f32], activation: &[f32]) -> Vec<f32> {
    (0..PROJECTION_ROWS)
        .map(|row| {
            (0..PROJECTION_COLUMNS)
                .map(|column| matrix[row * PROJECTION_COLUMNS + column] * activation[column])
                .fold(0.0_f32, |sum, value| sum + value)
        })
        .collect()
}

fn hash_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn hash_f32(values: &[f32]) -> String {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    hash_bytes(&bytes)
}

fn hash_f64(values: &[f64]) -> String {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    hash_bytes(&bytes)
}

fn hash_u64(values: &[u64]) -> String {
    let bytes: Vec<u8> = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    hash_bytes(&bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_passes_with_explicit_reference_dispatch() {
        let fixture = ProjectionFixture::synthetic_q8_0();
        let result =
            run_projection_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(
            result.classification,
            ValidationClassification::GoldenIdentical
        );
        assert!(result.memory_admitted);
        assert_eq!(result.dispatch, ProjectionDispatch::ExplicitReference);
        assert_eq!(result.telemetry.storage_read_requests, 1);
        assert_eq!(result.telemetry.storage_read_bytes, 68);
        assert_eq!(result.telemetry.decode_operations, 1);
        assert_eq!(result.telemetry.buffer_materialization_operations, 1);
        assert_eq!(result.telemetry.backend_build_import_operations, 0);
        assert_eq!(result.telemetry.compute_operations, 1);
        assert_eq!(
            result.reference_output_sha256,
            PROJECTION_REFERENCE_OUTPUT_SHA256
        );
    }

    #[test]
    fn unexpected_direct_dispatch_fails_closed() {
        let fixture = ProjectionFixture::synthetic_q8_0();
        assert!(matches!(
            run_projection_fixture(&fixture, ProjectionDispatch::QualifiedDirect),
            Err(ProjectionParityError::UnexpectedDispatch {
                expected: ProjectionDispatch::QualifiedDirect,
                actual: ProjectionDispatch::ExplicitReference,
            })
        ));
    }

    #[test]
    fn malformed_projection_bytes_do_not_modify_output() {
        let fixture = ProjectionFixture::synthetic_q8_0();
        let malformed = fixture.encoded[..fixture.encoded.len() - 1].to_vec();
        let mut output = vec![7.0_f32; PROJECTION_ROWS * PROJECTION_COLUMNS];
        let error =
            decode_q8_0_matrix(&malformed, PROJECTION_ROWS, PROJECTION_COLUMNS, &mut output)
                .unwrap_err();
        assert_eq!(output, vec![7.0; PROJECTION_ROWS * PROJECTION_COLUMNS]);
        assert!(!format!("{error}").is_empty());
    }

    #[test]
    fn projection_result_is_deterministic() {
        let fixture = ProjectionFixture::synthetic_q8_0();
        let first =
            run_projection_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        let second =
            run_projection_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(first, second);
    }

    #[test]
    fn router_passes_with_deterministic_ties_weights_and_aggregation() {
        let fixture = RouterFixture::synthetic();
        let result = run_router_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(
            result.classification,
            ValidationClassification::NumericallyQualifiedGreedyIdentical
        );
        assert!(result.memory_admitted);
        assert_eq!(result.telemetry.storage_read_requests, 1);
        assert_eq!(result.telemetry.storage_read_bytes, 64);
        assert_eq!(result.telemetry.buffer_materialization_operations, 1);
        assert_eq!(result.telemetry.compute_operations, 1);
        assert_eq!(result.selected_ids_sha256, ROUTER_IDS_SHA256);
        assert_eq!(result.weights_sha256, ROUTER_WEIGHTS_SHA256);
        assert_eq!(result.output_sha256, ROUTER_OUTPUT_SHA256);
    }

    #[test]
    fn malformed_router_fixture_fails_before_dispatch() {
        let mut fixture = RouterFixture::synthetic();
        fixture.scores[0] = f64::NAN;
        assert_eq!(
            run_router_fixture(&fixture, ProjectionDispatch::ExplicitReference),
            Err(RouterParityError::HashMismatch("scores"))
        );
    }

    #[test]
    fn expert_passes_with_explicit_reference_dispatch() {
        let fixture = ExpertFixture::synthetic();
        let result = run_expert_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(
            result.classification,
            ValidationClassification::GoldenIdentical
        );
        assert!(result.memory_admitted);
        assert_eq!(result.dispatch, ProjectionDispatch::ExplicitReference);
        assert_eq!(result.telemetry.storage_read_requests, 3);
        assert_eq!(
            result.telemetry.storage_read_bytes,
            3 * EXPERT_ROWS as u64 * 34
        );
        assert_eq!(result.telemetry.decode_operations, 3);
        assert_eq!(result.telemetry.buffer_materialization_operations, 3);
        assert_eq!(result.telemetry.backend_build_import_operations, 0);
        assert_eq!(result.telemetry.compute_operations, 4);
        assert_eq!(result.output_sha256, EXPERT_REFERENCE_OUTPUT_SHA256);
    }

    #[test]
    fn malformed_expert_bytes_do_not_modify_decoded_output() {
        let fixture = ExpertFixture::synthetic();
        let malformed = fixture.gate_encoded[..fixture.gate_encoded.len() - 1].to_vec();
        let mut output = vec![7.0_f32; EXPERT_ROWS * EXPERT_COLUMNS];
        let error =
            decode_q8_0_matrix(&malformed, EXPERT_ROWS, EXPERT_COLUMNS, &mut output).unwrap_err();
        assert_eq!(output, vec![7.0; EXPERT_ROWS * EXPERT_COLUMNS]);
        assert!(!format!("{error}").is_empty());
    }

    #[test]
    fn unexpected_expert_direct_dispatch_fails_closed() {
        let fixture = ExpertFixture::synthetic();
        assert!(matches!(
            run_expert_fixture(&fixture, ProjectionDispatch::QualifiedDirect),
            Err(ExpertParityError::UnexpectedDispatch {
                expected: ProjectionDispatch::QualifiedDirect,
                actual: ProjectionDispatch::ExplicitReference,
            })
        ));
    }

    #[test]
    fn expert_result_is_deterministic() {
        let fixture = ExpertFixture::synthetic();
        let first = run_expert_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        let second = run_expert_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        assert_eq!(first, second);
    }
}
