use super::*;
use crate::test_support::fixture;

fn cache() -> CopiedResidency {
    let f = fixture(128, 64, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let meta = source.metadata_snapshot().to_owned();
    let hashes = vec![[[[0; 32]; 3]; 3]; 3];
    CopiedResidency::new(
        source,
        7,
        &f.request,
        ContentAuthority {
            checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
            metadata: &meta,
            content: [8; 32],
            hashes: &hashes,
        },
        u64::MAX,
        0,
    )
    .unwrap()
}
#[test]
fn tickets_bind_slot_identity_and_generation_and_block_active_reuse() {
    let mut cache = cache();
    for i in 0..2 {
        let t = Ticket {
            owner: cache.owner,
            lease_epoch: 0,
            demand: cache.demand(i as u32).unwrap(),
            slot: i,
            generation: 3,
        };
        cache.slots[i].state = State::Filling(t);
        cache.publish(t).unwrap();
        assert!(cache.publish(t).is_err());
        let lease = cache.acquire(t).unwrap();
        assert!(cache
            .release(Ticket {
                owner: lease.owner + 1,
                ..lease
            })
            .is_err());
        assert!(cache.acquire(t).is_err());
        assert!(cache.table.evict(t.demand.key).is_err());
        assert!(cache.release(Ticket { generation: 2, ..t }).is_err());
    }
    assert!(cache.victim().is_err());
    let State::Leased(t) = cache.slots[0].state else {
        panic!()
    };
    cache.release(t).unwrap();
    assert!(cache.release(t).is_err());
    let next = cache.acquire(t).unwrap();
    assert!(cache.release(t).is_err());
    cache.release(next).unwrap();
    assert_eq!(cache.victim().unwrap(), 0);
    let w = cache.working_bytes();
    assert!(cache.finish().is_err());
    assert!(cache.is_quarantined());
    assert_eq!(cache.working_bytes(), w);
}
#[test]
fn exhaustion_refuses_before_eviction_or_reads() {
    let f = fixture(128, 64, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let meta = source.metadata_snapshot().to_owned();
    let mut cache = CopiedResidency::new(
        source,
        7,
        &f.request,
        ContentAuthority {
            checkpoint: f.root.file_name().unwrap().to_str().unwrap(),
            metadata: &meta,
            content: [8; 32],
            hashes: &vec![[[[0; 32]; 3]; 3]; 3],
        },
        u64::MAX,
        0,
    )
    .unwrap();
    let a = cache.demand(0).unwrap();
    cache.slots[0].generation = u64::MAX;
    assert_eq!(
        cache
            .consume(&[a], || false, |_| panic!())
            .unwrap_err()
            .primary
            .phase,
        "OVERFLOW"
    );
    cache.stats.consumed = u64::MAX;
    assert_eq!(
        cache
            .consume(&[a], || false, |_| panic!())
            .unwrap_err()
            .primary
            .phase,
        "OVERFLOW"
    );
    assert_eq!(cache.read_calls(), 0);
}

#[test]
fn cleanup_uncertainty_keeps_both_errors_and_charge() {
    let mut cache = cache();
    let invalid = Ticket {
        owner: cache.owner,
        lease_epoch: 1,
        slot: 0,
        generation: 1,
        demand: cache.demand(0).unwrap(),
    };
    let before = cache.working_bytes();
    let failure = cache
        .end_wave(Err(refusal("CONSUMER", "injected")), [Some(invalid), None])
        .unwrap_err();
    assert_eq!(failure.primary.phase, "CONSUMER");
    assert_eq!(failure.cleanup.unwrap().phase, "LEASE");
    assert!(cache.is_quarantined());
    assert_eq!(cache.working_bytes(), before);
}

#[test]
fn standing_charge_checks_metadata_ceiling_and_overflow_before_allocation() {
    let exact = 2 + METADATA_LIMIT + CONTROL_BYTES + WORKSPACE_BYTES;
    assert_eq!(standing_charge(1, METADATA_LIMIT, exact).unwrap(), exact);
    assert_eq!(
        standing_charge(1, METADATA_LIMIT + 1, u64::MAX)
            .unwrap_err()
            .phase,
        "BUDGET"
    );
    assert_eq!(
        standing_charge(u64::MAX, 0, u64::MAX).unwrap_err().phase,
        "OVERFLOW"
    );
    assert_eq!(
        standing_charge(1, METADATA_LIMIT, exact - 1)
            .unwrap_err()
            .phase,
        "BUDGET"
    );
}
