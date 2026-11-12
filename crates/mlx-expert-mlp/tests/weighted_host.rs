use backend::{
    step::{HostLayerExecutor, StepCoordinator},
    CancellationToken, ContractError, ErrorCategory,
};
use mlx_expert_mlp::{
    resident_fixture::{Arm, Population},
    resident_pipeline::*,
    weighted::*,
};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
    refusal::DeviceFacts,
};
use serde_json::{json, Value};
use std::{
    cell::RefCell,
    fs,
    io::Write,
    path::{Path, PathBuf},
    rc::Rc,
    sync::Arc,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}
fn fixture(name: &str) -> Value {
    let bytes = mlx_expert_mlp::resident_fixture::checked_file(
        &root().join("fixtures/weighted-expert-mlp").join(name),
        1 << 20,
    )
    .unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
fn tensor(words: impl IntoIterator<Item = u32>) -> HostTensor {
    let bytes: Vec<u8> = words.into_iter().flat_map(u32::to_le_bytes).collect();
    HostTensor {
        name: "controlled".into(),
        dtype: Dtype::F32,
        shape: vec![1, bytes.len() / 4],
        bytes,
    }
}
fn lanes(bytes: &[u8]) -> Vec<u32> {
    bytes
        .chunks_exact(4)
        .map(|b| u32::from_le_bytes(b.try_into().unwrap()))
        .collect()
}
fn export(name: &str, v: Value) {
    let Some(dir) = std::env::var_os("WEIGHTED_TEST_EXPORT") else {
        return;
    };
    let dir = Path::new(&dir);
    let b = serde_json::to_vec(&v).unwrap();
    let total: u64 = dir
        .read_dir()
        .unwrap()
        .map(|entry| entry.unwrap().metadata().unwrap().len())
        .sum();
    assert!(b.len() <= 8 << 20 && total + b.len() as u64 <= 8 << 20);
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(dir.join(format!("{name}.json")))
        .unwrap();
    f.write_all(&b).unwrap();
}
#[derive(Default, Clone, Debug, PartialEq, Eq)]
struct Events {
    events: Vec<&'static str>,
    projections: usize,
    activations: usize,
    imports: usize,
    retired: usize,
}
type Log = Rc<RefCell<Events>>;
struct Synthetic {
    log: Log,
    cancel: CancellationToken,
    mode: &'static str,
    recipe: Value,
    patterns: Value,
    expert: Option<usize>,
}
impl Synthetic {
    fn new(profile: &str, mode: &'static str) -> (Self, Log, CancellationToken) {
        let manifest: Value = serde_json::from_slice(include_bytes!(
            "../../../fixtures/resident-expert-mlp/manifest.json"
        ))
        .unwrap();
        let token = CancellationToken::new();
        let log = Log::default();
        (
            Self {
                log: log.clone(),
                cancel: token.clone(),
                mode,
                recipe: manifest["recipes"][profile].clone(),
                patterns: fixture("routes.json")["patterns"][profile].clone(),
                expert: None,
            },
            log,
            token,
        )
    }
}
impl Driver for Synthetic {
    fn begin(&mut self) -> StageResult<DeviceFacts> {
        self.expert = None;
        self.log.borrow_mut().events.push("begin");
        Ok(DeviceFacts::GPU)
    }
    fn projection(
        &mut self,
        role: usize,
        input: &HostTensor,
        parts: &[HostTensor; 3],
        bits: u32,
    ) -> StageResult<Projection> {
        let k = if role == 2 { 64 } else { 128 };
        let n = if role == 2 { 128 } else { 64 };
        assert_eq!(input.shape, [1, k]);
        assert_eq!(input.dtype, Dtype::F32);
        let hashes = parts.each_ref().map(|p| sha256_hex(&p.bytes));
        let matched: Vec<_> = (0..3)
            .filter(|&i| self.recipe["planes"][i][role]["sha256"] == json!(hashes))
            .collect();
        assert_eq!(matched.len(), 1);
        let e = matched[0];
        if role == 0 {
            self.expert = Some(e)
        }
        assert_eq!(self.expert, Some(e));
        assert_eq!(self.recipe["planes"][e][role]["bits"], bits);
        for (c, p) in parts.iter().enumerate() {
            assert_eq!(p.dtype, if c == 0 { Dtype::U32 } else { Dtype::BF16 });
            assert_eq!(
                p.shape,
                [
                    n,
                    if c == 0 {
                        k * bits as usize / 32
                    } else {
                        k / 64
                    }
                ]
            );
        }
        let mut log = self.log.borrow_mut();
        log.events.push(["gate", "up", "down"][role]);
        log.projections += 1;
        log.imports += 4;
        if self.mode == "panic" && role == 1 {
            panic!("controlled host callback unwind")
        }
        if matches!(self.mode, "partial" | "double") && role == 1 {
            return Err(Fault::clean("partial up projection"));
        }
        if self.mode == "second" && role == 1 && log.retired >= 2 {
            return Err(Fault::clean("second occurrence failed"));
        }
        if self.mode == "cancel" && role == 1 {
            self.cancel.cancel();
        }
        let output = if role == 2 {
            let pattern = self.patterns[e].as_array().unwrap();
            tensor((0..128).map(|i| pattern[i % pattern.len()].as_u64().unwrap() as u32))
        } else {
            tensor(vec![
                if self.mode == "gate_domain" {
                    17f32.to_bits()
                } else {
                    0
                };
                64
            ])
        };
        Ok(Projection {
            output,
            imports: 4,
            calls: 1,
            before_import: 0,
            before_call: 0,
            cpu_checks: 2,
            gpu: true,
            memory: [0; 3],
        })
    }
    fn activation(&mut self, _: &HostTensor, _: &HostTensor) -> StageResult<Activation> {
        let mut log = self.log.borrow_mut();
        log.activations += 1;
        log.events.push("activation");
        if self.mode == "activation" {
            return Err(Fault::clean("controlled activation failure"));
        }
        Ok(Activation {
            hidden: tensor(vec![u32::from(self.mode == "down_guard"); 64]),
            clamps: [[0; 64]; 2],
            stats: [2, 0, 9, 4, 13, 1, 9, 0],
            memory: [0; 3],
        })
    }
    fn retire(&mut self) -> StageResult<Retirement> {
        let mut log = self.log.borrow_mut();
        log.retired += 1;
        log.events.push("retire");
        if self.mode == "double" {
            return Err(Fault::uncertain("controlled retirement failure"));
        }
        Ok(Retirement {
            live: u64::from(self.mode == "retire"),
            freed: 1,
            double_free: 0,
            errors: 0,
            messages: 0,
            results: [1, 1, 0],
        })
    }
    fn finish(&mut self) -> StageResult<()> {
        self.log.borrow_mut().events.push("finish");
        if self.mode == "finish" {
            Err(Fault::uncertain("controlled finish failure"))
        } else {
            Ok(())
        }
    }
}
type Host = StepCoordinator<WeightedExecutor<Synthetic>>;
fn host(
    path: &Path,
    profile: &str,
    arm: Arm,
    mode: &'static str,
    cap: Option<u64>,
) -> (Host, InputStore, Log, CancellationToken) {
    let (d, l, t) = Synthetic::new(profile, mode);
    let (h, s) = setup(
        path,
        profile,
        RouteBook::fixed(profile).unwrap(),
        arm,
        d,
        cap,
    )
    .unwrap();
    (h, s, l, t)
}
fn records(h: &Host) -> Vec<Value> {
    h.backend().records().map(|(pos,(expert,weight),b)|json!({"position":pos,"expert":expert,"weight":weight,"row":serde_json::from_slice::<Value>(b).unwrap(),"bytes":b.len()})).collect()
}
const PEAK: [u64; 5] = [1028, 1544, 1548, 1552, 1556];
#[test]
fn weighted_five_positions_match_independent_lane_bits_and_replay() {
    let reference = fixture("expected.json");
    for profile in ["default", "mixed"] {
        for arm in [Arm::Cached, Arm::Allocating] {
            let (mut h, s, log, t) = host(&root(), profile, arm, "", None);
            let g = &reference["profiles"][profile];
            assert_eq!(h.backend().book().digest(), g["book"]);
            let w = h.backend().working_bytes();
            let ledger = h.backend().ledger().clone();
            assert_eq!(ledger["W_cache"].as_u64().unwrap() + HOST_BYTES + NATIVE, w);
            assert!(ledger["host_bound"].as_u64().unwrap() <= HOST_BYTES);
            let parts = ledger["parts"].as_array().unwrap();
            assert_eq!(
                parts.iter().map(|v| v[1].as_u64().unwrap()).sum::<u64>(),
                ledger["host_bound"].as_u64().unwrap()
            );
            assert_eq!(ledger["saved_payload_ceiling"], 393216);
            let mut seq = vec![];
            let mut replay = Value::Null;
            for pos in 0..5 {
                let book = h.backend().book();
                let req = book.request(pos).unwrap();
                assert_eq!(
                    book.plan_digest(pos).unwrap(),
                    reference["plan_sha256"][pos as usize]
                );
                assert!(
                    req.id.len() <= 256
                        && req.id.contains(book.digest())
                        && req.id.contains(book.plan_digest(pos).unwrap())
                );
                let result = h
                    .execute(&req, &s, &s, &t, |_| {
                        if pos == 0 {
                            Err(ContractError::new(
                                ErrorCategory::InvalidStateTransition,
                                "delivery",
                                "lost delivery",
                            ))
                        } else {
                            Ok(())
                        }
                    })
                    .unwrap();
                let i = pos as usize;
                let n = [1, 3, 6, 9, 12][i];
                assert_eq!(result.committed.bytes.len(), 512);
                assert_eq!(result.committed.token, 0);
                assert!(!result.replayed);
                assert_eq!(result.delivery_error.is_some(), pos == 0);
                let bits = lanes(&result.committed.bytes);
                assert_eq!(json!(bits), g["outputs"][i]["bits"]);
                let digest = sha256_hex(&result.committed.bytes);
                assert_eq!(digest, g["outputs"][i]["sha256"]);
                assert_eq!(h.state().position(), pos + 1);
                assert_eq!(s.reads(), pos + 1);
                assert_eq!(h.peak_reservation_bytes(), w + PEAK[i]);
                assert_eq!(h.active_reservations(), 0);
                assert_eq!(h.active_reservation_bytes(), 0);
                let snap = h.backend().snapshot();
                let observed = log.borrow().clone();
                assert_eq!(snap["weighted"], n);
                assert_eq!(snap["dispatches"], pos + 1);
                assert_eq!(snap["records"], n);
                assert_eq!(observed.retired, n);
                assert_eq!(observed.projections, 3 * n);
                assert_eq!(observed.activations, n);
                assert_eq!(observed.imports, 12 * n);
                for (key, c, a) in [
                    ("cache_reads", [9, 18, 27, 36, 54], [0; 5]),
                    ("control_reads", [0; 5], [9, 27, 54, 81, 108]),
                    ("fills", [1, 2, 3, 4, 6], [0; 5]),
                    ("hits", [0, 1, 3, 5, 6], [0; 5]),
                    ("evictions", [0, 0, 1, 2, 4], [0; 5]),
                ] {
                    assert_eq!(
                        snap[key],
                        if arm == Arm::Cached { c[i] } else { a[i] },
                        "{key} at {i}"
                    );
                }
                if pos == 0 {
                    let result2 = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap();
                    assert!(result2.replayed && Arc::ptr_eq(&result.committed, &result2.committed));
                    assert_eq!(h.state().position(), 1);
                    assert_eq!(s.reads(), 1);
                    assert_eq!(h.backend().snapshot(), snap);
                    assert_eq!(*log.borrow(), observed);
                    let mut conflict = req.clone();
                    conflict.scratch_bytes = 1;
                    assert_eq!(
                        h.execute(&conflict, &s, &s, &t, |_| Ok(()))
                            .unwrap_err()
                            .error
                            .code(),
                        "step_identity_mismatch"
                    );
                    assert_eq!(s.reads(), 1);
                    replay = json!({"same_arc":true,"position":1,"input_reads":1,"snapshot":snap,"events":observed.events});
                }
                seq.push(json!({"position":pos,"semantic_position":h.state().position(),"input_reads":s.reads(),"request_id":req.id,"bits":bits,"sha256":digest,
                "peak":h.peak_reservation_bytes(),"active":h.active_reservation_bytes(),"snapshot":snap,"synthetic_events":observed.events,
                "fake_imports":observed.imports,"fake_projections":observed.projections,"fake_activations":observed.activations,"retired":observed.retired}));
            }
            let rows = records(&h);
            let mut slots = std::collections::BTreeMap::new();
            for (entry, &(e, b)) in rows.iter().zip(FIXED.iter().flat_map(|p| p.iter())) {
                let r = &entry["row"];
                assert_eq!(r["expert"], e);
                assert_eq!(r["weight_bits"], b);
                assert_eq!(r["status"], "weighted_after_retirement");
                assert_eq!(r["component_sha256_before"], r["component_sha256_after"]);
                assert_eq!(r["cleanup"]["live"], 0);
                if arm == Arm::Cached {
                    slots.insert(r["slot_generation"][0].as_u64().unwrap(), e);
                }
            }
            if arm == Arm::Cached {
                let mut live: Vec<_> = slots.values().copied().collect();
                live.sort();
                assert_eq!(live, [1, 2]);
            }
            export(
                &format!("positive-{profile}-{}", arm.name()),
                json!({"boundary":"synthetic external Driver; host-only","ledger":ledger,"route_book":g["book"],"steps":seq,"replay":replay,"occurrences":rows,"final_cached_slots":slots}),
            );
        }
    }
}
#[test]
fn route_limits_identities_and_pre_read_refusals() {
    let pop = Population::load("default").unwrap();
    let base = Identity::for_population(&pop).unwrap();
    for plans in [
        &[][..],
        &[&[][..]],
        &[&[(3, 0x3f800000)]],
        &[&[(0, 0x3f000000)]],
        &[&[(0, 0), (0, 0), (0, 0), (0, 0x3f800000)]],
        &[FIXED[0]; 6],
        &[FIXED[2]; 5],
    ] {
        assert!(RouteBook::new(base.clone(), plans).is_err());
    }
    for bits in [
        0x80000000, 0x7fc00000, 0x7f800000, 0xbf800000, 1, 0x3dcccccd,
    ] {
        assert!(RouteBook::new(base.clone(), &[&[(0, bits)]]).is_err());
    }
    let expected = RouteBook::new(base.clone(), &FIXED).unwrap();
    for k in 0..7 {
        let mut id = base.clone();
        match k {
            0 => id.geometry[1] += 1,
            1 => id.input[2] ^= 4,
            2 => id.content[1] ^= 1,
            3 => id.profile = "mixed",
            4 => id.manifest[3] ^= 1,
            5 => id.bits[2] = 8,
            _ => id.geometry[5] = 1,
        }
        let other = RouteBook::new(id, &FIXED).unwrap();
        assert_ne!(other.digest(), expected.digest());
        let (driver, log, _) = Synthetic::new("default", "");
        let error = setup(
            Path::new("nonexistent"),
            "default",
            other,
            Arm::Cached,
            driver,
            None,
        )
        .err()
        .unwrap();
        assert!(error.contains("mismatch"));
        assert!(log.borrow().events.is_empty());
    }
    for changed in [
        &[(1, 0x3f400000), (0, 0x3e800000)][..],
        &[(0, 0x3e800000), (1, 0x3f400000)],
        &[(2, 0x3f400000), (1, 0x3e800000)],
    ] {
        let mut order = FIXED;
        order[1] = changed;
        let other = RouteBook::new(base.clone(), &order).unwrap();
        assert_ne!(other.digest(), expected.digest());
        assert_ne!(
            other.request(0).unwrap().id,
            expected.request(0).unwrap().id
        );
    }
    let (mut h, s, log, t) = host(&root(), "default", Arm::Cached, "", None);
    let other = RouteBook::fixed("mixed").unwrap().request(0).unwrap();
    assert!(h.execute(&other, &s, &s, &t, |_| Ok(())).is_err());
    assert_eq!(s.reads(), 0);
    assert!(log.borrow().events.is_empty());
    let mut req = h.backend().book().request(0).unwrap();
    req.id.push_str(".crossed");
    assert_eq!(
        h.execute(&req, &s, &s, &t, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "stage"
    );
    assert_eq!(s.reads(), 1);
    assert_eq!(h.backend().snapshot()["cache_reads"], 0);
    assert_eq!(log.borrow().projections, 0);
}
#[test]
fn ordered_binary32_combiner_edges_and_invalid_vectors() {
    fn run(pairs: &[(u32, u32)]) -> std::result::Result<u32, String> {
        let mut acc = WeightedSum::default();
        for &(w, x) in pairs {
            acc = acc.add(w, &tensor(vec![x; 128]))?;
        }
        Ok(lanes(&acc.into_bytes())[0])
    }
    let q = 0x3e800000;
    let h = 0x3f000000;
    let one = 0x3f800000;
    let a = (q, 0x4c800000);
    let b = (q, 0xcc800000);
    let c = (h, 0x3f000000);
    assert_eq!(run(&[a, b, c]).unwrap(), q);
    assert_eq!(run(&[a, c, b]).unwrap(), 0);
    assert_eq!(
        run(&[(q, 0xc0400000), (0x3f400000, 0x3f800001)]).unwrap(),
        0x34000000
    );
    for (pairs, expected) in [
        (vec![(one, 0x3f800000), (one, 0x33800000)], 0x3f800000),
        (vec![(one, 0x3f800001), (one, 0x33800000)], 0x3f800002),
        (vec![(one, 0x007fffff), (one, 1)], 0x00800000),
        (vec![(one, 0x00800000), (one, 0x80000001)], 0x007fffff),
        (vec![(h, 1)], 0),
        (vec![(h, 3)], 2),
        (vec![(0, 0xbf800000)], 0),
        (vec![(one, 0x7f7fffff)], 0x7f7fffff),
    ] {
        assert_eq!(run(&pairs).unwrap(), expected);
    }
    for pairs in [
        vec![(one, 0x7f7fffff); 2],
        vec![(0, 0x7fc00000)],
        vec![(one, 0xff800000)],
        vec![(0x80000000, 0)],
    ] {
        assert!(run(&pairs).is_err());
    }
    for k in 0..3 {
        let mut v = tensor(vec![0; 128]);
        match k {
            0 => v.dtype = Dtype::U32,
            1 => v.shape = vec![128],
            _ => {
                v.bytes.pop();
            }
        }
        assert!(WeightedSum::default().add(one, &v).is_err());
    }
}
#[test]
fn budget_one_byte_short_at_each_position_before_next_read() {
    let mut evidence = vec![];
    for arm in [Arm::Cached, Arm::Allocating] {
        let w = host(&root(), "mixed", arm, "", None)
            .0
            .backend()
            .working_bytes();
        for (i, extra) in PEAK.into_iter().enumerate() {
            let (mut h, s, log, t) = host(&root(), "mixed", arm, "", Some(w + extra - 1));
            for p in 0..i {
                let req = h.backend().book().request(p as u64).unwrap();
                h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap();
            }
            let req = h.backend().book().request(i as u64).unwrap();
            let snap = h.backend().snapshot();
            let before = log.borrow().clone();
            let failure = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap_err();
            assert_eq!(s.reads(), i as u64);
            assert_eq!(h.state().position(), i as u64);
            assert_eq!(snap, h.backend().snapshot());
            assert_eq!(*log.borrow(), before);
            assert_eq!(h.active_reservation_bytes(), 0);
            evidence.push(json!({"arm":arm.name(),"position":i,"capacity":w+extra-1,"standing":w,"prior_snapshot":snap,"failure":failure.error.code(),"input_reads":s.reads()}));
        }
    }
    export("capacity", json!(evidence));
}
#[test]
fn failures_release_or_quarantine_without_partial_commit() {
    let mut evidence = vec![];
    for arm in [Arm::Allocating, Arm::Cached] {
        for mode in [
            "partial",
            "gate_domain",
            "activation",
            "down_guard",
            "cancel",
            "retire",
            "finish",
            "double",
            "panic",
            "second",
        ] {
            let (mut h, s, log, t) = host(&root(), "mixed", arm, mode, None);
            let mut pos = 0;
            if mode == "second" {
                let req = h.backend().book().request(0).unwrap();
                h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap();
                pos = 1;
            }
            let before = h.retained().cloned();
            let req = h.backend().book().request(pos).unwrap();
            let failure = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap_err();
            assert_eq!(h.state().position(), pos);
            assert_eq!(s.reads(), pos + 1);
            assert_eq!(h.active_reservation_bytes(), 0);
            if let Some(previous) = before {
                assert!(Arc::ptr_eq(&previous, h.retained().unwrap()))
            } else {
                assert!(h.retained().is_none())
            }
            let snap = h.backend().snapshot();
            assert_eq!(snap["pending"], false);
            assert_eq!(snap["output"], false);
            let uncertain = matches!(mode, "retire" | "finish" | "double" | "panic");
            assert_eq!(snap["quarantined"], uncertain);
            assert_eq!(snap["working_bytes"], h.backend().working_bytes());
            assert_eq!(log.borrow().retired, if mode == "second" { 3 } else { 1 });
            if mode == "second" {
                assert_eq!(snap["weighted"], 2);
            }
            if mode == "double" {
                assert!(failure.error.message().contains("partial up"));
                assert!(failure
                    .cleanup_error
                    .as_ref()
                    .unwrap()
                    .message()
                    .contains("retirement failure"));
            }
            let original = log.borrow().clone();
            if uncertain {
                assert!(h.execute(&req, &s, &s, &t, |_| Ok(())).is_err());
                assert_eq!(*log.borrow(), original);
            }
            evidence.push(json!({"mode":mode,"arm":arm.name(),"input_reads_at_failure":pos+1,"input_reads_after_reuse_control":s.reads(),"snapshot":snap,"records":records(&h),
            "events":original.events,"error":failure.to_string(),"state":h.state().position(),"active":h.active_reservations()}));
        }
    }
    export("faults", json!(evidence));
}
#[test]
fn cumulative_failed_records_stop_further_expert_work() {
    let (mut h, s, log, t) = host(&root(), "default", Arm::Cached, "partial", None);
    let req = h.backend().book().request(0).unwrap();
    for _ in 0..12 {
        assert!(h.execute(&req, &s, &s, &t, |_| Ok(())).is_err());
    }
    let snap = h.backend().snapshot();
    assert_eq!(snap["records"], 12);
    assert_eq!(snap["dispatches"], 12);
    assert_eq!(
        h.execute(&req, &s, &s, &t, |_| Ok(()))
            .unwrap_err()
            .error
            .code(),
        "quota"
    );
    assert_eq!(snap, h.backend().snapshot());
    assert_eq!(log.borrow().retired, 12);
    assert_eq!(s.reads(), 13);
    assert_eq!(h.state().position(), 0);
    export(
        "exhausted",
        json!({"snapshot":snap,"inputs_after_stage_refusal":s.reads(),"rows":records(&h)}),
    );
}
#[test]
fn corrupted_source_never_supplies_an_occurrence() {
    use std::io::{Read, Seek, SeekFrom};
    let mut evidence = vec![];
    for arm in [Arm::Cached, Arm::Allocating] {
        let tmp = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "weighted-source-{}-{}",
            std::process::id(),
            arm.name()
        ));
        fs::create_dir(&tmp).unwrap();
        let p = Population::load("default").unwrap();
        let rel = Path::new("fixtures/resident-expert-mlp").join(&p.name);
        fs::create_dir_all(tmp.join(&rel)).unwrap();
        for n in [
            "config.json",
            "model.safetensors.index.json",
            "model.safetensors",
        ] {
            fs::copy(root().join(&rel).join(n), tmp.join(&rel).join(n)).unwrap();
        }
        let input = p.input(&tmp, 0);
        fs::create_dir_all(input.parent().unwrap()).unwrap();
        fs::copy(p.input(&root(), 0), &input).unwrap();
        let off = p.ranges[0][0][0][0];
        let mut f = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(tmp.join(&rel).join("model.safetensors"))
            .unwrap();
        f.seek(SeekFrom::Start(off)).unwrap();
        let mut byte = [0];
        f.read_exact(&mut byte).unwrap();
        byte[0] ^= 1;
        f.seek(SeekFrom::Start(off)).unwrap();
        f.write_all(&byte).unwrap();
        drop(f);
        let (mut h, s, log, t) = host(&tmp, "default", arm, "", None);
        let req = h.backend().book().request(0).unwrap();
        let fail = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap_err();
        let snap = h.backend().snapshot();
        assert_eq!(h.state().position(), 0);
        assert_eq!(snap["weighted"], 0);
        assert_eq!(snap["fills"], 0);
        assert_eq!(snap["occupied"], 0);
        assert_eq!(log.borrow().projections, 0);
        assert_eq!(h.active_reservations(), 0);
        evidence.push(json!({"arm":arm.name(),"error":fail.error.code(),"snapshot":snap,"rows":records(&h),"inputs":s.reads()}));
        drop(h);
        fs::remove_dir_all(tmp).unwrap();
    }
    export("corrupt-fill", json!(evidence));
}
