use super::*;
use serde_json::{json, Value};
use std::{fs, path::Path, sync::mpsc::channel, time::Duration};

fn cache(bad_hash: bool) -> CopiedResidency {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/resident-expert-mlp");
    let manifest: Value =
        serde_json::from_slice(&fs::read(root.join("manifest.json")).unwrap()).unwrap();
    let recipe = &manifest["recipes"]["default"];
    let mut hashes: Vec<TupleHashes> = (0..3)
        .map(|expert| {
            std::array::from_fn(|role| {
                std::array::from_fn(|part| {
                    parse_hash(
                        recipe["planes"][expert][role]["sha256"][part]
                            .as_str()
                            .unwrap(),
                    )
                    .unwrap()
                })
            })
        })
        .collect();
    if bad_hash {
        hashes[1][1][1][0] ^= 1;
    }
    let request = ExpertRequest {
        expert: 0,
        experts: 3,
        d: 128,
        h: 64,
        bits: [4; 3],
        group_size: 64,
        modules: std::array::from_fn(|i| recipe["planes"][0][i]["module"].as_str().unwrap().into()),
    };
    let name = recipe["name"].as_str().unwrap();
    CopiedResidency::new(
        BoundedSource::open(&root.join(name).canonicalize().unwrap()).unwrap(),
        0,
        &request,
        ContentAuthority {
            checkpoint: name,
            metadata: recipe["metadata"].as_str().unwrap(),
            content: parse_hash(recipe["content"].as_str().unwrap()).unwrap(),
            hashes: &hashes,
        },
        u64::MAX,
        0,
    )
    .unwrap()
}
fn stage(mode: Mode, bad_hash: bool, max: usize) -> StagedResidency {
    StagedResidency::with_policy_capacity(
        cache(bad_hash),
        mode,
        Policy::BufferedRequested,
        u64::MAX,
        max,
    )
    .unwrap()
}
fn home(stage: &StagedResidency) {
    let activity = stage.activity();
    assert!(activity.banks_home && !activity.outstanding);
    assert_eq!(activity.spawned, activity.joined);
    assert!(stage.expected.is_none() && stage.fixed.is_some());
    assert_eq!(
        stage.fixed.as_ref().unwrap().scratch.backing_bytes() as u64,
        stage.policy_ledger().unwrap().scratch_backing_bytes
    );
}
fn gate_bytes(stage: &StagedResidency) -> u64 {
    stage.ledger().component_capacities[0].iter().sum::<usize>() as u64
}

#[test]
fn fixed_resource_receipt_cap_and_new_attempt_observations() {
    let mut stage = stage(Mode::Serial, false, 1);
    let cost = stage.working_bytes();
    let l = stage.policy_ledger().unwrap();
    assert_eq!(l.role_capacity, 3);
    assert_eq!(
        l.receipt_bytes,
        3 * l.role_record_bytes as u64 + l.receipt_bookkeeping
    );
    assert_eq!(
        l.transport_bytes,
        l.scratch_backing_bytes + BASE_CONTROL + POLICY_CONTROL
    );
    assert_eq!(cost, stage.ledger().total + l.total);
    let short = cache(false);
    let source = Arc::clone(&short.source);
    assert!(matches!(
        StagedResidency::with_policy_capacity(short, Mode::Serial, Policy::BufferedRequested, cost - 1, 1),
        Err(e) if e.phase == "BUDGET"
    ));
    assert_eq!(source.payload_read_calls(), 0);
    StagedResidency::with_policy_capacity(
        cache(false),
        Mode::Serial,
        Policy::NoCacheRequested,
        cost,
        1,
    )
    .unwrap();
    let key = stage.demand(0).unwrap();
    stage.consume(&[key], || false, |_| Ok(())).unwrap();
    assert_eq!(stage.policy_records().len(), 3);
    assert_eq!(stage.policy_verified_discards(), (0, 0));
    let before = stage.activity();
    assert!(
        matches!(stage.consume(&[key,key], || false, |_| panic!()), Err(e) if e.primary.phase == "BUDGET")
    );
    assert!(stage.policy_records().is_empty());
    assert_eq!(stage.activity(), before);
    assert_eq!(
        stage
            .fixed
            .as_ref()
            .unwrap()
            .preflight(1, u64::MAX)
            .unwrap_err()
            .phase,
        "OVERFLOW"
    );
    stage.consume(&[key], || false, |_| Ok(())).unwrap();
    assert!(stage.policy_records().is_empty());
    assert_eq!(stage.activity().requested_bytes, before.requested_bytes);
    assert_eq!(stage.activity().copied_bytes, before.copied_bytes);
    home(&stage);
}

#[test]
fn fixed_partial_progress_after_later_hash_refusal_preserves_previous_resident() {
    for mode in [Mode::Serial, Mode::Overlap] {
        let mut stage = stage(mode, true, 3);
        let a = stage.demand(0).unwrap();
        let b = stage.demand(1).unwrap();
        stage.consume(&[a], || false, |_| Ok(())).unwrap();
        let prior = stage.cache().residents();
        let before = stage.activity();
        let failure = stage.consume(&[b], || false, |_| panic!()).unwrap_err();
        assert_eq!(failure.primary.phase, "CONTENT");
        assert!(failure.cleanup.is_none());
        let rows = stage.policy_records();
        assert_eq!(rows.len(), 2);
        assert!(rows[0].verified && !rows[1].verified);
        let observed = json!(&rows[1]);
        assert_eq!(observed["primary_phase"], "CONTENT");
        let receipt = &observed["outcome"]["receipt"];
        assert_eq!(receipt["logical_attempts"], 2);
        assert_eq!(receipt["attempted"], 2);
        assert!(receipt["completed"].as_u64().unwrap() > 0);
        assert_eq!(receipt["published"], false);
        assert_eq!(observed["outcome"]["retired_live"], 0);
        assert_eq!(
            observed["outcome"]["retired_released"],
            receipt["setup"]["live"]
        );
        assert_eq!(stage.cache().residents(), prior);
        assert_eq!(stage.activity().copy_operations, before.copy_operations);
        assert_eq!(stage.activity().verified_roles - before.verified_roles, 1);
        assert_eq!(stage.policy_verified_discards(), (1, gate_bytes(&stage)));
        assert_eq!(stage.activity().attempted_reads - before.attempted_reads, 5);
        assert_eq!(
            stage.activity().discarded_issued_bytes - before.discarded_issued_bytes,
            stage.activity().requested_bytes - before.requested_bytes
        );
        home(&stage);
        stage.finish().unwrap();
        assert!(stage.consume(&[b], || true, |_| panic!()).is_err());
        assert_eq!(stage.policy_verified_discards(), (0, 0));
    }
}

#[test]
fn fixed_refused_preparation_returns_its_observation_without_a_transfer() {
    let mut stage = stage(Mode::Serial, false, 1);
    let reader = stage.fixed.as_mut().unwrap();
    // Both alignments admit a window. Rust025 must refuse a non-runtime page before setup.
    reader.ledger.page_size = if reader.ledger.page_size == 4096 {
        16384
    } else {
        4096
    };
    let key = stage.demand(0).unwrap();
    let failure = stage.consume(&[key], || false, |_| panic!()).unwrap_err();
    assert_eq!(
        (failure.primary.phase, failure.primary.detail.as_str()),
        ("POLICY", "PAGE_ALIGNMENT")
    );
    let observed = json!(&stage.policy_records()[0]);
    assert_eq!(observed["outcome"]["kind"], "setup_failure");
    assert_eq!(observed["outcome"]["setup"]["live"], 0);
    assert_eq!(
        observed["outcome"]["setup"]["slots"],
        json!([null, null, null])
    );
    assert_eq!(stage.activity().attempted_reads, 0);
    assert_eq!(stage.cache().stats().fills, 0);
    home(&stage);
}

#[test]
fn fixed_cancel_and_worker_panic_retain_completed_role_and_recover_scratch() {
    for panic_reader in [false, true] {
        let mut stage = stage(Mode::Overlap, false, 1);
        let flag = Arc::new(AtomicBool::new(false));
        let signal = Arc::clone(&flag);
        stage.hook = Some(Arc::new(move |_, _, at| {
            if at == Point::Role(0) {
                if panic_reader {
                    panic!("injected after retired policy role")
                }
                signal.store(true, Ordering::Release);
            }
        }));
        let key = stage.demand(0).unwrap();
        let failure = stage
            .consume(&[key], || flag.load(Ordering::Acquire), |_| panic!())
            .unwrap_err();
        assert_eq!(
            failure.primary.phase,
            if panic_reader { "WORKER" } else { "CANCELLED" }
        );
        assert_eq!(stage.policy_records().len(), 1);
        assert!(stage.policy_records()[0].verified);
        assert_eq!(stage.activity().verified_roles, 1);
        assert_eq!(stage.policy_verified_discards(), (1, gate_bytes(&stage)));
        assert_eq!(stage.cache().stats().fills, 0);
        assert_eq!(stage.cache().is_quarantined(), panic_reader);
        home(&stage);
    }
}

#[test]
fn fixed_owner_failure_drains_distinct_speculative_error_and_keeps_its_work() {
    let mut stage = stage(Mode::Overlap, false, 3);
    let (sent, ready) = channel();
    stage.hook = Some(Arc::new(move |wave, _, point| {
        if wave == 1 && point == Point::Role(0) {
            sent.send(()).unwrap();
            panic!("injected future reader failure after verified role")
        }
    }));
    let keys = [0, 1, 2].map(|expert| stage.demand(expert).unwrap());
    let error = stage
        .consume(
            &keys,
            || false,
            |_| {
                ready.recv_timeout(Duration::from_secs(3)).unwrap();
                Err(refusal("CONSUMER", "foreground primary"))
            },
        )
        .unwrap_err();
    assert_eq!(error.primary.phase, "CONSUMER");
    assert_eq!(error.cleanup.unwrap().phase, "WORKER");
    assert_eq!(stage.policy_records().len(), 7);
    assert_eq!(stage.policy_records()[6].wave, 1);
    assert!(stage.policy_records()[6].verified);
    assert_eq!(stage.policy_verified_discards(), (1, gate_bytes(&stage)));
    assert!(stage.cache().is_quarantined());
    home(&stage);
}
