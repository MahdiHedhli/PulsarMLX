use crate::{FailureClass, RunnerError};
use gguf::{Gguf, TensorInfo, TensorType};
use std::collections::{BTreeMap, HashMap, HashSet};

pub const GLM52_LAYER_COUNT: u64 = 79;
pub const GLM52_LEADING_DENSE_LAYER_COUNT: u64 = 3;
pub const GLM52_EXPERT_COUNT: u64 = 256;
pub const GLM52_EXPERT_USED_COUNT: u64 = 8;
pub const GLM52_SHARED_EXPERT_COUNT: u64 = 1;
pub const GLM52_EMBEDDING_LENGTH: u64 = 6144;
pub const GLM52_VOCAB_SIZE: u64 = 154_880;
pub const GLM52_TENSOR_COUNT: usize = 1_809;

#[derive(Debug, Clone)]
pub struct Glm52TensorMap {
    tensors: BTreeMap<String, TensorInfo>,
}

#[derive(Debug, Clone)]
pub struct Glm52FixtureTensorContract {
    pub name: String,
    pub dims: Vec<u64>,
    pub tensor_type: TensorType,
}

#[derive(Debug, Clone)]
pub struct Glm52FixtureTensorMap {
    tensors: BTreeMap<String, TensorInfo>,
}

impl Glm52TensorMap {
    pub fn from_gguf(catalog: &Gguf) -> Result<Self, RunnerError> {
        require_arch_meta(catalog, "block_count", GLM52_LAYER_COUNT)?;
        require_arch_meta(
            catalog,
            "leading_dense_block_count",
            GLM52_LEADING_DENSE_LAYER_COUNT,
        )?;
        require_arch_meta(catalog, "expert_count", GLM52_EXPERT_COUNT)?;
        require_arch_meta(catalog, "expert_used_count", GLM52_EXPERT_USED_COUNT)?;
        require_arch_meta(catalog, "expert_shared_count", GLM52_SHARED_EXPERT_COUNT)?;
        require_arch_meta(catalog, "embedding_length", GLM52_EMBEDDING_LENGTH)?;
        require_arch_meta(catalog, "vocab_size", GLM52_VOCAB_SIZE)?;
        Self::from_parts(catalog.architecture(), catalog.tensors.iter().cloned())
    }

    pub fn from_parts(
        architecture: Option<&str>,
        tensors: impl IntoIterator<Item = TensorInfo>,
    ) -> Result<Self, RunnerError> {
        let expected = expected_contracts();
        let bindings = bind_exact_contracts(architecture, tensors, expected, GLM52_TENSOR_COUNT)?;
        Ok(Self { tensors: bindings })
    }

    pub fn tensor(&self, name: &str) -> Option<&TensorInfo> {
        self.tensors.get(name)
    }

    pub fn len(&self) -> usize {
        self.tensors.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tensors.is_empty()
    }

    pub fn layer_tensor(&self, layer: u32, suffix: &str) -> Option<&TensorInfo> {
        self.tensor(&format!("blk.{layer}.{suffix}"))
    }
}

impl Glm52FixtureTensorMap {
    pub fn from_parts(
        architecture: Option<&str>,
        tensors: impl IntoIterator<Item = TensorInfo>,
        contracts: impl IntoIterator<Item = Glm52FixtureTensorContract>,
    ) -> Result<Self, RunnerError> {
        let expected = contracts
            .into_iter()
            .map(|contract| TensorContract {
                name: contract.name,
                dims: contract.dims,
                types: vec![contract.tensor_type],
            })
            .collect::<Vec<_>>();
        let count = expected.len();
        let tensors = bind_exact_contracts(architecture, tensors, expected, count)?;
        Ok(Self { tensors })
    }

    pub fn tensor(&self, name: &str) -> Option<&TensorInfo> {
        self.tensors.get(name)
    }

    pub fn len(&self) -> usize {
        self.tensors.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tensors.is_empty()
    }
}

#[derive(Debug)]
struct TensorContract {
    name: String,
    dims: Vec<u64>,
    types: Vec<TensorType>,
}

const F32: &[TensorType] = &[TensorType::F32];
const Q4K: &[TensorType] = &[TensorType::Q4K];
const Q5K: &[TensorType] = &[TensorType::Q5K];
const Q6K: &[TensorType] = &[TensorType::Q6K];
const Q8_0: &[TensorType] = &[TensorType::Q8_0];
const Q5K_Q6K: &[TensorType] = &[TensorType::Q5K, TensorType::Q6K];
const Q6K_Q8_0: &[TensorType] = &[TensorType::Q6K, TensorType::Q8_0];
const ROUTED_GATE_UP: &[TensorType] = &[TensorType::IQ2XXS, TensorType::IQ2S, TensorType::Q2K];
const ROUTED_DOWN: &[TensorType] = &[TensorType::IQ3XXS, TensorType::IQ4XS, TensorType::Q3K];

fn expected_contracts() -> Vec<TensorContract> {
    let mut contracts = vec![
        contract("token_embd.weight", &[6144, 154_880], Q4K),
        contract("output_norm.weight", &[6144], F32),
        contract("output.weight", &[6144, 154_880], Q4K),
    ];
    for layer in 0..GLM52_LAYER_COUNT {
        let prefix = format!("blk.{layer}");
        contracts.extend([
            contract(format!("{prefix}.attn_k_b.weight"), &[192, 512, 64], Q8_0),
            contract(format!("{prefix}.attn_kv_a_mqa.weight"), &[6144, 576], Q8_0),
            contract(format!("{prefix}.attn_kv_a_norm.weight"), &[512], F32),
            contract(format!("{prefix}.attn_norm.weight"), &[6144], F32),
            contract(
                format!("{prefix}.attn_output.weight"),
                &[16_384, 6144],
                Q5K_Q6K,
            ),
            contract(format!("{prefix}.attn_q_a.weight"), &[6144, 2048], Q5K_Q6K),
            contract(format!("{prefix}.attn_q_a_norm.weight"), &[2048], F32),
            contract(format!("{prefix}.attn_q_b.weight"), &[2048, 16_384], Q8_0),
            contract(format!("{prefix}.attn_v_b.weight"), &[512, 256, 64], Q8_0),
            contract(
                format!("{prefix}.indexer.attn_k.weight"),
                &[6144, 128],
                Q8_0,
            ),
            contract(
                format!("{prefix}.indexer.attn_q_b.weight"),
                &[2048, 4096],
                Q8_0,
            ),
            contract(format!("{prefix}.indexer.k_norm.bias"), &[128], F32),
            contract(format!("{prefix}.indexer.k_norm.weight"), &[128], F32),
            contract(format!("{prefix}.indexer.proj.weight"), &[6144, 32], F32),
        ]);
        if layer < GLM52_LEADING_DENSE_LAYER_COUNT {
            contracts.extend([
                contract(format!("{prefix}.ffn_down.weight"), &[12_288, 6144], Q6K),
                contract(format!("{prefix}.ffn_gate.weight"), &[6144, 12_288], Q5K),
                contract(format!("{prefix}.ffn_norm.weight"), &[6144], F32),
                contract(format!("{prefix}.ffn_up.weight"), &[6144, 12_288], Q5K),
            ]);
        } else {
            contracts.extend([
                contract(format!("{prefix}.exp_probs_b.bias"), &[256], F32),
                contract(
                    format!("{prefix}.ffn_down_exps.weight"),
                    &[2048, 6144, 256],
                    ROUTED_DOWN,
                ),
                contract(
                    format!("{prefix}.ffn_down_shexp.weight"),
                    &[2048, 6144],
                    Q6K_Q8_0,
                ),
                contract(
                    format!("{prefix}.ffn_gate_exps.weight"),
                    &[6144, 2048, 256],
                    ROUTED_GATE_UP,
                ),
                contract(format!("{prefix}.ffn_gate_inp.weight"), &[6144, 256], F32),
                contract(
                    format!("{prefix}.ffn_gate_shexp.weight"),
                    &[6144, 2048],
                    Q5K_Q6K,
                ),
                contract(format!("{prefix}.ffn_norm.weight"), &[6144], F32),
                contract(
                    format!("{prefix}.ffn_up_exps.weight"),
                    &[6144, 2048, 256],
                    ROUTED_GATE_UP,
                ),
                contract(
                    format!("{prefix}.ffn_up_shexp.weight"),
                    &[6144, 2048],
                    Q5K_Q6K,
                ),
            ]);
        }
    }
    contracts.extend([
        contract("blk.78.nextn.eh_proj.weight", &[12_288, 6144], Q8_0),
        contract("blk.78.nextn.enorm.weight", &[6144], F32),
        contract("blk.78.nextn.hnorm.weight", &[6144], F32),
        contract("blk.78.nextn.shared_head_norm.weight", &[6144], F32),
    ]);
    contracts
}

fn contract(name: impl Into<String>, dims: &[u64], types: &'static [TensorType]) -> TensorContract {
    TensorContract {
        name: name.into(),
        dims: dims.to_vec(),
        types: types.to_vec(),
    }
}

fn bind_exact_contracts(
    architecture: Option<&str>,
    tensors: impl IntoIterator<Item = TensorInfo>,
    expected: Vec<TensorContract>,
    required_count: usize,
) -> Result<BTreeMap<String, TensorInfo>, RunnerError> {
    if architecture != Some("glm-dsa") {
        return Err(map_error(
            "glm52_architecture",
            "tensor map requires architecture glm-dsa",
        ));
    }
    let mut actual = HashMap::new();
    for tensor in tensors {
        if actual.insert(tensor.name.clone(), tensor).is_some() {
            return Err(map_error(
                "glm52_duplicate_tensor",
                "tensor map contains a duplicate name",
            ));
        }
    }
    if actual.len() != expected.len() || expected.len() != required_count {
        return Err(map_error(
            "glm52_tensor_count",
            format!(
                "tensor map has {} names; exact contract requires {}",
                actual.len(),
                required_count
            ),
        ));
    }
    let expected_names = expected
        .iter()
        .map(|contract| contract.name.as_str())
        .collect::<HashSet<_>>();
    let unexpected = actual
        .keys()
        .filter(|name| !expected_names.contains(name.as_str()))
        .take(3)
        .cloned()
        .collect::<Vec<_>>();
    if !unexpected.is_empty() {
        return Err(map_error(
            "glm52_unexpected_tensor",
            format!("unexpected tensor names: {}", unexpected.join(", ")),
        ));
    }
    let mut bindings = BTreeMap::new();
    for contract in expected {
        let tensor = actual.remove(&contract.name).ok_or_else(|| {
            map_error(
                "glm52_missing_tensor",
                format!("missing tensor {}", contract.name),
            )
        })?;
        if tensor.dims != contract.dims {
            return Err(map_error(
                "glm52_tensor_shape",
                format!(
                    "tensor {} has dimensions {:?}; expected {:?}",
                    tensor.name, tensor.dims, contract.dims
                ),
            ));
        }
        if !contract.types.contains(&tensor.ty) {
            return Err(map_error(
                "glm52_tensor_quantization",
                format!(
                    "tensor {} has unsupported type {:?}; accepted {:?}",
                    tensor.name, tensor.ty, contract.types
                ),
            ));
        }
        bindings.insert(tensor.name.clone(), tensor);
    }
    Ok(bindings)
}

fn require_arch_meta(catalog: &Gguf, suffix: &str, expected: u64) -> Result<(), RunnerError> {
    let actual = catalog.arch_meta(suffix).and_then(gguf::Value::as_u64);
    if actual != Some(expected) {
        return Err(map_error(
            "glm52_metadata",
            format!("glm-dsa.{suffix} is {actual:?}; expected {expected}"),
        ));
    }
    Ok(())
}

fn map_error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::CheckpointIdentity, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Deserialize;
    use std::fs;
    use std::path::Path;

    #[derive(Deserialize)]
    struct CatalogEvidence {
        architecture: String,
        tensor_count: usize,
        tensors: Vec<CatalogTensor>,
    }

    #[derive(Deserialize)]
    struct CatalogTensor {
        name: String,
        dims: Vec<u64>,
        type_id: u32,
        data_offset_rel: u64,
    }

    #[test]
    fn committed_public_catalog_satisfies_exact_tensor_map() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../docs/research/glm52/raw/f016-c01-catalog-0001.json");
        let bytes = fs::read(path).expect("committed public catalog");
        let evidence: CatalogEvidence =
            crate::json::parse_json_no_duplicates(&bytes).expect("catalog evidence JSON");
        assert_eq!(evidence.tensor_count, GLM52_TENSOR_COUNT);
        let tensors = evidence.tensors.into_iter().map(|tensor| TensorInfo {
            name: tensor.name,
            dims: tensor.dims,
            ty: TensorType::from_id(tensor.type_id),
            offset: tensor.data_offset_rel,
        });
        let map = Glm52TensorMap::from_parts(Some(&evidence.architecture), tensors)
            .expect("validated GLM-5.2 map");
        assert_eq!(map.len(), GLM52_TENSOR_COUNT);
        assert!(map.tensor("token_embd.weight").is_some());
        assert!(map.layer_tensor(3, "ffn_gate_exps.weight").is_some());
        assert!(map.layer_tensor(78, "nextn.eh_proj.weight").is_some());
    }

    #[test]
    fn missing_shape_and_ambiguous_names_fail_closed() {
        let mut tensors = expected_contracts()
            .into_iter()
            .map(|contract| TensorInfo {
                name: contract.name,
                dims: contract.dims,
                ty: contract.types[0],
                offset: 0,
            })
            .collect::<Vec<_>>();
        tensors[0].dims[0] = 1;
        assert_eq!(
            Glm52TensorMap::from_parts(Some("glm-dsa"), tensors)
                .unwrap_err()
                .code,
            "glm52_tensor_shape"
        );

        let mut tensors = expected_contracts()
            .into_iter()
            .map(|contract| TensorInfo {
                name: contract.name,
                dims: contract.dims,
                ty: contract.types[0],
                offset: 0,
            })
            .collect::<Vec<_>>();
        tensors[1].name = tensors[0].name.clone();
        assert_eq!(
            Glm52TensorMap::from_parts(Some("glm-dsa"), tensors)
                .unwrap_err()
                .code,
            "glm52_duplicate_tensor"
        );
    }
}
