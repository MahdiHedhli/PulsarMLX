use super::*;
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
    time::Duration,
};

// The external host-test supervisor recognizes these markers. It alone applies
// the five-second observation deadline and owns termination/reaping.
struct CleanupObservation;
impl CleanupObservation {
    fn start() -> Self {
        eprintln!("M4B_CLEANUP_BEGIN");
        Self
    }
}
impl Drop for CleanupObservation {
    fn drop(&mut self) {
        eprintln!("M4B_CLEANUP_END");
    }
}
fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}
fn cache(root: &Path) -> CopiedResidency {
    let raw = fs::read(repo().join("fixtures/resident-expert-mlp/manifest.json")).unwrap();
    let manifest: Value = serde_json::from_slice(&raw).unwrap();
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
    CopiedResidency::new(
        BoundedSource::open(root).unwrap(),
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
    .unwrap()
}
fn fixture() -> PathBuf {
    repo().join("fixtures/resident-expert-mlp/d128-h64-default")
}
fn stage(mode: Mode) -> StagedResidency {
    StagedResidency::new(cache(&fixture()), mode, u64::MAX).unwrap()
}
fn keys<const N: usize>(s: &StagedResidency, ids: [u32; N]) -> [Demand; N] {
    ids.map(|i| s.demand(i).unwrap())
}
fn drained(s: &StagedResidency) {
    let a = s.activity();
    assert_eq!(a.spawned, a.joined);
    assert!(a.banks_home && !a.outstanding && s.expected.is_none());
}

#[test]
fn staged_reader_and_foreground_happens_before() {
    use std::sync::mpsc::channel;
    for mode in [Mode::Serial, Mode::Overlap] {
        let mut s = stage(mode);
        let (start, await_start) = channel();
        let (done, await_done) = channel();
        let await_start = Mutex::new(await_start);
        let exited = Arc::new(AtomicBool::new(false));
        let marker = exited.clone();
        s.hook = Some(Arc::new(move |wave, _, point| {
            if wave != 1 {
                return;
            }
            if point == Point::Before {
                await_start
                    .lock()
                    .unwrap()
                    .recv_timeout(Duration::from_secs(3))
                    .unwrap();
                assert_eq!(marker.load(Ordering::Acquire), mode == Mode::Serial);
            }
            if point == Point::Role(0) {
                done.send(thread::current().id()).unwrap();
            }
        }));
        let owner = thread::current().id();
        let calls = std::rc::Rc::new(std::cell::Cell::new(0));
        let mut observed = None;
        let d = keys(&s, [0, 1, 2]);
        s.consume(
            &d,
            || false,
            |_| {
                assert_eq!(owner, thread::current().id());
                let n = calls.get() + 1;
                calls.set(n);
                if n == 1 && mode == Mode::Overlap {
                    start.send(()).unwrap();
                    observed = Some(await_done.recv_timeout(Duration::from_secs(3)).unwrap());
                }
                if n == 2 {
                    exited.store(true, Ordering::Release);
                    if mode == Mode::Serial {
                        start.send(()).unwrap();
                    }
                }
                Ok(())
            },
        )
        .unwrap();
        let reader =
            observed.unwrap_or_else(|| await_done.recv_timeout(Duration::from_secs(3)).unwrap());
        assert_ne!(owner, reader);
        assert_eq!(s.reader_thread(), Some(reader));
        assert_eq!(calls.get(), 3);
        drained(&s);
        println!("staged-order {mode:?} owner={owner:?} reader={reader:?} first_future_role_while_callback={} {:?}",mode==Mode::Overlap,s.activity());
    }
}
#[test]
fn staged_cancellation_releases_banks_and_discards_observed_reads() {
    for phase in ["before", "between", "verified"] {
        let mut s = stage(Mode::Overlap);
        let flag = Arc::new(AtomicBool::new(phase == "before"));
        let setter = flag.clone();
        s.hook = Some(Arc::new(move |_, bank, p| {
            if (phase == "between" && p == Point::Role(0))
                || (phase == "verified" && bank == 1 && p == Point::Verified)
            {
                setter.store(true, Ordering::Release)
            }
        }));
        let d = keys(&s, [0, 1]);
        let _cleanup = CleanupObservation::start();
        let e = s
            .consume(
                &d,
                || flag.load(Ordering::Acquire),
                |_| panic!("cancelled consumption"),
            )
            .unwrap_err();
        assert_eq!(e.primary.phase, "CANCELLED");
        assert!(e.cleanup.is_none());
        assert_eq!(s.cache.stats().fills, 0);
        let a = s.activity();
        assert_eq!(
            a.attempted_reads,
            match phase {
                "before" => 0,
                "between" => 3,
                _ => 18,
            }
        );
        assert_eq!(a.discarded_issued_bytes, a.requested_bytes);
        assert_eq!(a.verified_components, a.attempted_reads);
        assert_eq!(a.cancelled_jobs, u64::from(phase == "between"));
        assert_eq!(a.spawned, u64::from(phase != "before"));
        assert_eq!(a.copied_bytes, 0);
        drained(&s);
        s.finish().unwrap();
        println!("staged-cancel {phase} {a:?}");
    }
}
#[test]
fn staged_partial_tuple_hash_and_source_stamp_keep_previous_resident() {
    use std::os::unix::fs::FileExt;
    for mode in [Mode::Serial, Mode::Overlap] {
        for cause in ["hash", "stamp"] {
            let tmp = std::env::temp_dir()
                .canonicalize()
                .unwrap()
                .join(format!("stage-{mode:?}-{cause}-{}", std::process::id()));
            fs::create_dir(&tmp).unwrap();
            let root = tmp.join("d128-h64-default");
            fs::create_dir(&root).unwrap();
            for n in [
                "config.json",
                "model.safetensors.index.json",
                "model.safetensors",
            ] {
                fs::copy(fixture().join(n), root.join(n)).unwrap();
            }
            let manifest: Value = serde_json::from_slice(
                &fs::read(repo().join("fixtures/resident-expert-mlp/manifest.json")).unwrap(),
            )
            .unwrap();
            let offset = manifest["recipes"]["default"]["planes"][2][1]["ranges"][0]["begin"]
                .as_u64()
                .unwrap();
            let shard = root.join("model.safetensors");
            if cause == "hash" {
                let f = fs::OpenOptions::new()
                    .read(true)
                    .write(true)
                    .open(&shard)
                    .unwrap();
                let mut b = [0];
                f.read_exact_at(&mut b, offset).unwrap();
                b[0] ^= 1;
                f.write_all_at(&b, offset).unwrap();
            }
            let mut s = StagedResidency::new(cache(&root), mode, u64::MAX).unwrap();
            s.consume(&keys(&s, [0]), || false, |_| Ok(())).unwrap();
            let old = s.cache.residents();
            let before = s.activity();
            if cause == "stamp" {
                let path = root.join("config.json");
                s.hook = Some(Arc::new(move |_, b, p| {
                    if b == 1 && p == Point::Role(0) {
                        let f = fs::OpenOptions::new().write(true).open(&path).unwrap();
                        f.write_all_at(b" ", 0).unwrap();
                    }
                }));
            }
            let error = s
                .consume(&keys(&s, [1, 2]), || false, |_| panic!("partial publish"))
                .unwrap_err();
            let a = s.activity();
            assert_eq!(a.copy_operations, before.copy_operations);
            assert_eq!(s.cache.residents(), old);
            assert_eq!(s.cache.stats().fills, 1);
            assert_eq!(
                a.attempted_reads - before.attempted_reads,
                if cause == "hash" { 13 } else { 12 }
            );
            assert_eq!(a.verified_roles - before.verified_roles, 4);
            assert!(a.discarded_issued_bytes > 0);
            drained(&s);
            s.finish().unwrap();
            println!(
                "staged-fault {mode:?} {cause} phase={} {a:?}",
                error.primary.phase
            );
            drop(s);
            fs::remove_dir_all(tmp).unwrap();
        }
    }
}
#[test]
fn staged_panic_refusal_and_secondary_failure_join_before_return() {
    for action in ["owner_panic", "worker_panic", "both", "refusal"] {
        let mut s = stage(Mode::Overlap);
        // Make future failure deterministic while a foreground error remains primary.
        let (tx, rx) = std::sync::mpsc::channel();
        s.hook = Some(Arc::new(move |w, _, p| {
            if p == Point::Before
                && ((action == "both" && w == 1) || (action == "worker_panic" && w == 0))
            {
                tx.send(()).unwrap();
                panic!("synthetic worker panic")
            }
        }));
        let keys = keys(&s, [0, 1, 2]);
        let _cleanup = CleanupObservation::start();
        let r = catch_unwind(AssertUnwindSafe(|| {
            s.consume(
                &keys,
                || false,
                |_| {
                    if action == "owner_panic" {
                        panic!("synthetic foreground panic")
                    }
                    if action == "both" {
                        rx.recv_timeout(Duration::from_secs(3)).unwrap();
                    }
                    Err(refusal("CONSUMER", "synthetic refusal"))
                },
            )
        }));
        drained(&s);
        assert_eq!(s.cache.is_quarantined(), action != "refusal");
        assert_eq!(s.activity.spawned, 1);
        if action == "owner_panic" {
            assert!(r.is_err())
        } else {
            let e = r.unwrap().unwrap_err();
            assert_eq!(
                e.primary.phase,
                if action == "worker_panic" {
                    "WORKER"
                } else {
                    "CONSUMER"
                }
            );
            if action == "both" {
                assert_eq!(e.cleanup.unwrap().phase, "WORKER");
            }
        }
        if s.cache.is_quarantined() {
            assert!(s.consume(&keys, || false, |_| Ok(())).is_err());
            assert_eq!(s.activity.spawned, 1);
        }
        println!("staged-unwind {action} {:?}", s.activity());
    }
}
#[test]
fn staged_completion_identity_duplicate_and_queue_refusals() {
    for mutation in 0..11 {
        let mut s = stage(Mode::Serial);
        let k = keys(&s, [0, 1]);
        let (tx, rx) = sync_channel(1);
        s.submit(k.map(Some), 0, &tx).unwrap();
        assert!(s.submit(k.map(Some), 0, &tx).is_err());
        let mut job = rx.recv().unwrap();
        let a = job.tickets[0].as_mut().unwrap();
        match mutation {
            0 => a.owner += 1,
            1 => a.invocation += 1,
            2 => a.epoch += 1,
            3 => a.wave += 1,
            4 => a.bank = 1,
            5 => a.generation += 1,
            6 => a.content[0] ^= 1,
            7 => a.demand.binding[0] ^= 1,
            8 => a.hashes[0][0][0] ^= 1,
            9 => a.lengths[1][0] += 1,
            _ => job.tickets.swap(0, 1),
        }
        let (ret, done) = sync_channel(1);
        ret.send(Completion {
            job,
            error: None,
            panicked: false,
            cancelled: false,
            verified_roles: 0,
            verified_bytes: 0,
        })
        .unwrap();
        assert!(s.receive(&done).is_err());
        assert!(s.cache.is_quarantined());
        assert!(s.receive(&done).is_err());
        assert_eq!(s.cache.stats().fills, 0);
        assert_eq!(s.cache.read_calls(), 0);
    }
    let mut s = stage(Mode::Serial);
    let k = keys(&s, [0]);
    let (tx, rx) = sync_channel(1);
    let owned = s.banks.take().unwrap();
    tx.try_send(Job {
        tickets: [None, None],
        banks: owned,
    })
    .ok()
    .expect("occupy the sole queue slot");
    // A second isolated wrapper supplies the candidate banks for this full-queue injection.
    let other = stage(Mode::Serial);
    s.banks = other.banks;
    assert!(s.submit([Some(k[0]), None], 0, &tx).is_err());
    assert!(s.banks.is_some() && s.expected.is_none());
    assert_eq!(s.activity.requests, 0);
    drop(rx.recv().unwrap());
}
#[test]
fn staged_preflight_budget_epochs_and_counter_exhaustion() {
    let c = cache(&fixture());
    let w = c.working_bytes();
    let size = c.ledger().tuple_bytes;
    let src = c.source.clone();
    let exact = total_charge(w, size).unwrap();
    assert!(total_charge(u64::MAX, size).is_err());
    assert!(total_charge(w, u64::MAX).is_err());
    assert!(StagedResidency::new(c, Mode::Overlap, exact - 1).is_err());
    assert_eq!(src.payload_read_calls(), 0);
    for index in 0..8 {
        let mut s = stage(Mode::Serial);
        let k = keys(&s, [0]);
        match index {
            0 => s.invocation = u64::MAX,
            1 => s.epoch = u64::MAX - 1,
            2 => s.generations[0] = u64::MAX,
            3 => s.cache.slots[1].generation = u64::MAX,
            4 => s.activity.copied_bytes = u64::MAX,
            5 => s.activity.requests = u64::MAX,
            6 => s.activity.verified_bytes = u64::MAX,
            _ => s.activity.discarded_issued_bytes = u64::MAX,
        }
        assert_eq!(
            s.consume(&k, || false, |_| Ok(()))
                .unwrap_err()
                .primary
                .phase,
            "OVERFLOW"
        );
        assert_eq!(s.activity.spawned, 0);
        assert_eq!(s.cache.read_calls(), 0);
    }
    let mut s = stage(Mode::Overlap);
    let a = s.demand(0).unwrap();
    for bad in [
        vec![],
        vec![a; 65],
        vec![Demand {
            binding: [0; 32],
            ..a
        }],
    ] {
        assert!(s.consume(&bad, || false, |_| Ok(())).is_err());
        assert_eq!(s.activity.spawned, 0);
        assert_eq!(s.cache.read_calls(), 0);
    }
}

#[test]
fn staged_future_error_preserves_foreground_order_and_primary() {
    for mode in [Mode::Serial, Mode::Overlap] {
        let mut s = stage(mode);
        let d = keys(&s, [0, 1, 2]);
        let callbacks = std::cell::Cell::new(0);
        s.hook = Some(Arc::new(|wave, _, p| {
            if wave == 1 && p == Point::Before {
                panic!("injected future reader failure")
            }
        }));
        let _cleanup = CleanupObservation::start();
        let e = s
            .consume(
                &d,
                || false,
                |v| {
                    assert_eq!(v.demand.key.expert, callbacks.get());
                    callbacks.set(callbacks.get() + 1);
                    Ok(())
                },
            )
            .unwrap_err();
        assert_eq!(e.primary.phase, "WORKER");
        assert_eq!(callbacks.get(), 2);
        assert_eq!(s.cache.stats().consumed, 2);
        assert_eq!(s.activity.attempted_reads, 18);
        assert!(s.cache.is_quarantined());
        drained(&s);
        println!(
            "staged-future {mode:?} foreground=2 failure={} {:?}",
            e.primary.phase,
            s.activity()
        );
    }
}
