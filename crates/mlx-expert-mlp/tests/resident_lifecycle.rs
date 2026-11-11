#[path = "../src/resident_verifier.rs"]
mod verifier;
use backend::{step::HostLayerExecutor, CancellationToken};
use mlx_expert_mlp::{resident::*, resident_fixture::*, resident_pipeline::*};
use mlx_native_affine::{dtype::Dtype, fixture::HostTensor, refusal::DeviceFacts};
use std::{
    cell::RefCell,
    path::{Path, PathBuf},
    rc::Rc,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}
fn tensor(n: usize, value: f32) -> HostTensor {
    HostTensor {
        name: "stub".into(),
        dtype: Dtype::F32,
        shape: vec![1, n],
        bytes: (0..n).flat_map(|_| value.to_le_bytes()).collect(),
    }
}
struct Fake {
    fault: &'static str,
    events: Rc<RefCell<Vec<&'static str>>>,
    token: CancellationToken,
}
impl Fake {
    fn at(&self, name: &'static str) -> StageResult<()> {
        self.events.borrow_mut().push(name);
        if self.fault == name {
            return Err(Fault::uncertain(name));
        }
        Ok(())
    }
}
impl Driver for Fake {
    fn begin(&mut self) -> StageResult<DeviceFacts> {
        self.at("begin")?;
        Ok(DeviceFacts::GPU)
    }
    fn projection(
        &mut self,
        i: usize,
        x: &HostTensor,
        p: &[HostTensor; 3],
        bits: u32,
    ) -> StageResult<Projection> {
        assert_eq!(x.shape, [1, if i == 2 { 64 } else { 128 }]);
        assert_eq!(p[0].dtype, Dtype::U32);
        assert_eq!(p[1].dtype, Dtype::BF16);
        assert_eq!(p[2].dtype, Dtype::BF16);
        assert_eq!(p[0].shape[1], x.shape[1] * bits as usize / 32);
        assert_eq!(p[1].shape, [p[0].shape[0], x.shape[1] / 64]);
        self.at(["gate", "up", "down"][i])?;
        self.at("partial import")?;
        self.at("evaluate")?;
        self.at("sync")?;
        self.at("readback")?;
        if self.fault == "cancel" && i == 1 {
            self.token.cancel();
        }
        if self.fault == "unwind" {
            panic!("controlled fake unwind")
        }
        Ok(Projection {
            output: tensor(
                if i == 2 { 128 } else { 64 },
                if self.fault == "domain" { 17. } else { 0. },
            ),
            imports: 4,
            calls: 3,
            before_import: 0,
            before_call: 0,
            cpu_checks: 2,
            gpu: true,
            memory: [
                1,
                0,
                if self.fault == "memory" {
                    (NATIVE + 1) as usize
                } else {
                    4
                },
            ],
        })
    }
    fn activation(&mut self, _: &HostTensor, _: &HostTensor) -> StageResult<Activation> {
        self.at("activation")?;
        Ok(Activation {
            hidden: tensor(
                64,
                if self.fault == "down guard" {
                    f32::from_bits(1)
                } else {
                    0.
                },
            ),
            clamps: [[0; 64]; 2],
            stats: [2, 0, 9, 4, 13, 1, 9, 0],
            memory: [1, 0, 4],
        })
    }
    fn retire(&mut self) -> StageResult<Retirement> {
        self.at("retire")?;
        Ok(Retirement {
            live: u64::from(self.fault == "census"),
            freed: 4,
            double_free: 0,
            errors: 0,
            messages: 0,
            results: [2, 2, 0],
        })
    }
    fn finish(&mut self) -> StageResult<()> {
        self.at("finish")
    }
}
fn fake(fault: &'static str) -> (Fake, Rc<RefCell<Vec<&'static str>>>, CancellationToken) {
    let events = Rc::new(RefCell::new(vec![]));
    let token = CancellationToken::new();
    (
        Fake {
            fault,
            events: events.clone(),
            token: token.clone(),
        },
        events,
        token,
    )
}
#[test]
fn copied_and_allocating_order_replay_and_warm_step() {
    for profile in ["default", "mixed"] {
        for arm in [Arm::Cached, Arm::Allocating] {
            let (driver, events, _) = fake("");
            let (mut host, store, cp) = setup(&root(), profile, arm, driver, None).unwrap();
            let seq = run_sequence(&mut host, &store, &cp, arm).unwrap();
            let snap = host.backend().snapshot();
            assert_eq!(seq["replay"], seq["first"]);
            assert_eq!(seq["final"]["qmm_imports"], 108);
            assert_eq!(seq["final"]["projections"], 27);
            assert_eq!(seq["final"]["activations"], 9);
            assert_eq!(snap["cache_reads"], if arm == Arm::Cached { 36 } else { 0 });
            assert_eq!(
                snap["control_reads"],
                if arm == Arm::Allocating { 81 } else { 0 }
            );
            assert_eq!(
                host.peak_reservation_bytes(),
                host.backend().working_bytes() + 512 + 3072 + 1536 + 8
            );
            assert_eq!(
                events.borrow().iter().filter(|x| **x == "retire").count(),
                9
            );
            let rows: Vec<serde_json::Value> = host
                .backend()
                .records
                .iter()
                .map(|b| serde_json::from_slice(b).unwrap())
                .collect();
            let mut out = vec![];
            for (i, r) in rows.iter().enumerate() {
                assert_eq!(r["ordinal"], i);
                assert_eq!(r["component_sha256_before"], r["component_sha256_after"]);
                out.push(r["expert"].as_u64().unwrap());
            }
            assert_eq!(out, [0, 1, 0, 2, 1, 0, 0, 1, 0]);
            println!(
                "host fixture {profile} {} ledger={} sequence={} binding={} slots={:?}",
                arm.name(),
                host.backend().ledger(),
                seq,
                rows[0]["binding"],
                rows.iter()
                    .map(|v| &v["slot_generation"])
                    .collect::<Vec<_>>()
            );
        }
    }
}
#[test]
fn unresolved_boundaries_stop_quarantine_and_prevent_reuse() {
    for fault in [
        "begin",
        "gate",
        "up",
        "down",
        "activation",
        "partial import",
        "evaluate",
        "sync",
        "readback",
        "memory",
        "retire",
        "census",
        "finish",
        "unwind",
    ] {
        for arm in [Arm::Allocating, Arm::Cached] {
            let (driver, events, t) = fake(fault);
            let (mut host, store, cp) = setup(&root(), "mixed", arm, driver, None).unwrap();
            let w = host.backend().working_bytes();
            let failed = host
                .execute(&request(&cp, 0), &store, &store, &t, |_| Ok(()))
                .unwrap_err();
            assert!(!failed.to_string().is_empty());
            assert_eq!(host.state().position(), 0);
            let s = host.backend().snapshot();
            assert_eq!(s["quarantined"], true, "{fault}");
            assert_eq!(s["mlp_calls"], if fault == "finish" { 6 } else { 1 });
            if fault != "finish" {
                assert!(failed.cleanup_error.is_some(), "{fault}");
            }
            let starts = events.borrow().iter().filter(|e| **e == "begin").count();
            assert!(host
                .execute(&request(&cp, 0), &store, &store, &t, |_| Ok(()))
                .is_err());
            assert_eq!(
                events.borrow().iter().filter(|e| **e == "begin").count(),
                starts
            );
            assert_eq!(w, host.backend().working_bytes());
        }
    }
}
#[test]
fn clean_domain_refusals_and_cancellation_drain_before_return() {
    for fault in ["down guard", "domain", "cancel"] {
        let (driver, events, t) = fake(fault);
        let (mut host, store, cp) = setup(&root(), "default", Arm::Cached, driver, None).unwrap();
        let e = host
            .execute(&request(&cp, 0), &store, &store, &t, |_| Ok(()))
            .unwrap_err();
        assert!(e.cleanup_error.is_none(), "{fault}: {e}");
        assert_eq!(host.state().position(), 0);
        let events = events.borrow();
        assert!(events.contains(&"retire"));
        assert!(!events.contains(&"down"));
        assert_eq!(host.backend().snapshot()["quarantined"], false);
    }
}
#[test]
fn per_owner_reservation_short_and_overflow_refuse_before_reads() {
    for arm in [Arm::Allocating, Arm::Cached] {
        let (f, _, _) = fake("");
        let (h, _, _) = setup(&root(), "mixed", arm, f, None).unwrap();
        let w = h.backend().working_bytes();
        let (f, ev, t) = fake("");
        let (mut h, s, cp) = setup(&root(), "mixed", arm, f, Some(w + 512 + 3072 + 3)).unwrap();
        assert!(h.execute(&request(&cp, 0), &s, &s, &t, |_| Ok(())).is_err());
        assert_eq!(s.reads(), 0);
        assert!(ev.borrow().is_empty());
        assert_eq!(h.backend().snapshot()["cache_reads"], 0);
        let mut wrong = request(&cp, 0);
        wrong.scratch_bytes = u64::MAX;
        assert!(h.execute(&wrong, &s, &s, &t, |_| Ok(())).is_err());
        assert_eq!(s.reads(), 0);
        let (f, _, _) = fake("");
        assert!(setup(&root(), "default", arm, f, Some(u64::MAX)).is_err());
    }
}
#[test]
fn typed_staging_matches_all_original_components_and_rejects_crossed_geometry() {
    for profile in ["default", "mixed"] {
        let p = Population::load(profile).unwrap();
        let (c, source) = p.open(&root(), Arm::Allocating).unwrap();
        let g = Geometry::from_cache(&c, &p).unwrap();
        let source = source.unwrap();
        for e in 0..3 {
            let plan = source.plan(p.request(e)).unwrap();
            let owned = plan.load().unwrap();
            let parts =
                std::array::from_fn(|i| std::array::from_fn(|j| owned.bytes(i, j).unwrap()));
            let (staged, capacity) = stage_parts(parts, g, &p.hashes[e as usize]).unwrap();
            for i in 0..3 {
                for j in 0..3 {
                    assert_eq!(staged[i][j].bytes, parts[i][j]);
                    assert_ne!(staged[i][j].bytes.as_ptr(), parts[i][j].as_ptr());
                    assert_eq!(staged[i][j].shape, g.shape(i, j));
                }
            }
            assert!(capacity < 65536);
            let mut invalid = parts;
            invalid.swap(0, 2);
            assert!(stage_parts(invalid, g, &p.hashes[e as usize]).is_err());
            let mut short = parts;
            short[0][0] = &short[0][0][1..];
            assert!(stage_parts(short, g, &p.hashes[e as usize]).is_err());
            assert!(stage_parts(parts, g, &p.hashes[(e as usize + 1) % 3]).is_err());
            assert!(
                stage_parts(parts, Geometry { bits: [2, 4, 8] }, &p.hashes[e as usize]).is_err()
            );
        }
        let mut other = Population::load(profile).unwrap();
        other.bits[1] = 8;
        assert!(Geometry::from_cache(&c, &other).is_err());
    }
}

#[test]
fn changed_selected_payload_and_oversized_input_stop_before_driver() {
    use std::{
        fs,
        io::{Seek, SeekFrom, Write},
    };
    for arm in [Arm::Cached, Arm::Allocating] {
        let tmp = std::env::temp_dir().join(format!(
            "resident-selected-{}-{}",
            std::process::id(),
            arm.name()
        ));
        fs::create_dir(&tmp).unwrap();
        let tmp = tmp.canonicalize().unwrap();
        let pop = Population::load("default").unwrap();
        let rel = Path::new("fixtures/resident-expert-mlp").join(&pop.name);
        fs::create_dir_all(tmp.join(&rel)).unwrap();
        for file in [
            "config.json",
            "model.safetensors.index.json",
            "model.safetensors",
        ] {
            fs::copy(root().join(&rel).join(file), tmp.join(&rel).join(file)).unwrap();
        }
        let input = pop.input(&tmp, 0);
        fs::create_dir_all(input.parent().unwrap()).unwrap();
        fs::copy(pop.input(&root(), 0), &input).unwrap();
        fs::OpenOptions::new()
            .append(true)
            .open(&input)
            .unwrap()
            .write_all(&[9])
            .unwrap();
        let (driver, ev, t) = fake("");
        let (mut h, store, cp) = setup(&tmp, "default", arm, driver, None).unwrap();
        assert!(h
            .execute(&request(&cp, 0), &store, &store, &t, |_| Ok(()))
            .is_err());
        assert_eq!(store.reads(), 0);
        assert!(ev.borrow().is_empty());
        fs::copy(pop.input(&root(), 0), &input).unwrap();
        drop(h);
        let mut shard = fs::OpenOptions::new()
            .write(true)
            .open(tmp.join(&rel).join("model.safetensors"))
            .unwrap();
        shard.seek(SeekFrom::Start(pop.ranges[0][0][0][0])).unwrap();
        shard.write_all(&[0xee, 0xee, 0xee, 0xee]).unwrap();
        drop(shard);
        let (driver, ev, t) = fake("");
        let (mut h, store, cp) = setup(&tmp, "default", arm, driver, None).unwrap();
        assert!(h
            .execute(&request(&cp, 0), &store, &store, &t, |_| Ok(()))
            .is_err());
        assert_eq!(h.state().position(), 0);
        assert!(!ev.borrow().contains(&"begin"));
        drop(h);
        fs::remove_dir_all(tmp).unwrap();
    }
}
#[test]
#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
fn independent_metadata_proof_at_relocated_canonical_roots() {
    use std::{
        fs,
        process::Command,
        time::{SystemTime, UNIX_EPOCH},
    };
    let source = root();
    let temp = std::env::temp_dir().canonicalize().unwrap().join(format!(
        "resident-ledger-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let script = r#"import json,sys,pathlib
source,repo=map(pathlib.Path,sys.argv[1:3])
sys.path.append(str(source/'scripts/research'))
import f020_resident_mlp_check as check
view=repo/'fixtures/resident-expert-mlp'
recipes=json.loads((view/'manifest.json').read_bytes())['recipes']
print(json.dumps({p:{a:check.expect_ledger(p,a,r,repo) for a in ('allocating','cached')} for p,r in recipes.items()}))
"#;
    for suffix in ["s", "a-longer-checkout-root", "é-東京"] {
        let repo = temp.join(suffix);
        let view = Path::new("fixtures/resident-expert-mlp");
        fs::create_dir_all(repo.join(view)).unwrap();
        fs::copy(
            source.join(view).join("manifest.json"),
            repo.join(view).join("manifest.json"),
        )
        .unwrap();
        for profile in ["default", "mixed"] {
            let pop = Population::load(profile).unwrap();
            let rel = view.join(&pop.name);
            fs::create_dir_all(repo.join(&rel)).unwrap();
            for name in [
                "config.json",
                "model.safetensors.index.json",
                "model.safetensors",
            ] {
                fs::copy(source.join(&rel).join(name), repo.join(&rel).join(name)).unwrap();
            }
            for e in 0..3 {
                let dst = pop.input(&repo, e);
                fs::create_dir_all(dst.parent().unwrap()).unwrap();
                fs::copy(pop.input(&source, e), dst).unwrap();
            }
        }
        let cmd = Command::new("/usr/bin/python3")
            .args(["-I", "-S", "-B", "-c", script])
            .arg(&source)
            .arg(&repo)
            .output()
            .unwrap();
        assert!(
            cmd.status.success(),
            "{}",
            String::from_utf8_lossy(&cmd.stderr)
        );
        let expected: serde_json::Value = serde_json::from_slice(&cmd.stdout).unwrap();
        for profile in ["default", "mixed"] {
            for arm in [Arm::Cached, Arm::Allocating] {
                let (driver, _, _) = fake("");
                let (mut step, store, cp) = setup(&repo, profile, arm, driver, None).unwrap();
                let ledger = step.backend().ledger().clone();
                assert_eq!(expected[profile][arm.name()], ledger);
                let seq = run_sequence(&mut step, &store, &cp, arm).unwrap();
                let w = step.backend().working_bytes();
                assert_eq!(seq["peak_reservation"], w + 5128);
                assert_eq!(seq["first"], seq["replay"]);
                for (offset, position) in [(512 + 3072 + 4, 0), (5128, 1)] {
                    let (driver, events, t) = fake("");
                    let (mut bounded, s, cp) =
                        setup(&repo, profile, arm, driver, Some(w + offset - 1)).unwrap();
                    if position == 1 {
                        bounded
                            .execute(&request(&cp, 0), &s, &s, &t, |_| Ok(()))
                            .unwrap();
                    }
                    let before = (
                        bounded.backend().snapshot(),
                        s.reads(),
                        events.borrow().len(),
                    );
                    assert!(bounded
                        .execute(&request(&cp, position), &s, &s, &t, |_| Ok(()))
                        .is_err());
                    assert_eq!(
                        before,
                        (
                            bounded.backend().snapshot(),
                            s.reads(),
                            events.borrow().len()
                        )
                    );
                    assert_eq!(bounded.state().position(), position);
                }
                let bytes = repo
                    .join(view)
                    .join(Population::load(profile).unwrap().name)
                    .as_os_str()
                    .len();
                println!(
                    "relocated host {}",
                    serde_json::json!({"root_case":suffix,"root_utf8_bytes":bytes,"profile":profile,"arm":arm.name(),"ledger":ledger,"sequence":seq,"short_refusals":2})
                );
            }
        }
    }
    fs::remove_dir_all(temp).unwrap();
}
