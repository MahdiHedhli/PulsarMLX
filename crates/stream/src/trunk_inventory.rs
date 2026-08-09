use serde::Deserialize;

pub const AUTHORITATIVE_TENSOR_COUNT: u64 = 1_353;
pub const AUTHORITATIVE_EXCLUDED_EXPERT_MATRIX_COUNT: u64 = 456;
pub const AUTHORITATIVE_COMPRESSED_BYTES: u64 = 13_474_784_256;
pub const AUTHORITATIVE_DECODED_F32_BYTES: u64 = 66_223_309_824;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct TrunkGroupSummary {
    pub trunk_group: String,
    pub tensor_count: u64,
    pub compressed_bytes: u64,
    pub decoded_f32_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct TrunkTensorSummary {
    pub name: String,
    pub trunk_group: String,
    pub quantization: String,
    pub compressed_bytes: u64,
    pub decoded_f32_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct TrunkInventorySummary {
    pub schema: String,
    pub schema_version: String,
    pub tensor_count: u64,
    pub excluded_expert_matrix_count: u64,
    pub total_compressed_bytes: u64,
    pub total_decoded_f32_bytes: u64,
    pub by_trunk_group: Vec<TrunkGroupSummary>,
    pub tensors: Vec<TrunkTensorSummary>,
}

impl TrunkInventorySummary {
    pub fn from_json(data: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(data)
    }

    pub fn validate_authoritative(&self) -> Result<(), String> {
        if self.schema != "pulsarmlx.research.glm52-gguf-trunk-inventory" {
            return Err(format!("unexpected inventory schema {:?}", self.schema));
        }
        if self.schema_version != "1.0.0" {
            return Err(format!("unexpected inventory schema version {:?}", self.schema_version));
        }
        if self.tensor_count != AUTHORITATIVE_TENSOR_COUNT {
            return Err(format!("unexpected tensor count {}", self.tensor_count));
        }
        if self.excluded_expert_matrix_count != AUTHORITATIVE_EXCLUDED_EXPERT_MATRIX_COUNT {
            return Err(format!(
                "unexpected excluded expert matrix count {}",
                self.excluded_expert_matrix_count
            ));
        }
        if self.total_compressed_bytes != AUTHORITATIVE_COMPRESSED_BYTES {
            return Err(format!(
                "unexpected compressed byte total {}",
                self.total_compressed_bytes
            ));
        }
        if self.total_decoded_f32_bytes != AUTHORITATIVE_DECODED_F32_BYTES {
            return Err(format!(
                "unexpected decoded byte total {}",
                self.total_decoded_f32_bytes
            ));
        }
        if self.tensors.len() as u64 != self.tensor_count {
            return Err(format!("unexpected tensor records {}", self.tensors.len()));
        }

        let group_compressed = self
            .by_trunk_group
            .iter()
            .try_fold(0_u64, |total, group| total.checked_add(group.compressed_bytes));
        let group_decoded = self
            .by_trunk_group
            .iter()
            .try_fold(0_u64, |total, group| total.checked_add(group.decoded_f32_bytes));
        let group_tensors = self
            .by_trunk_group
            .iter()
            .try_fold(0_u64, |total, group| total.checked_add(group.tensor_count));
        let (Some(group_compressed), Some(group_decoded), Some(group_tensors)) =
            (group_compressed, group_decoded, group_tensors)
        else {
            return Err("trunk-group totals overflow".to_owned());
        };
        if group_compressed != self.total_compressed_bytes
            || group_decoded != self.total_decoded_f32_bytes
            || group_tensors != self.tensor_count
        {
            return Err("trunk-group totals do not match inventory totals".to_owned());
        }
        Ok(())
    }

    pub fn group(&self, name: &str) -> Option<&TrunkGroupSummary> {
        self.by_trunk_group
            .iter()
            .find(|group| group.trunk_group == name)
    }

    pub fn tensor_sizes(&self) -> impl Iterator<Item = (u64, u64)> + '_ {
        self.tensors
            .iter()
            .map(|tensor| (tensor.compressed_bytes, tensor.decoded_f32_bytes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::Path;

    fn inventory_json() -> String {
        fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json"),
        )
        .expect("read authoritative trunk inventory")
    }

    #[test]
    fn authoritative_inventory_totals_are_ingested() {
        let inventory = TrunkInventorySummary::from_json(&inventory_json())
            .expect("inventory parses");
        inventory
            .validate_authoritative()
            .expect("inventory totals remain authoritative");
        assert_eq!(inventory.tensor_count, AUTHORITATIVE_TENSOR_COUNT);
        assert_eq!(
            inventory.group("output_head").unwrap().decoded_f32_bytes,
            3_806_355_456
        );
    }

    #[test]
    fn reject_inventory_total_drift() {
        let mut inventory = TrunkInventorySummary::from_json(&inventory_json())
            .expect("inventory parses");
        inventory.total_decoded_f32_bytes += 1;
        assert!(inventory.validate_authoritative().is_err());
    }
}
