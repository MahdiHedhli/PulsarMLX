//! Storage/orchestration equality on generated marker bytes.
use mlx_expert_ranges::{
    residency::overlap::{Mode, StagedResidency},
    BoundedSource, ExpertRequest,
};
use serde_json::Value;
use std::{fs, path::Path};
const ADAPTER: u64 = 4096;

use backend::{step::*, *};
use mlx_expert_ranges::residency::*;

use sha2::{Digest, Sha256};
use std::cell::Cell;

fn setup() -> (String, StagedResidency) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/resident-expert-mlp")
        .canonicalize()
        .unwrap();
    let manifest: Value =
        serde_json::from_slice(&fs::read(root.join("manifest.json")).unwrap()).unwrap();
    let r = &manifest["recipes"]["default"];
    let req = ExpertRequest {
        expert: 0,
        experts: 3,
        d: 128,
        h: 64,
        bits: [4; 3],
        group_size: 64,
        modules: std::array::from_fn(|i| r["planes"][0][i]["module"].as_str().unwrap().into()),
    };
    let hashes: Vec<_> = (0..3)
        .map(|e| {
            std::array::from_fn(|i| {
                std::array::from_fn(|j| {
                    parse_hash(r["planes"][e][i]["sha256"][j].as_str().unwrap()).unwrap()
                })
            })
        })
        .collect();
    let source = BoundedSource::open(&root.join(r["name"].as_str().unwrap())).unwrap();
    let c = CopiedResidency::new(
        source,
        0,
        &req,
        ContentAuthority {
            checkpoint: r["name"].as_str().unwrap(),
            metadata: r["metadata"].as_str().unwrap(),
            content: parse_hash(r["content"].as_str().unwrap()).unwrap(),
            hashes: &hashes,
        },
        u64::MAX,
        0,
    )
    .unwrap();
    (
        r["content"].as_str().unwrap().into(),
        StagedResidency::new(c, Mode::Overlap, u64::MAX).unwrap(),
    )
}
fn error(code: &'static str) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidStateTransition,
        code,
        "synthetic host fixture",
    )
}
fn identity() -> CheckpointIdentity {
    CheckpointIdentity::try_new(
        "5d80254c9a88fdacf176189a7c1bdfabc98552c1440a435dbfbda82d2e65721c",
        "staged-default-v1",
    )
    .unwrap()
}
fn request() -> StepRequest {
    StepRequest {
        id: "fixture-step".into(),
        checkpoint: identity(),
        expected_position: 0,
        layers: vec![0],
        inputs: vec![RuntimeTensor {
            name: "activation".into(),
            shard: "fixture".into(),
            range: TensorRange {
                offset: 0,
                length: 1,
            },
            shape: vec![1],
            quantization: "u8".into(),
        }],
        scratch_bytes: 8,
        output_bytes: 32,
    }
}
struct Inputs(Cell<u64>);
impl TensorCatalog for Inputs {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok(request().inputs.into_iter().find(|t| t.name == name))
    }
}
impl HostTensorStore for Inputs {
    fn validate_range(&self, t: &RuntimeTensor) -> Result<(), ContractError> {
        if t == &request().inputs[0] {
            Ok(())
        } else {
            Err(error("range"))
        }
    }
}
impl TensorStore for Inputs {
    fn read_range(
        &self,
        _: &RuntimeTensor,
        out: &mut [u8],
        cancel: &CancellationToken,
    ) -> Result<usize, ContractError> {
        cancel.check()?;
        self.0.set(self.0.get() + 1);
        out.copy_from_slice(&[17]);
        Ok(1)
    }
}
struct PackedExecutor {
    cache: StagedResidency,
    staged: Option<(String, u8, [Demand; 6])>,
    output: Option<LayerOutput>,
    dispatches: usize,
    abort_during_consume: bool,
    fail_finish: bool,
}
impl HostLayerExecutor for PackedExecutor {
    fn working_bytes(&self) -> u64 {
        self.cache.working_bytes() + ADAPTER
    }
    fn stage(
        &mut self,
        r: &StepRequest,
        inputs: &[LoadedTensor],
        _: &mut [u8],
        _: &CancellationToken,
    ) -> Result<(), ContractError> {
        let need = std::mem::size_of::<[Demand; 6]>()
            + std::mem::size_of::<Sha256>()
            + std::mem::size_of::<LayerOutput>()
            + 2 * r.id.len()
            + 32
            + 512;
        if need as u64 > ADAPTER {
            return Err(error("workspace"));
        }
        assert_eq!(inputs.len(), 1);
        assert_eq!(inputs[0].descriptor.name, "activation");
        let keys = [0, 1, 0, 2, 1, 0].map(|e| self.cache.demand(e).unwrap());
        if r != &request() || inputs[0].bytes.len() != 1 {
            return Err(error("fixed_host_request"));
        }
        self.staged = Some((r.id.clone(), inputs[0].bytes[0], keys));
        Ok(())
    }
    fn take_output(&mut self, _: RuntimeBuffer) -> Result<LayerOutput, ContractError> {
        self.output.take().ok_or(error("no_output"))
    }
    fn finish(&mut self) -> Result<(), ContractError> {
        self.staged = None;
        self.output = None;
        if self.fail_finish {
            self.cache.quarantine();
            return Err(error("fixture_finish"));
        }
        self.cache.finish().map_err(|_| error("cache_finish"))
    }
}
impl LayerExecutor for PackedExecutor {
    fn execute_layer(
        &mut self,
        request: LayerRequest,
        token: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError> {
        self.dispatches += 1;
        let (id, activation, keys) = self.staged.as_ref().ok_or(error("missing_stage"))?;
        let mut h = Sha256::new();
        h.update([*activation]);
        let result = self.cache.consume(
            keys,
            || token.check().is_err(),
            |view| {
                for row in view.components {
                    for component in row {
                        h.update(component);
                    }
                }
                if self.abort_during_consume {
                    token.cancel();
                }
                Ok(())
            },
        );
        if result.is_err() {
            token.check()?;
            return Err(error("packed_cache"));
        }
        let bytes = h.finalize().to_vec();
        let buffer = RuntimeBuffer {
            slot_id: 0,
            byte_length: 32,
        };
        self.output = Some(LayerOutput {
            step_id: id.clone(),
            request,
            buffer,
            token: u32::from_le_bytes(bytes[..4].try_into().unwrap()),
            bytes,
        });
        Ok(buffer)
    }
}
fn host(
    cache: StagedResidency,
    budget: u64,
    abort: bool,
    fail_finish: bool,
) -> StepCoordinator<PackedExecutor> {
    StepCoordinator::new(
        identity(),
        MemoryBudget::try_new(budget + 128, 128, budget).unwrap(),
        GenerationState::default(),
        PackedExecutor {
            cache,
            staged: None,
            output: None,
            dispatches: 0,
            abort_during_consume: abort,
            fail_finish,
        },
    )
    .unwrap()
}
#[test]
fn staged_coordinator_commit_lost_delivery_and_replay() {
    let (content, cache) = setup();
    assert_eq!(identity().checkpoint_set_sha256, content);
    let w = cache.working_bytes() + ADAPTER;
    let mut host = host(cache, w + 45, false, false);
    let store = Inputs(Cell::new(0));
    let mut req = request();
    let cancel = CancellationToken::new();
    let result = host
        .execute(&req, &store, &store, &cancel, |_| Err(error("delivery")))
        .unwrap();
    assert_eq!(result.delivery_error.unwrap().code(), "delivery");
    assert_eq!(host.state().position(), 1);
    let stored = host.backend().cache.activity();
    assert_eq!(stored.spawned, stored.joined);
    assert_eq!(stored.attempted_reads, 36);
    assert_eq!(stored.copy_operations, 36);
    let mut expected = Sha256::new();
    expected.update([17]);
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/resident-expert-mlp");
    let m: Value = serde_json::from_slice(&fs::read(root.join("manifest.json")).unwrap()).unwrap();
    let r = &m["recipes"]["default"];
    let shard = fs::read(
        root.join(r["name"].as_str().unwrap())
            .join("model.safetensors"),
    )
    .unwrap();
    for expert in [0, 1, 0, 2, 1, 0] {
        for role in r["planes"][expert].as_array().unwrap() {
            for (c, part) in role["ranges"].as_array().unwrap().iter().enumerate() {
                let begin = part["begin"].as_u64().unwrap() as usize;
                let n = part["len"].as_u64().unwrap() as usize;
                let bytes = &shard[begin..begin + n];
                assert_eq!(format!("{:x}", Sha256::digest(bytes)), role["sha256"][c]);
                expected.update(bytes);
            }
        }
    }
    assert_eq!(&result.committed.bytes[..], &expected.finalize()[..]);
    assert_eq!(host.peak_reservation_bytes(), w + 45);
    assert_eq!(host.active_reservation_bytes(), 0);
    assert_eq!(host.backend().cache.cache().read_calls(), 36);
    let stats = host.backend().cache.cache().stats();
    let replay = host
        .execute(&req, &store, &store, &cancel, |_| Ok(()))
        .unwrap();
    assert!(replay.replayed);
    assert_eq!(host.backend().cache.activity(), stored);
    println!(
        "staged-coordinator replay=true position={} peak={} adapter={} activity={:?}",
        host.state().position(),
        host.peak_reservation_bytes(),
        ADAPTER,
        stored
    );
    assert!(std::sync::Arc::ptr_eq(&result.committed, &replay.committed));
    req.id = "changed".into();
    assert!(host
        .execute(&req, &store, &store, &cancel, |_| Ok(()))
        .is_err());
    assert_eq!(
        (
            host.state().position(),
            host.backend().dispatches,
            store.0.get()
        ),
        (1, 1, 1)
    );
    assert_eq!(host.backend().cache.cache().stats(), stats);
    assert_eq!(host.backend().cache.cache().read_calls(), 36);
    assert_eq!(host.backend().working_bytes(), w);
    assert!(host.backend().staged.is_none() && host.backend().output.is_none());
}
#[test]
fn staged_coordinator_short_budget_and_precancel() {
    let (_fixture, cache) = setup();
    let w = cache.working_bytes() + ADAPTER;
    let mut host = host(cache, w + 44, false, false);
    let io = Inputs(Cell::new(0));
    assert_eq!(
        host.execute(&request(), &io, &io, &CancellationToken::new(), |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "step_budget_exceeded"
    );
    assert_eq!(
        (
            io.0.get(),
            host.backend().cache.cache().read_calls(),
            host.backend().dispatches
        ),
        (0, 0, 0)
    );
    assert_eq!(host.state().position(), 0);
    assert_eq!(host.backend().cache.activity().spawned, 0);
    let c = CancellationToken::new();
    c.cancel();
    assert!(host.execute(&request(), &io, &io, &c, |_| Ok(())).is_err());
    assert_eq!(host.backend().cache.activity().spawned, 0);
    assert_eq!(io.0.get(), 0);
    println!("staged-coordinator short and precancel reads=0 workers=0 commits=0");
}
#[test]
fn staged_coordinator_cancellation_and_poisoned_finish() {
    for fail in [false, true] {
        let (_fixture, cache) = setup();
        let w = cache.working_bytes() + ADAPTER;
        let mut host = host(cache, w + 45, true, fail);
        let io = Inputs(Cell::new(0));
        let e = host
            .execute(
                &request(),
                &io,
                &io,
                &CancellationToken::new(),
                |_| panic!(),
            )
            .unwrap_err();
        assert_eq!(e.error.code(), {
            let cancelled = CancellationToken::new();
            cancelled.cancel();
            cancelled.check().unwrap_err().code()
        });
        assert_eq!(
            e.cleanup_error.map(|e| e.code()),
            if fail { Some("fixture_finish") } else { None }
        );
        assert_eq!(host.state().position(), 0);
        assert_eq!(host.active_reservation_bytes(), 0);
        let b = host.backend();
        assert_eq!(b.cache.cache().stats().consumed, 1);
        assert!((18..=27).contains(&b.cache.cache().read_calls()));
        let a = b.cache.activity();
        assert_eq!(a.joined, 1);
        assert!(a.banks_home && !a.outstanding);
        println!("staged-coordinator cancel fail_finish={fail} position=0 {a:?}");
        assert_eq!(b.working_bytes(), w);
        assert_eq!(b.cache.cache().is_quarantined(), fail);
        assert!(b.staged.is_none() && b.output.is_none());
        if fail {
            assert_eq!(
                host.execute(
                    &request(),
                    &io,
                    &io,
                    &CancellationToken::new(),
                    |_| panic!()
                )
                .unwrap_err()
                .error
                .code(),
                "backend_cleanup_required"
            );
        }
    }
}
