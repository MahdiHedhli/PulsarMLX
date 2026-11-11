//! Allocation-free accounting of the source's separately retained representations.
use super::{refusal, BoundedSource, HeldFile, Result};
use mlx_affine::QuantSpec;
use safetensors_catalog::{HeaderTensor, ShardHeader, ShardProvenance, TensorMeta, MAX_DEPTH};
use serde_json::Value;
use std::{fs::File, mem::size_of};

#[derive(Default)]
struct Count(u64);

impl Count {
    fn bytes(&mut self, n: usize) -> Result<()> {
        self.0 = self
            .0
            .checked_add(u64::try_from(n).map_err(|_| refusal("OVERFLOW", "metadata size"))?)
            .ok_or_else(|| refusal("OVERFLOW", "metadata sum"))?;
        Ok(())
    }

    fn rows<T>(&mut self, len: usize) -> Result<()> {
        self.bytes(
            len.checked_mul(size_of::<T>())
                .ok_or_else(|| refusal("OVERFLOW", "metadata rows"))?,
        )
    }

    fn strings(&mut self, map: &std::collections::BTreeMap<String, String>) -> Result<()> {
        self.rows::<(String, String)>(map.len())?;
        for (key, value) in map {
            self.bytes(key.len())?;
            self.bytes(value.len())?;
        }
        Ok(())
    }

    fn json(&mut self, value: &Value, depth: usize) -> Result<()> {
        if depth > MAX_DEPTH {
            return Err(refusal("LIMIT", "metadata JSON depth"));
        }
        match value {
            Value::String(s) => self.bytes(s.len())?,
            Value::Array(v) => {
                self.rows::<Value>(v.len())?;
                for child in v {
                    self.json(child, depth + 1)?;
                }
            }
            Value::Object(o) => {
                self.rows::<(String, Value)>(o.len())?;
                for (key, child) in o {
                    self.bytes(key.len())?;
                    self.json(child, depth + 1)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
}

impl BoundedSource {
    pub fn logical_metadata_bytes(&self) -> Result<u64> {
        let mut n = Count::default();
        n.rows::<Self>(1)?;
        n.bytes(self.identity.len())?;
        n.bytes(self._directory.display().len())?;
        n.bytes(self.checkpoint.root_name().len())?;
        let shards = self.checkpoint.shards();
        n.rows::<ShardProvenance>(shards.len())?;
        n.rows::<Option<File>>(shards.len())?;
        for shard in shards {
            n.bytes(shard.file_name.len())?;
        }
        for header in self.checkpoint.headers() {
            n.rows::<ShardHeader>(1)?;
            n.strings(&header.metadata)?;
            n.rows::<(String, HeaderTensor)>(header.tensors.len())?;
            for (key, tensor) in &header.tensors {
                n.bytes(key.len())?;
                n.bytes(tensor.name.len())?;
                n.rows::<u64>(tensor.shape.len())?;
            }
        }
        let catalog = self.checkpoint.catalog();
        n.rows::<(String, TensorMeta)>(catalog.len())?;
        for (key, tensor) in catalog.iter() {
            n.bytes(key.len())?;
            n.bytes(tensor.name.len())?;
            n.rows::<u64>(tensor.shape.len())?;
        }
        if let Some(index) = self.checkpoint.index() {
            n.strings(&index.weight_map)?;
        }
        n.rows::<(String, QuantSpec)>(self.config.overrides().len())?;
        for name in self.config.overrides().keys() {
            n.bytes(name.len())?;
        }
        n.rows::<(String, HeldFile)>(self.held.len())?;
        for name in self.held.keys() {
            n.bytes(name.len())?;
        }
        n.json(&self.config_document, 0)?;
        Ok(n.0)
    }

    pub fn metadata_snapshot(&self) -> &str {
        &self.identity
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn json_payload_and_limits() {
        let mut n = Count::default();
        n.json(&serde_json::json!({"xy":["abc",7]}), 0).unwrap();
        assert_eq!(
            n.0 as usize,
            size_of::<(String, Value)>() + 2 + 2 * size_of::<Value>() + 3
        );
        assert!(n.json(&Value::Null, MAX_DEPTH + 1).is_err());
        assert!(Count(u64::MAX).bytes(1).is_err());
        assert!(n.rows::<Value>(usize::MAX).is_err());
    }
}
