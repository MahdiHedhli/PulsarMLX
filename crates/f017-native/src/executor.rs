//! Instantiable real bounded-P1 math producer. Preflight and one-shot
//! authority stay in the wrapper; this object owns the complete token graph.

use crate::loader::{CheckpointManifest, EvidencedTensorSource, SecureCheckpoint, TensorCatalog};
use crate::model::{
    execute_one_token, execute_one_token_observed, ExecutionObserver, ModelConfig, NativeMlxBackend,
};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;
use stream::{
    BoundedP1Math, EvidencedP1Math, MlxContext, P1EvidenceRecorder, P1LayerDiagnostic,
    P1NumericalDiagnosticManifest, DIAGNOSTIC_SCHEMA, EXPECTED_TOKEN,
};

pub struct FullNativeP1Math {
    pub checkpoint: SecureCheckpoint,
    pub config: ModelConfig,
    invocations: u32,
}
impl FullNativeP1Math {
    pub fn new(checkpoint: SecureCheckpoint, config: ModelConfig) -> Self {
        Self {
            checkpoint,
            config,
            invocations: 0,
        }
    }
}
impl BoundedP1Math for FullNativeP1Math {
    fn backend_id(&self) -> &'static str {
        "NATIVE_RUST_MLX_FULL_GLM52_ONE_TOKEN"
    }
    fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String> {
        if self.invocations != 0 {
            return Err("bounded math invoked more than once".into());
        }
        self.invocations = 1;
        execute_one_token(
            &mut self.checkpoint,
            &mut NativeMlxBackend { context },
            &self.config,
            prompt_token,
        )
    }
}

/// Forward-only generation: checkpoint opening and every tensor use occur
/// inside the RN1-owned evidenced attempt rather than in the wrapper.
pub struct FullNativeP1MathV3 {
    pub checkpoint_root: PathBuf,
    pub manifest: Option<CheckpointManifest>,
    pub catalog: Option<TensorCatalog>,
    pub config: ModelConfig,
    invocations: u32,
}

impl FullNativeP1MathV3 {
    pub fn new(
        checkpoint_root: PathBuf,
        manifest: CheckpointManifest,
        catalog: TensorCatalog,
        config: ModelConfig,
    ) -> Self {
        Self {
            checkpoint_root,
            manifest: Some(manifest),
            catalog: Some(catalog),
            config,
            invocations: 0,
        }
    }
}

fn f32_sha256(values: &[f32]) -> String {
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.to_bits().to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

struct DiagnosticObserver {
    durable_layer_directory: PathBuf,
    layers: Vec<P1LayerDiagnostic>,
    final_hidden_state_sha256: String,
    final_norm_sha256: String,
    full_logits_sha256: String,
    logits_shape: Vec<u64>,
    top_token_ids: Vec<u32>,
    top_logit_f32_bits: Vec<u32>,
    selected_token: Option<u32>,
}

impl DiagnosticObserver {
    fn new(durable_layer_directory: PathBuf) -> Self {
        Self {
            durable_layer_directory,
            layers: Vec::new(),
            final_hidden_state_sha256: String::new(),
            final_norm_sha256: String::new(),
            full_logits_sha256: String::new(),
            logits_shape: Vec::new(),
            top_token_ids: Vec::new(),
            top_logit_f32_bits: Vec::new(),
            selected_token: None,
        }
    }

    fn bank_layer(&self, layer: &P1LayerDiagnostic) -> Result<(), String> {
        let path = self
            .durable_layer_directory
            .join(format!("{:08}.json", layer.layer));
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o400)
            .open(&path)
            .map_err(|error| error.to_string())?;
        let mut bytes = serde_json::to_vec(layer).map_err(|error| error.to_string())?;
        bytes.push(b'\n');
        output
            .write_all(&bytes)
            .map_err(|error| error.to_string())?;
        output.sync_all().map_err(|error| error.to_string())?;
        File::open(&self.durable_layer_directory)
            .and_then(|directory| directory.sync_all())
            .map_err(|error| error.to_string())?;
        if fs::read(&path).map_err(|error| error.to_string())? != bytes {
            return Err("durable layer diagnostic readback mismatch".into());
        }
        Ok(())
    }

    fn finish(self) -> P1NumericalDiagnosticManifest {
        P1NumericalDiagnosticManifest {
            schema: DIAGNOSTIC_SCHEMA.into(),
            backend: "NATIVE_RUST_MLX_FULL_GLM52_ONE_TOKEN_EVIDENCED_V3".into(),
            serialization: "F32_LE_DIRECT_PRODUCTION_BUFFER_HASHES".into(),
            synchronization: "EACH_MLX_MATVEC_EVALUATED;CONTEXT_SYNC_BEFORE_POST_SNAPSHOT".into(),
            direct_production_bytes: true,
            layers: self.layers,
            final_hidden_state_sha256: self.final_hidden_state_sha256,
            final_norm_sha256: self.final_norm_sha256,
            full_logits_sha256: self.full_logits_sha256,
            logits_dtype: "little-endian-f32".into(),
            logits_shape: self.logits_shape,
            top_token_ids: self.top_token_ids,
            top_logit_f32_bits: self.top_logit_f32_bits,
            selected_token: self.selected_token,
            expected_token: EXPECTED_TOKEN,
            tie_rule: "LOWEST_TOKEN_ID_ON_EQUAL_F32_LOGIT".into(),
        }
    }
}

impl ExecutionObserver for DiagnosticObserver {
    fn layer(
        &mut self,
        layer: usize,
        layer_input: &[f32],
        post_attention_residual: &[f32],
        router_normalized_input: &[f32],
        selected_expert_ids: &[usize],
        routing_weights: &[f32],
        routed_aggregate: &[f32],
        shared_expert: &[f32],
        layer_output: &[f32],
    ) -> Result<(), String> {
        let diagnostic = P1LayerDiagnostic {
            layer: u32::try_from(layer).map_err(|_| "layer index")?,
            layer_input_sha256: f32_sha256(layer_input),
            post_attention_residual_sha256: f32_sha256(post_attention_residual),
            router_normalized_input_sha256: f32_sha256(router_normalized_input),
            selected_expert_ids: selected_expert_ids
                .iter()
                .map(|value| u32::try_from(*value).map_err(|_| "expert id".to_string()))
                .collect::<Result<Vec<_>, _>>()?,
            routing_weight_f32_bits: routing_weights
                .iter()
                .map(|value| value.to_bits())
                .collect(),
            routed_aggregate_sha256: f32_sha256(routed_aggregate),
            shared_expert_sha256: f32_sha256(shared_expert),
            layer_output_sha256: f32_sha256(layer_output),
            hidden_width: layer_output.len() as u64,
            dtype: "little-endian-f32".into(),
            byte_order: "coordinate-major-contiguous".into(),
        };
        self.bank_layer(&diagnostic)?;
        self.layers.push(diagnostic);
        Ok(())
    }

    fn final_output(
        &mut self,
        hidden: &[f32],
        normalized: &[f32],
        logits: &[f32],
        selected_token: u32,
    ) -> Result<(), String> {
        self.final_hidden_state_sha256 = f32_sha256(hidden);
        self.final_norm_sha256 = f32_sha256(normalized);
        self.full_logits_sha256 = f32_sha256(logits);
        self.logits_shape = vec![logits.len() as u64];
        let mut order = (0..logits.len()).collect::<Vec<_>>();
        order.sort_by(|left, right| {
            logits[*right]
                .total_cmp(&logits[*left])
                .then_with(|| left.cmp(right))
        });
        order.truncate(32.min(order.len()));
        self.top_token_ids = order.iter().map(|index| *index as u32).collect();
        self.top_logit_f32_bits = order.iter().map(|index| logits[*index].to_bits()).collect();
        self.selected_token = Some(selected_token);
        Ok(())
    }
}

impl EvidencedP1Math for FullNativeP1MathV3 {
    fn backend_id(&self) -> &'static str {
        "NATIVE_RUST_MLX_FULL_GLM52_ONE_TOKEN_EVIDENCED_V3"
    }

    fn execute_one_evidenced(
        &mut self,
        context: &MlxContext,
        prompt_token: u32,
        recorder: &mut P1EvidenceRecorder,
    ) -> Result<(u32, P1NumericalDiagnosticManifest), String> {
        if self.invocations != 0 {
            return Err("bounded evidenced math invoked more than once".into());
        }
        self.invocations = 1;
        let manifest = self
            .manifest
            .take()
            .ok_or("checkpoint manifest already consumed")?;
        let catalog = self
            .catalog
            .take()
            .ok_or("checkpoint catalog already consumed")?;
        let diagnostic_directory = recorder.diagnostic_layer_directory();
        let checkpoint =
            SecureCheckpoint::open_evidenced(&self.checkpoint_root, manifest, catalog, recorder)?;
        let mut source = EvidencedTensorSource::new(checkpoint, recorder);
        let mut observer = DiagnosticObserver::new(diagnostic_directory);
        let token = execute_one_token_observed(
            &mut source,
            &mut NativeMlxBackend { context },
            &self.config,
            prompt_token,
            &mut observer,
        )?;
        Ok((token, observer.finish()))
    }
}
