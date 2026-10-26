//! Public-package integration: compile/link with `cargo test -p engine
//! --test host_step_package --no-run`. Do not run native-linked artifacts under
//! the bounded host qualification; the fixture itself uses no native APIs.

use backend::step::{HostLayerExecutor, HostTensorStore, StepCoordinator, U32FixtureBackend};
use backend::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, GenerationState,
    MemoryBudget, RuntimeTensor, TensorCatalog, TensorRange, TensorStore,
};
use engine::host_step;
use stream::{
    ExpertSource, MatrixReadSpec, PositionalRead, PositionalSource, Read, ReadTelemetry,
    ReaderShard, SlabAllocatorError, SourceError, StableSlab, StableSlabAllocator,
    StableSlabConfig, ZeroingPolicy,
};

struct Bytes([u8; 4]);

impl PositionalRead for Bytes {
    fn read_at(&self, destination: &mut [u8], offset: u64) -> std::io::Result<usize> {
        let offset = usize::try_from(offset)
            .map_err(|_| std::io::Error::from(std::io::ErrorKind::InvalidInput))?;
        let source = self.0.get(offset..).unwrap_or_default();
        let count = source.len().min(destination.len());
        destination[..count].copy_from_slice(&source[..count]);
        Ok(count)
    }
}

struct Fixture {
    tensor: RuntimeTensor,
    lease: StableSlab,
}

impl TensorCatalog for Fixture {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok((name == self.tensor.name).then(|| self.tensor.clone()))
    }
}

impl HostTensorStore for Fixture {
    fn validate_range(&self, tensor: &RuntimeTensor) -> Result<(), ContractError> {
        if tensor != &self.tensor || tensor.range.end()? != self.lease.as_slice().len() as u64 {
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
        destination: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancellation.check()?;
        self.validate_range(tensor)?;
        if destination.len() != self.lease.as_slice().len() {
            return Err(ContractError::new(
                ErrorCategory::InvalidTensor,
                "fixture_destination",
                "fixture destination length mismatch",
            ));
        }
        destination.copy_from_slice(self.lease.as_slice());
        Ok(destination.len())
    }
}

// These must be the same public coordinator type and the real backend trait.
fn through_engine<B: HostLayerExecutor>(host: StepCoordinator<B>) -> host_step::StepCoordinator<B> {
    host
}

#[test]
fn actual_storage_types_feed_the_public_engine_coordinator(
) -> Result<(), Box<dyn std::error::Error>> {
    let read = Read { offset: 0, len: 4 };
    let mut source = PositionalSource::from_readers(vec![ReaderShard::new(
        0,
        4,
        "synthetic-u32",
        Box::new(Bytes(7_u32.to_le_bytes())),
    )])?;
    let payload = source.fetch_exact(read)?;
    assert_eq!(payload.range(), read);
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        4,
        16,
        1,
        ZeroingPolicy::ZeroOnAcquire,
    ))
    .expect("valid fixture slab configuration");
    let mut lease = allocator.acquire().expect("one fixture lease fits");
    lease.as_mut_slice().copy_from_slice(payload.payload());
    let fixture = Fixture {
        tensor: RuntimeTensor {
            name: "input".into(),
            shard: "synthetic-u32".into(),
            range: TensorRange {
                offset: read.offset,
                length: read.len,
            },
            shape: vec![1],
            quantization: "fixture-u32-le".into(),
        },
        lease,
    };
    let checkpoint = CheckpointIdentity::try_new("a".repeat(64), "synthetic-v1")?;
    let request = host_step::StepRequest {
        id: "package-step-0".into(),
        checkpoint: checkpoint.clone(),
        expected_position: 0,
        inputs: vec![fixture.tensor.clone()],
        layers: vec![1, 2],
        scratch_bytes: 4,
        output_bytes: 4,
    };
    let mut host = through_engine(StepCoordinator::new(
        checkpoint,
        MemoryBudget::try_new(1024, 256, 128)?,
        GenerationState::default(),
        U32FixtureBackend::default(),
    )?);
    let result = host.execute(
        &request,
        &fixture,
        &fixture,
        &CancellationToken::new(),
        |_| Ok(()),
    )?;
    assert_eq!(result.committed.token, 10);
    assert_eq!(host.state().tokens(), [10]);
    assert_eq!(host.active_reservations(), 0);

    // Exercise refusals through the real public package types, without allocating
    // a huge buffer or mutating private counters to synthesize overflow.
    let cap_failure: SourceError = source
        .fetch_matrix_whole(
            MatrixReadSpec {
                tensor_offset: 0,
                rows: 1,
                row_bytes: 4,
            },
            1,
            &mut ReadTelemetry::default(),
        )
        .unwrap_err();
    assert!(matches!(
        cap_failure,
        SourceError::MatrixRequestLimit {
            row_bytes: 4,
            max_request_bytes: 1
        }
    ));
    let capacity_failure: SlabAllocatorError = StableSlabAllocator::new(StableSlabConfig::new(
        usize::MAX,
        16,
        1,
        ZeroingPolicy::NoZero,
    ))
    .err()
    .ok_or("unrepresentable capacity accepted")?;
    assert!(matches!(
        capacity_failure,
        SlabAllocatorError::InvalidCapacity { .. }
    ));
    Ok(())
}
