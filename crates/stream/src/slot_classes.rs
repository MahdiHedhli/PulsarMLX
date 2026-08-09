use std::collections::BTreeMap;

use crate::trunk_inventory::TrunkInventorySummary;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum SlotEncoding {
    Compressed,
    DecodedF32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservedSlotClass {
    pub trunk_group: String,
    pub quantization: String,
    pub encoding: SlotEncoding,
    pub slot_size_bytes: u64,
    pub tensor_count: u64,
    pub total_bytes: u64,
}

pub fn observed_slot_classes(
    inventory: &TrunkInventorySummary,
) -> Result<Vec<ObservedSlotClass>, String> {
    inventory.validate_authoritative()?;

    let mut classes = BTreeMap::<(String, String, SlotEncoding), ObservedSlotClass>::new();
    for tensor in &inventory.tensors {
        for (encoding, size) in [
            (SlotEncoding::Compressed, tensor.compressed_bytes),
            (SlotEncoding::DecodedF32, tensor.decoded_f32_bytes),
        ] {
            let key = (
                tensor.trunk_group.clone(),
                tensor.quantization.clone(),
                encoding,
            );
            let entry = classes.entry(key).or_insert_with(|| ObservedSlotClass {
                trunk_group: tensor.trunk_group.clone(),
                quantization: tensor.quantization.clone(),
                encoding,
                slot_size_bytes: 0,
                tensor_count: 0,
                total_bytes: 0,
            });
            entry.slot_size_bytes = entry.slot_size_bytes.max(size);
            entry.tensor_count = entry
                .tensor_count
                .checked_add(1)
                .ok_or("slot class tensor count overflow")?;
            entry.total_bytes = entry
                .total_bytes
                .checked_add(size)
                .ok_or("slot class byte total overflow")?;
        }
    }
    Ok(classes.into_values().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::trunk_inventory::TrunkInventorySummary;
    use std::fs;
    use std::path::Path;

    fn inventory() -> TrunkInventorySummary {
        let data = fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json"),
        )
        .expect("read authoritative trunk inventory");
        TrunkInventorySummary::from_json(&data).expect("inventory parses")
    }

    #[test]
    fn slot_classes_are_derived_from_observed_tensor_sizes() {
        let inventory = inventory();
        let classes = observed_slot_classes(&inventory).expect("slot classes derive");
        assert!(!classes.is_empty());
        assert_eq!(classes.iter().map(|class| class.tensor_count).sum::<u64>(), 2_706);

        for class in &classes {
            assert!(class.slot_size_bytes > 0);
            assert!(inventory.tensors.iter().any(|tensor| {
                tensor.trunk_group == class.trunk_group
                    && tensor.quantization == class.quantization
                    && match class.encoding {
                        SlotEncoding::Compressed => tensor.compressed_bytes == class.slot_size_bytes,
                        SlotEncoding::DecodedF32 => tensor.decoded_f32_bytes == class.slot_size_bytes,
                    }
            }));
        }
    }
}
