use backend::{MemoryBudget, RoutingPlan};
use quant::decode_q8_0_matrix;
use sha2::{Digest, Sha256};
use std::fmt;
use std::time::Duration;
use stream::{
    ExpertAdmissionPolicy, ExpertAdmissionRequest, ExpertKey, ExpertKind, ExpertLifecycle,
    ExpertResidencyTable, ExpertResidencyTier, RuntimeTelemetry, SlotId, TelemetryBucket,
    TelemetrySnapshot, ValidationClassification,
};

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
pub const TOP8_SHARED_FIXTURE_VERSION: &str = "glm52-runtime-top8-shared-v1";
pub const TOP8_SHARED_ROUTER_TENSOR_NAME: &str = "synthetic.blk.0.ffn_gate_inp.weight";
pub const TOP8_SHARED_ROUTED_TENSOR_NAME: &str = "synthetic.blk.0.ffn_experts.weight";
pub const TOP8_SHARED_SHARED_TENSOR_NAME: &str = "synthetic.blk.0.ffn_shared_expert.weight";
pub const TOP8_SHARED_TENSOR_SHARD: &str = "synthetic-trunk-00001";
pub const TOP8_SHARED_OUTPUT_WIDTH: usize = 2;
const TOP8_SHARED_SCORES_SHA256: &str =
    "e718add56286e18ff81450763e0c2f227a35a73195fe0ed038a3d155711599e9";
const TOP8_SHARED_ROUTED_SHA256: &str =
    "d65ec8230922af8bf4bbf3a1e7d412788b6f498da72051f72b0fc21cddf29908";
const TOP8_SHARED_SHARED_SHA256: &str =
    "ffd197f51045b6ab70c0b9e786c2e9d3098dbccdeafa53f32a2d7b0920b3c5c2";
const TOP8_SHARED_RESIDUAL_SHA256: &str =
    "b74fce6cd8bcafd014a1ce8c6585beac59c5f4098a6d499f5d1d42d464146633";
const TOP8_SHARED_OUTPUT_SHA256: &str =
    "08f6285a290c60d7e9f6d39890fd7173e28044499ddc3c5e64266522c91089bc";
pub const MLA_DENSE_FIXTURE_VERSION: &str = "glm52-runtime-mla-dense-v1";
pub const MLA_DENSE_QUERY_TENSOR_NAME: &str = "synthetic.blk.0.attn_q.weight";
pub const MLA_DENSE_KEY_TENSOR_NAME: &str = "synthetic.blk.0.attn_k.weight";
pub const MLA_DENSE_VALUE_TENSOR_NAME: &str = "synthetic.blk.0.attn_v.weight";
pub const MLA_DENSE_OUTPUT_TENSOR_NAME: &str = "synthetic.blk.0.attn_o.weight";
pub const MLA_DENSE_TENSOR_SHARD: &str = "synthetic-trunk-00001";
const MLA_DENSE_QUERY_SHA256: &str =
    "dc91ce9a50ddc828740aa26743716897fdb2bb64f1db662fe263a59be56145ae";
const MLA_DENSE_KEYS_SHA256: &str =
    "f652af1297e907749725d45a6880a3f4c541fd9290bc2c79e8c68b013ec1d4ab";
const MLA_DENSE_VALUES_SHA256: &str =
    "9f94a24f3f648f60bc02bcb8844d3ca21708f17f9833a200b7f9fd65281acff5";
const MLA_DENSE_PROJECTION_SHA256: &str =
    "71b86374c0cb45f7268948d366a6cc9b43d2de00c92c5f4417097c4e17fa4b36";
const MLA_DENSE_RESIDUAL_SHA256: &str =
    "c60fb7d5e38a94bfbe33b33f187596b2b1cd91c78bf15bbaf0769d6a9edbe90c";
const MLA_DENSE_OUTPUT_SHA256: &str =
    "98e7e51398cd0186f16f5b2295d1e502416ef40e3746b43f9d3966fa1ceb62a3";
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
pub struct Top8SharedFixture {
    pub source_commit: &'static str,
    pub fixture_version: &'static str,
    pub tensor_names: [&'static str; 3],
    pub tensor_shard: &'static str,
    pub dimensions: [usize; 3],
    pub quantization: &'static str,
    pub dtype: &'static str,
    pub scores: Vec<f64>,
    pub routed_outputs: Vec<f64>,
    pub shared_output: Vec<f64>,
    pub residual: Vec<f64>,
}

impl Top8SharedFixture {
    pub fn synthetic() -> Self {
        Self {
            source_commit: PROJECTION_SOURCE_COMMIT,
            fixture_version: TOP8_SHARED_FIXTURE_VERSION,
            tensor_names: [
                TOP8_SHARED_ROUTER_TENSOR_NAME,
                TOP8_SHARED_ROUTED_TENSOR_NAME,
                TOP8_SHARED_SHARED_TENSOR_NAME,
            ],
            tensor_shard: TOP8_SHARED_TENSOR_SHARD,
            dimensions: [1, 8, TOP8_SHARED_OUTPUT_WIDTH],
            quantization: "F32",
            dtype: "f64",
            scores: (0..8).map(|expert| expert as f64).collect(),
            routed_outputs: (0..8)
                .flat_map(|expert| [expert as f64 + 1.0, -(expert as f64)])
                .collect(),
            shared_output: vec![0.25, -0.5],
            residual: vec![1.0, -1.0],
        }
    }

    pub fn validate(&self) -> Result<(), Top8SharedParityError> {
        if self.source_commit != PROJECTION_SOURCE_COMMIT {
            return Err(Top8SharedParityError::InvalidFixture("source_commit"));
        }
        if self.fixture_version != TOP8_SHARED_FIXTURE_VERSION {
            return Err(Top8SharedParityError::InvalidFixture("fixture_version"));
        }
        if self.tensor_names
            != [
                TOP8_SHARED_ROUTER_TENSOR_NAME,
                TOP8_SHARED_ROUTED_TENSOR_NAME,
                TOP8_SHARED_SHARED_TENSOR_NAME,
            ]
            || self.tensor_shard != TOP8_SHARED_TENSOR_SHARD
            || self.dimensions != [1, 8, TOP8_SHARED_OUTPUT_WIDTH]
            || self.quantization != "F32"
            || self.dtype != "f64"
        {
            return Err(Top8SharedParityError::InvalidFixture("tensor identity"));
        }
        if self.scores.len() != 8
            || self.routed_outputs.len() != 8 * TOP8_SHARED_OUTPUT_WIDTH
            || self.shared_output.len() != TOP8_SHARED_OUTPUT_WIDTH
            || self.residual.len() != TOP8_SHARED_OUTPUT_WIDTH
        {
            return Err(Top8SharedParityError::InvalidFixture("shape"));
        }
        if hash_f64(&self.scores) != TOP8_SHARED_SCORES_SHA256 {
            return Err(Top8SharedParityError::HashMismatch("router scores"));
        }
        if hash_f64(&self.routed_outputs) != TOP8_SHARED_ROUTED_SHA256 {
            return Err(Top8SharedParityError::HashMismatch("routed expert outputs"));
        }
        if hash_f64(&self.shared_output) != TOP8_SHARED_SHARED_SHA256 {
            return Err(Top8SharedParityError::HashMismatch("shared expert output"));
        }
        if hash_f64(&self.residual) != TOP8_SHARED_RESIDUAL_SHA256 {
            return Err(Top8SharedParityError::HashMismatch("residual"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Top8SharedParityError {
    InvalidFixture(&'static str),
    HashMismatch(&'static str),
    MemoryRejected,
    Residency(String),
    UnexpectedDispatch {
        expected: ProjectionDispatch,
        actual: ProjectionDispatch,
    },
    Routing(String),
    NumericalMismatch(&'static str),
    Telemetry(String),
}

impl fmt::Display for Top8SharedParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidFixture(field) => {
                write!(formatter, "invalid top-8 shared fixture: {field}")
            }
            Self::HashMismatch(field) => {
                write!(formatter, "top-8 shared fixture hash mismatch: {field}")
            }
            Self::MemoryRejected => {
                formatter.write_str("top-8 shared fixture rejected by memory budget")
            }
            Self::Residency(error) => write!(formatter, "top-8 shared residency failed: {error}"),
            Self::UnexpectedDispatch { expected, actual } => write!(
                formatter,
                "unexpected top-8 shared dispatch: expected {expected:?}, got {actual:?}"
            ),
            Self::Routing(error) => write!(formatter, "top-8 shared routing failed: {error}"),
            Self::NumericalMismatch(stage) => {
                write!(formatter, "top-8 shared numerical mismatch: {stage}")
            }
            Self::Telemetry(error) => write!(formatter, "top-8 shared telemetry failed: {error}"),
        }
    }
}

impl std::error::Error for Top8SharedParityError {}

#[derive(Debug, Clone, PartialEq)]
pub struct Top8SharedParityResult {
    pub classification: ValidationClassification,
    pub dispatch: ProjectionDispatch,
    pub memory_admitted: bool,
    pub shared_protected: bool,
    pub routed_residency: ExpertResidencyTier,
    pub shared_residency: ExpertResidencyTier,
    pub telemetry: TelemetrySnapshot,
    pub output_sha256: String,
}

pub fn run_top8_shared_fixture(
    fixture: &Top8SharedFixture,
    expected_dispatch: ProjectionDispatch,
) -> Result<Top8SharedParityResult, Top8SharedParityError> {
    fixture.validate()?;
    let memory = MemoryBudget::try_new(
        M2_MAX_TOTAL_BYTES,
        M2_MAX_SAFETY_RESERVE_BYTES,
        M2_MAX_TOTAL_BYTES - M2_MAX_SAFETY_RESERVE_BYTES - M2_MAX_REQUIRED_MARGIN_BYTES,
    )
    .map_err(|_| Top8SharedParityError::MemoryRejected)?;
    let requested_bytes = ((fixture.scores.len() + fixture.routed_outputs.len())
        * std::mem::size_of::<f64>()
        + (fixture.shared_output.len() + fixture.residual.len()) * std::mem::size_of::<f64>())
        as u64;
    if !memory.admits(requested_bytes) {
        return Err(Top8SharedParityError::MemoryRejected);
    }
    let actual_dispatch = ProjectionDispatch::ExplicitReference;
    if actual_dispatch != expected_dispatch {
        return Err(Top8SharedParityError::UnexpectedDispatch {
            expected: expected_dispatch,
            actual: actual_dispatch,
        });
    }

    let policy = ExpertAdmissionPolicy::new(4096, 8, true, true)
        .ok_or_else(|| Top8SharedParityError::Residency("invalid policy".to_owned()))?;
    let mut residency = ExpertResidencyTable::new(policy);
    let routed_key = ExpertKey {
        layer: 0,
        expert: 7,
        kind: ExpertKind::Routed,
    };
    let shared_key = ExpertKey {
        layer: 0,
        expert: 0,
        kind: ExpertKind::Shared,
    };
    residency
        .admit(ExpertAdmissionRequest {
            key: routed_key,
            tier: ExpertResidencyTier::CompressedResident,
            bytes: 512,
            slot_id: SlotId(7),
            protected: false,
        })
        .map_err(|error| Top8SharedParityError::Residency(format!("routed: {error:?}")))?;
    let shared_entry = residency
        .admit(ExpertAdmissionRequest {
            key: shared_key,
            tier: ExpertResidencyTier::NativeReadyHot,
            bytes: 512,
            slot_id: SlotId(0),
            protected: true,
        })
        .map_err(|error| Top8SharedParityError::Residency(format!("shared: {error:?}")))?;
    if !shared_entry.protected
        || residency.fallback(shared_key) != stream::ExpertFallback::Native(shared_entry)
    {
        return Err(Top8SharedParityError::Residency(
            "shared expert was not protected native-ready".to_owned(),
        ));
    }
    residency
        .transition(shared_key, ExpertLifecycle::Leased)
        .and_then(|_| residency.transition(shared_key, ExpertLifecycle::Pinned))
        .map_err(|error| Top8SharedParityError::Residency(format!("lifecycle: {error:?}")))?;

    let mut telemetry = RuntimeTelemetry::new();
    telemetry
        .record_storage_read(
            Duration::from_nanos(1),
            3,
            (fixture.scores.len() + fixture.routed_outputs.len() + fixture.shared_output.len())
                as u64
                * std::mem::size_of::<f64>() as u64,
        )
        .map_err(|error| Top8SharedParityError::Telemetry(format!("{error:?}")))?;
    telemetry
        .record_stage(
            TelemetryBucket::BufferMaterialization,
            Duration::from_nanos(1),
            2,
        )
        .map_err(|error| Top8SharedParityError::Telemetry(format!("{error:?}")))?;

    let plan = RoutingPlan::try_softmax(&fixture.scores, 1, 8, 8)
        .map_err(|error| Top8SharedParityError::Routing(error.to_string()))?;
    let expected_ids: Vec<u64> = (0..8).rev().collect();
    if plan.selected_expert_ids() != expected_ids {
        return Err(Top8SharedParityError::NumericalMismatch("expert ordering"));
    }
    let reference_weights = reference_softmax(&fixture.scores);
    if plan
        .normalized_weights()
        .iter()
        .zip(reference_weights.iter())
        .any(|(actual, expected)| (actual - expected).abs() > 1.0e-12)
    {
        return Err(Top8SharedParityError::NumericalMismatch("routing weights"));
    }
    let routed = plan
        .aggregate_selected_outputs(&fixture.routed_outputs, TOP8_SHARED_OUTPUT_WIDTH as u64)
        .map_err(|error| Top8SharedParityError::Routing(error.to_string()))?;
    let reference_routed = reference_aggregate(&reference_weights, &fixture.routed_outputs);
    let output: Vec<f64> = routed
        .iter()
        .zip(fixture.shared_output.iter().zip(fixture.residual.iter()))
        .map(|(routed, (shared, residual))| routed + shared + residual)
        .collect();
    let reference_output: Vec<f64> = reference_routed
        .iter()
        .zip(fixture.shared_output.iter().zip(fixture.residual.iter()))
        .map(|(routed, (shared, residual))| routed + shared + residual)
        .collect();
    if output
        .iter()
        .zip(reference_output.iter())
        .any(|(actual, expected)| (actual - expected).abs() > 1.0e-12)
    {
        return Err(Top8SharedParityError::NumericalMismatch(
            "shared aggregation",
        ));
    }
    let output_sha256 = hash_f64(&reference_output);
    if output_sha256 != TOP8_SHARED_OUTPUT_SHA256 {
        return Err(Top8SharedParityError::HashMismatch("reference output"));
    }
    telemetry
        .record_stage(
            TelemetryBucket::BackendBuildImport,
            Duration::from_nanos(1),
            1,
        )
        .and_then(|_| telemetry.record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 2))
        .map_err(|error| Top8SharedParityError::Telemetry(format!("{error:?}")))?;
    Ok(Top8SharedParityResult {
        classification: ValidationClassification::NumericallyQualifiedGreedyIdentical,
        dispatch: actual_dispatch,
        memory_admitted: true,
        shared_protected: shared_entry.protected,
        routed_residency: ExpertResidencyTier::CompressedResident,
        shared_residency: ExpertResidencyTier::NativeReadyHot,
        telemetry: telemetry
            .snapshot()
            .map_err(|error| Top8SharedParityError::Telemetry(format!("{error:?}")))?,
        output_sha256,
    })
}

fn reference_softmax(scores: &[f64]) -> Vec<f64> {
    let max = scores.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let weights: Vec<f64> = scores
        .iter()
        .rev()
        .map(|score| (score - max).exp())
        .collect();
    let total: f64 = weights.iter().sum();
    weights.into_iter().map(|weight| weight / total).collect()
}

fn reference_aggregate(weights: &[f64], selected_outputs: &[f64]) -> Vec<f64> {
    (0..TOP8_SHARED_OUTPUT_WIDTH)
        .map(|column| {
            weights
                .iter()
                .enumerate()
                .map(|(expert, weight)| {
                    weight * selected_outputs[expert * TOP8_SHARED_OUTPUT_WIDTH + column]
                })
                .sum()
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq)]
pub struct MlaDenseFixture {
    pub source_commit: &'static str,
    pub fixture_version: &'static str,
    pub tensor_names: [&'static str; 4],
    pub tensor_shard: &'static str,
    pub dimensions: [usize; 3],
    pub dtype: &'static str,
    pub query: Vec<f64>,
    pub keys: Vec<f64>,
    pub values: Vec<f64>,
    pub output_projection: Vec<f64>,
    pub residual: Vec<f64>,
    pub query_position: u64,
    pub key_positions: [u64; 2],
    pub rope_theta: f64,
}

impl MlaDenseFixture {
    pub fn synthetic() -> Self {
        Self {
            source_commit: PROJECTION_SOURCE_COMMIT,
            fixture_version: MLA_DENSE_FIXTURE_VERSION,
            tensor_names: [
                MLA_DENSE_QUERY_TENSOR_NAME,
                MLA_DENSE_KEY_TENSOR_NAME,
                MLA_DENSE_VALUE_TENSOR_NAME,
                MLA_DENSE_OUTPUT_TENSOR_NAME,
            ],
            tensor_shard: MLA_DENSE_TENSOR_SHARD,
            dimensions: [2, 2, 2],
            dtype: "f64",
            query: vec![1.0, 2.0],
            keys: vec![2.0, 1.0, 1.5, -0.5],
            values: vec![0.5, -1.0, 1.5, 0.25],
            output_projection: vec![1.0, -0.5, 0.25, 1.25],
            residual: vec![0.75, -0.25],
            query_position: 2,
            key_positions: [0, 1],
            rope_theta: 0.25,
        }
    }

    pub fn validate(&self) -> Result<(), MlaDenseParityError> {
        if self.source_commit != PROJECTION_SOURCE_COMMIT {
            return Err(MlaDenseParityError::InvalidFixture("source_commit"));
        }
        if self.fixture_version != MLA_DENSE_FIXTURE_VERSION {
            return Err(MlaDenseParityError::InvalidFixture("fixture_version"));
        }
        if self.tensor_names
            != [
                MLA_DENSE_QUERY_TENSOR_NAME,
                MLA_DENSE_KEY_TENSOR_NAME,
                MLA_DENSE_VALUE_TENSOR_NAME,
                MLA_DENSE_OUTPUT_TENSOR_NAME,
            ]
            || self.tensor_shard != MLA_DENSE_TENSOR_SHARD
            || self.dimensions != [2, 2, 2]
            || self.dtype != "f64"
        {
            return Err(MlaDenseParityError::InvalidFixture("tensor identity"));
        }
        if self.query.len() != 2
            || self.keys.len() != 4
            || self.values.len() != 4
            || self.output_projection.len() != 4
            || self.residual.len() != 2
            || !self.rope_theta.is_finite()
            || self.rope_theta <= 0.0
        {
            return Err(MlaDenseParityError::InvalidFixture("shape or position"));
        }
        if hash_f64(&self.query) != MLA_DENSE_QUERY_SHA256 {
            return Err(MlaDenseParityError::HashMismatch("query"));
        }
        if hash_f64(&self.keys) != MLA_DENSE_KEYS_SHA256 {
            return Err(MlaDenseParityError::HashMismatch("keys"));
        }
        if hash_f64(&self.values) != MLA_DENSE_VALUES_SHA256 {
            return Err(MlaDenseParityError::HashMismatch("values"));
        }
        if hash_f64(&self.output_projection) != MLA_DENSE_PROJECTION_SHA256 {
            return Err(MlaDenseParityError::HashMismatch("output projection"));
        }
        if hash_f64(&self.residual) != MLA_DENSE_RESIDUAL_SHA256 {
            return Err(MlaDenseParityError::HashMismatch("residual"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MlaDenseParityError {
    InvalidFixture(&'static str),
    HashMismatch(&'static str),
    MemoryRejected,
    UnexpectedDispatch {
        expected: ProjectionDispatch,
        actual: ProjectionDispatch,
    },
    NumericalMismatch(&'static str),
    Telemetry(String),
}

impl fmt::Display for MlaDenseParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidFixture(field) => write!(formatter, "invalid MLA/dense fixture: {field}"),
            Self::HashMismatch(field) => {
                write!(formatter, "MLA/dense fixture hash mismatch: {field}")
            }
            Self::MemoryRejected => {
                formatter.write_str("MLA/dense fixture rejected by memory budget")
            }
            Self::UnexpectedDispatch { expected, actual } => write!(
                formatter,
                "unexpected MLA/dense dispatch: expected {expected:?}, got {actual:?}"
            ),
            Self::NumericalMismatch(stage) => {
                write!(formatter, "MLA/dense numerical mismatch: {stage}")
            }
            Self::Telemetry(error) => write!(formatter, "MLA/dense telemetry failed: {error}"),
        }
    }
}

impl std::error::Error for MlaDenseParityError {}

#[derive(Debug, Clone, PartialEq)]
pub struct MlaDenseParityResult {
    pub classification: ValidationClassification,
    pub dispatch: ProjectionDispatch,
    pub memory_admitted: bool,
    pub telemetry: TelemetrySnapshot,
    pub output_sha256: String,
}

pub fn run_mla_dense_fixture(
    fixture: &MlaDenseFixture,
    expected_dispatch: ProjectionDispatch,
) -> Result<MlaDenseParityResult, MlaDenseParityError> {
    fixture.validate()?;
    let memory = MemoryBudget::try_new(
        M2_MAX_TOTAL_BYTES,
        M2_MAX_SAFETY_RESERVE_BYTES,
        M2_MAX_TOTAL_BYTES - M2_MAX_SAFETY_RESERVE_BYTES - M2_MAX_REQUIRED_MARGIN_BYTES,
    )
    .map_err(|_| MlaDenseParityError::MemoryRejected)?;
    let requested_bytes = (fixture.query.len()
        + fixture.keys.len()
        + fixture.values.len()
        + fixture.output_projection.len()
        + fixture.residual.len()) as u64
        * std::mem::size_of::<f64>() as u64;
    if !memory.admits(requested_bytes) {
        return Err(MlaDenseParityError::MemoryRejected);
    }
    let actual_dispatch = ProjectionDispatch::ExplicitReference;
    if actual_dispatch != expected_dispatch {
        return Err(MlaDenseParityError::UnexpectedDispatch {
            expected: expected_dispatch,
            actual: actual_dispatch,
        });
    }
    let mut telemetry = RuntimeTelemetry::new();
    telemetry
        .record_storage_read(Duration::from_nanos(1), 4, requested_bytes)
        .map_err(|error| MlaDenseParityError::Telemetry(format!("{error:?}")))?;
    telemetry
        .record_stage(
            TelemetryBucket::BufferMaterialization,
            Duration::from_nanos(1),
            4,
        )
        .map_err(|error| MlaDenseParityError::Telemetry(format!("{error:?}")))?;

    let rotated_query = rotate_pair(&fixture.query, fixture.query_position, fixture.rope_theta);
    let rotated_keys = [
        rotate_pair(
            &fixture.keys[0..2],
            fixture.key_positions[0],
            fixture.rope_theta,
        ),
        rotate_pair(
            &fixture.keys[2..4],
            fixture.key_positions[1],
            fixture.rope_theta,
        ),
    ];
    let scores = rotated_keys
        .iter()
        .map(|key| dot2(&rotated_query, key) / 2.0_f64.sqrt())
        .collect::<Vec<_>>();
    let weights = softmax_two(&scores);
    let attention = vec![
        weights[0] * fixture.values[0] + weights[1] * fixture.values[2],
        weights[0] * fixture.values[1] + weights[1] * fixture.values[3],
    ];
    let projected = matvec2(&fixture.output_projection, &attention);
    let output = projected
        .iter()
        .zip(fixture.residual.iter())
        .map(|(projected, residual)| projected + residual)
        .collect::<Vec<_>>();

    let reference_query =
        reference_rotate_pair(&fixture.query, fixture.query_position, fixture.rope_theta);
    let reference_keys = [
        reference_rotate_pair(
            &fixture.keys[0..2],
            fixture.key_positions[0],
            fixture.rope_theta,
        ),
        reference_rotate_pair(
            &fixture.keys[2..4],
            fixture.key_positions[1],
            fixture.rope_theta,
        ),
    ];
    let reference_scores = reference_keys
        .iter()
        .map(|key| reference_dot2(&reference_query, key) / 2.0_f64.sqrt())
        .collect::<Vec<_>>();
    let reference_weights = reference_softmax_two(&reference_scores);
    let reference_attention = vec![
        reference_weights[0] * fixture.values[0] + reference_weights[1] * fixture.values[2],
        reference_weights[0] * fixture.values[1] + reference_weights[1] * fixture.values[3],
    ];
    let reference_projected = reference_matvec2(&fixture.output_projection, &reference_attention);
    let reference_output = reference_projected
        .iter()
        .zip(fixture.residual.iter())
        .map(|(projected, residual)| projected + residual)
        .collect::<Vec<_>>();
    if output != reference_output {
        return Err(MlaDenseParityError::NumericalMismatch("MLA/dense output"));
    }
    let output_sha256 = hash_f64(&reference_output);
    if output_sha256 != MLA_DENSE_OUTPUT_SHA256 {
        return Err(MlaDenseParityError::HashMismatch("reference output"));
    }
    telemetry
        .record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 4)
        .map_err(|error| MlaDenseParityError::Telemetry(format!("{error:?}")))?;
    Ok(MlaDenseParityResult {
        classification: ValidationClassification::GoldenIdentical,
        dispatch: actual_dispatch,
        memory_admitted: true,
        telemetry: telemetry
            .snapshot()
            .map_err(|error| MlaDenseParityError::Telemetry(format!("{error:?}")))?,
        output_sha256,
    })
}

fn rotate_pair(values: &[f64], position: u64, theta: f64) -> Vec<f64> {
    let angle = position as f64 * theta;
    let (sin, cos) = angle.sin_cos();
    vec![
        values[0] * cos - values[1] * sin,
        values[0] * sin + values[1] * cos,
    ]
}

fn reference_rotate_pair(values: &[f64], position: u64, theta: f64) -> Vec<f64> {
    let angle = theta * position as f64;
    let cos = angle.cos();
    let sin = angle.sin();
    vec![
        cos * values[0] - sin * values[1],
        sin * values[0] + cos * values[1],
    ]
}

fn dot2(left: &[f64], right: &[f64]) -> f64 {
    left[0] * right[0] + left[1] * right[1]
}

fn reference_dot2(left: &[f64], right: &[f64]) -> f64 {
    let first = left[0] * right[0];
    let second = left[1] * right[1];
    first + second
}

fn softmax_two(scores: &[f64]) -> Vec<f64> {
    let max = scores[0].max(scores[1]);
    let first = (scores[0] - max).exp();
    let second = (scores[1] - max).exp();
    let total = first + second;
    vec![first / total, second / total]
}

fn reference_softmax_two(scores: &[f64]) -> Vec<f64> {
    let max = if scores[0] > scores[1] {
        scores[0]
    } else {
        scores[1]
    };
    let first_exp = (scores[0] - max).exp();
    let second_exp = (scores[1] - max).exp();
    let denominator = first_exp + second_exp;
    vec![first_exp / denominator, second_exp / denominator]
}

fn matvec2(matrix: &[f64], vector: &[f64]) -> Vec<f64> {
    vec![
        matrix[0] * vector[0] + matrix[1] * vector[1],
        matrix[2] * vector[0] + matrix[3] * vector[1],
    ]
}

fn reference_matvec2(matrix: &[f64], vector: &[f64]) -> Vec<f64> {
    let first = matrix[0] * vector[0] + matrix[1] * vector[1];
    let second = matrix[2] * vector[0] + matrix[3] * vector[1];
    vec![first, second]
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
    fn top8_shared_passes_with_protected_shared_residency() {
        let fixture = Top8SharedFixture::synthetic();
        let result =
            run_top8_shared_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(
            result.classification,
            ValidationClassification::NumericallyQualifiedGreedyIdentical
        );
        assert!(result.memory_admitted);
        assert!(result.shared_protected);
        assert_eq!(
            result.routed_residency,
            ExpertResidencyTier::CompressedResident
        );
        assert_eq!(result.shared_residency, ExpertResidencyTier::NativeReadyHot);
        assert_eq!(result.telemetry.storage_read_requests, 3);
        assert_eq!(result.telemetry.buffer_materialization_operations, 2);
        assert_eq!(result.telemetry.backend_build_import_operations, 1);
        assert_eq!(result.telemetry.compute_operations, 2);
        assert_eq!(result.output_sha256, TOP8_SHARED_OUTPUT_SHA256);
    }

    #[test]
    fn malformed_top8_shared_fixture_fails_before_dispatch() {
        let mut fixture = Top8SharedFixture::synthetic();
        fixture.scores[0] = f64::NAN;
        assert_eq!(
            run_top8_shared_fixture(&fixture, ProjectionDispatch::ExplicitReference),
            Err(Top8SharedParityError::HashMismatch("router scores"))
        );
    }

    #[test]
    fn mla_dense_passes_with_explicit_reference_dispatch() {
        let fixture = MlaDenseFixture::synthetic();
        let result =
            run_mla_dense_fixture(&fixture, ProjectionDispatch::ExplicitReference).unwrap();
        assert_eq!(
            result.classification,
            ValidationClassification::GoldenIdentical
        );
        assert!(result.memory_admitted);
        assert_eq!(result.dispatch, ProjectionDispatch::ExplicitReference);
        assert_eq!(result.telemetry.storage_read_requests, 4);
        assert_eq!(result.telemetry.buffer_materialization_operations, 4);
        assert_eq!(result.telemetry.compute_operations, 4);
        assert_eq!(result.output_sha256, MLA_DENSE_OUTPUT_SHA256);
    }

    #[test]
    fn malformed_mla_dense_fixture_fails_before_dispatch() {
        let mut fixture = MlaDenseFixture::synthetic();
        fixture.query[0] = f64::NAN;
        assert_eq!(
            run_mla_dense_fixture(&fixture, ProjectionDispatch::ExplicitReference),
            Err(MlaDenseParityError::HashMismatch("query"))
        );
    }

    #[test]
    fn unexpected_mla_dense_direct_dispatch_fails_closed() {
        let fixture = MlaDenseFixture::synthetic();
        assert!(matches!(
            run_mla_dense_fixture(&fixture, ProjectionDispatch::QualifiedDirect),
            Err(MlaDenseParityError::UnexpectedDispatch {
                expected: ProjectionDispatch::QualifiedDirect,
                actual: ProjectionDispatch::ExplicitReference,
            })
        ));
    }

    #[test]
    fn mla_dense_result_is_deterministic() {
        let fixture = MlaDenseFixture::synthetic();
        let first = run_mla_dense_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        let second = run_mla_dense_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        assert_eq!(first, second);
    }

    #[test]
    fn unexpected_top8_shared_direct_dispatch_fails_closed() {
        let fixture = Top8SharedFixture::synthetic();
        assert!(matches!(
            run_top8_shared_fixture(&fixture, ProjectionDispatch::QualifiedDirect),
            Err(Top8SharedParityError::UnexpectedDispatch {
                expected: ProjectionDispatch::QualifiedDirect,
                actual: ProjectionDispatch::ExplicitReference,
            })
        ));
    }

    #[test]
    fn top8_shared_result_is_deterministic() {
        let fixture = Top8SharedFixture::synthetic();
        let first = run_top8_shared_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        let second = run_top8_shared_fixture(&fixture, ProjectionDispatch::ExplicitReference);
        assert_eq!(first, second);
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
