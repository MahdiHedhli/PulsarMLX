//! cargo run --locked --offline -p backend --example host_lifecycle
//! CPU-only synthetic fixture: deliver fails once, then replays retained bytes.
use backend::step::{HostTensorStore, StepCoordinator, StepRequest, U32FixtureBackend};
use backend::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, GenerationState,
    MemoryBudget, RuntimeTensor, TensorCatalog, TensorRange, TensorStore,
};

struct Fixture {
    tensor: RuntimeTensor,
    bytes: [u8; 4],
}
impl TensorCatalog for Fixture {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok((name == self.tensor.name).then(|| self.tensor.clone()))
    }
}
impl HostTensorStore for Fixture {
    fn validate_range(&self, tensor: &RuntimeTensor) -> Result<(), ContractError> {
        if tensor != &self.tensor || tensor.range.end()? != self.bytes.len() as u64 {
            return Err(ContractError::new(
                ErrorCategory::InvalidTensor,
                "fixture_range",
                "fixture descriptor mismatch",
            ));
        }
        Ok(())
    }
}
impl TensorStore for Fixture {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        bytes: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancel.check()?;
        self.validate_range(tensor)?;
        bytes.copy_from_slice(&self.bytes);
        Ok(bytes.len())
    }
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let checkpoint = CheckpointIdentity::try_new("a".repeat(64), "synthetic-v1")?;
    let fixture = Fixture {
        tensor: RuntimeTensor {
            name: "input".into(),
            shard: "fixture".into(),
            range: TensorRange {
                offset: 0,
                length: 4,
            },
            shape: vec![1],
            quantization: "fixture-u32-le".into(),
        },
        bytes: 7_u32.to_le_bytes(),
    };
    let request = StepRequest {
        id: "step-0".into(),
        checkpoint: checkpoint.clone(),
        expected_position: 0,
        inputs: vec![fixture.tensor.clone()],
        layers: vec![1, 2],
        scratch_bytes: 4,
        output_bytes: 4,
    };
    let mut host = StepCoordinator::new(
        checkpoint,
        MemoryBudget::try_new(1024, 256, 128)?,
        GenerationState::default(),
        U32FixtureBackend::default(),
    )?;
    let cancel = CancellationToken::new();
    let first = host.execute(&request, &fixture, &fixture, &cancel, |_| {
        Err(ContractError::new(
            ErrorCategory::InvalidStateTransition,
            "delivery_failed",
            "simulated delivery fault",
        ))
    })?;
    assert_eq!(first.committed.token, 10);
    assert!(first.delivery_error.is_some());
    println!(
        "COMMITTED position={} token={} delivery=failed retained=true",
        first.committed.position, first.committed.token
    );
    let retry = host.execute(&request, &fixture, &fixture, &cancel, |result| {
        assert_eq!(result.bytes, 10_u32.to_le_bytes());
        Ok(())
    })?;
    assert!(retry.replayed);
    assert_eq!(host.state().tokens(), [10]);
    assert_eq!(host.backend().dispatches(), 2);
    assert_eq!(host.active_reservations(), 0);
    assert!(!host.backend().has_staged_resources());
    println!(
        "COMMITTED replay=true position={} dispatches={} active_reservations=0",
        host.state().position(),
        host.backend().dispatches()
    );
    Ok(())
}
