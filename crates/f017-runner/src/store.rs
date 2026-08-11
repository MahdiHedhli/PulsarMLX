use crate::checkpoint::VerifiedCheckpoint;
use crate::{FailureClass, RunnerError};
use backend::{
    CancellationToken, ContractError, RuntimeTensor, TensorCatalog, TensorRange, TensorStore,
};
use std::sync::Mutex;
use stream::{ExpertSource, PositionalSource, Read, ShardPath};

pub struct RunnerTensorStore {
    checkpoint: VerifiedCheckpoint,
    source: Mutex<PositionalSource>,
}

impl RunnerTensorStore {
    pub fn open(checkpoint: VerifiedCheckpoint) -> Result<Self, RunnerError> {
        let paths = checkpoint
            .shards
            .iter()
            .map(|shard| ShardPath {
                base: shard.base,
                path: shard.path.clone(),
            })
            .collect::<Vec<_>>();
        let source = PositionalSource::open_split(&paths).map_err(|error| {
            RunnerError::new(
                FailureClass::CheckpointIdentity,
                "tensor_store_open",
                error.to_string(),
            )
        })?;
        Ok(Self {
            checkpoint,
            source: Mutex::new(source),
        })
    }

    pub fn read_tensor_exact(
        &self,
        name: &str,
        cancellation: &CancellationToken,
    ) -> Result<Vec<u8>, ContractError> {
        let tensor = self.tensor(name)?.ok_or_else(|| {
            contract_error(
                "tensor_missing",
                "tensor is absent from the validated catalog",
            )
        })?;
        let length = usize::try_from(tensor.range.length)
            .map_err(|_| contract_error("tensor_length", "tensor length exceeds usize"))?;
        let mut destination = vec![0_u8; length];
        let actual = self.read_range(&tensor, &mut destination, cancellation)?;
        if actual != length {
            return Err(contract_error(
                "tensor_short_read",
                "tensor store returned a short read",
            ));
        }
        Ok(destination)
    }

    pub fn checkpoint(&self) -> &VerifiedCheckpoint {
        &self.checkpoint
    }
}

impl TensorCatalog for RunnerTensorStore {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        let Some(tensor) = self.checkpoint.catalog.tensor(name) else {
            return Ok(None);
        };
        let length = tensor
            .byte_size()
            .ok_or_else(|| contract_error("tensor_type", "tensor byte layout is unsupported"))?;
        let offset = self
            .checkpoint
            .catalog
            .data_offset
            .checked_add(tensor.offset)
            .ok_or_else(|| contract_error("tensor_offset", "tensor offset overflow"))?;
        let shard = self
            .checkpoint
            .shards
            .iter()
            .find(|shard| offset >= shard.base && offset < shard.base + shard.size_bytes)
            .ok_or_else(|| {
                contract_error("tensor_shard", "tensor offset does not belong to a shard")
            })?;
        Ok(Some(RuntimeTensor {
            name: tensor.name.clone(),
            shard: shard.filename.clone(),
            range: TensorRange { offset, length },
            shape: tensor.dims.clone(),
            quantization: format!("{:?}", tensor.ty),
        }))
    }
}

impl TensorStore for RunnerTensorStore {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        destination: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancellation.check()?;
        let expected = usize::try_from(tensor.range.length)
            .map_err(|_| contract_error("tensor_length", "tensor length exceeds usize"))?;
        if destination.len() != expected {
            return Err(contract_error(
                "tensor_destination",
                "destination length must equal tensor length",
            ));
        }
        let mut source = self
            .source
            .lock()
            .map_err(|_| contract_error("tensor_store_lock", "tensor store lock is poisoned"))?;
        let slab = source
            .fetch_exact(Read {
                offset: tensor.range.offset,
                len: tensor.range.length,
            })
            .map_err(|_| contract_error("tensor_read", "exact positional tensor read failed"))?;
        destination.copy_from_slice(slab.payload());
        Ok(destination.len())
    }
}

fn contract_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(backend::ErrorCategory::InvalidModel, code, message)
}
