//! `crates/backend`'s byte-oriented tensor traits, implemented for
//! [`Checkpoint`].
//!
//! `backend` is the workspace's backend-neutral contract crate and has no
//! dependencies of its own, so implementing its traits here costs nothing and
//! changes nothing in it. `RuntimeTensor.quantization` is filled with the
//! Safetensors dtype string: at this layer that *is* the whole storage
//! description. What the packed `U32` of an affine triple means is resolved a
//! layer up, in `mlx-affine`, from the checkpoint's configuration.

use backend::runtime::{CancellationToken, RuntimeTensor, TensorCatalog, TensorRange, TensorStore};
use backend::{ContractError, ErrorCategory};

use crate::checkpoint::{Checkpoint, TensorMeta};

fn to_contract(code: &'static str, message: impl AsRef<str>) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, code, message)
}

impl Checkpoint {
    fn runtime_tensor(&self, tensor: &TensorMeta) -> Result<RuntimeTensor, ContractError> {
        let shard = self
            .shard_name(tensor.shard)
            .map_err(|error| to_contract("safetensors_shard_unknown", error.to_string()))?;
        Ok(RuntimeTensor {
            name: tensor.name.clone(),
            shard: shard.to_string(),
            range: TensorRange {
                offset: tensor.data_begin,
                length: tensor.byte_len,
            },
            shape: tensor.shape.clone(),
            quantization: tensor.dtype.as_str().to_string(),
        })
    }
}

impl TensorCatalog for Checkpoint {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        match self.catalog().get(name) {
            None => Ok(None),
            Some(tensor) => Ok(Some(self.runtime_tensor(tensor)?)),
        }
    }
}

impl TensorStore for Checkpoint {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        destination: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancellation.check()?;
        let meta = self.catalog().get(&tensor.name).ok_or_else(|| {
            to_contract(
                "safetensors_catalog_entry_missing",
                "tensor is not in the catalog",
            )
        })?;
        let expected = self.runtime_tensor(meta)?;
        if *tensor != expected {
            return Err(ContractError::new(
                ErrorCategory::InvalidModel,
                "safetensors_catalog_identity_mismatch",
                "the requested runtime tensor differs from the catalog entry",
            ));
        }
        let length = usize::try_from(expected.range.length).map_err(|_| {
            ContractError::new(
                ErrorCategory::ResourceLimit,
                "safetensors_allocation_too_large",
                "the tensor exceeds the bounded allocation limit",
            )
        })?;
        if destination.len() != length {
            return Err(to_contract(
                "safetensors_destination_length_mismatch",
                "the destination does not cover the complete tensor range",
            ));
        }
        cancellation.check()?;
        Checkpoint::read_range(self, meta, 0, expected.range.length, destination)
            .map_err(|error| to_contract("safetensors_read_failed", error.to_string()))?;
        Ok(length)
    }
}
