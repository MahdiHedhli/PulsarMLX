#[path = "../src/weighted_native_guard.rs"]
mod guard;
use backend::{step::HostLayerExecutor, CancellationToken};
use guard::{Guard, Guarded};
use mlx_expert_mlp::{
    resident_fixture::Arm,
    resident_pipeline::*,
    weighted::{self, RouteBook},
};
use mlx_native_affine::{dtype::Dtype, fixture::HostTensor, refusal::DeviceFacts};
use std::{
    cell::{Cell, RefCell},
    fs,
    path::{Path, PathBuf},
    process::Command,
    rc::Rc,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}
fn tensor(n: usize) -> HostTensor {
    HostTensor {
        name: "control".into(),
        shape: vec![1, n],
        dtype: Dtype::F32,
        bytes: vec![0; 4 * n],
    }
}
struct Synthetic {
    log: Rc<RefCell<Vec<&'static str>>>,
    bad: bool,
}
impl Driver for Synthetic {
    fn begin(&mut self) -> StageResult<DeviceFacts> {
        self.log.borrow_mut().push("begin");
        Ok(DeviceFacts::GPU)
    }
    fn projection(
        &mut self,
        r: usize,
        _: &HostTensor,
        _: &[HostTensor; 3],
        _: u32,
    ) -> StageResult<Projection> {
        self.log.borrow_mut().push(["gate", "up", "down"][r]);
        Ok(Projection {
            output: tensor(if r == 2 { 128 } else { 64 }),
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
        self.log.borrow_mut().push("activation");
        Ok(Activation {
            hidden: tensor(64),
            clamps: [[0; 64]; 2],
            stats: [2, 0, 9, 4, 13, 1, 9, 0],
            memory: [0; 3],
        })
    }
    fn retire(&mut self) -> StageResult<Retirement> {
        self.log.borrow_mut().push("retire");
        if self.bad {
            return Err(Fault::uncertain("controlled retirement failure"));
        }
        Ok(Retirement {
            live: 0,
            freed: 1,
            double_free: 0,
            errors: 0,
            messages: 0,
            results: [1, 1, 0],
        })
    }
    fn finish(&mut self) -> StageResult<()> {
        self.log.borrow_mut().push("finish");
        Ok(())
    }
}
#[test]
fn guard_refuses_wrong_owner_and_initial_probe_failure() {
    assert!(Guard::new(|| Err(Fault::uncertain("unsupported"))).is_err());
    let mut g = Guard::new(|| Ok(0)).unwrap();
    std::thread::spawn(move || {
        assert!(g.check("retired").unwrap_err().uncertain);
        assert_eq!(g.words.len(), 1)
    })
    .join()
    .unwrap();
}
#[test]
fn guard_observes_retirement_before_weighting_and_finish_before_commit() {
    for mode in ["clean", "retire", "retired_fpcr", "finish_fpcr"] {
        let calls = Cell::new(0);
        let log = Rc::new(RefCell::new(Vec::new()));
        let state = Rc::new(RefCell::new(
            Guard::new(|| {
                let n = calls.get();
                calls.set(n + 1);
                Ok(u64::from(
                    (mode == "retired_fpcr" && n == 1) || (mode == "finish_fpcr" && n == 2),
                ))
            })
            .unwrap(),
        ));
        let driver = Guarded {
            copied: Synthetic {
                log: log.clone(),
                bad: mode == "retire",
            },
            state: state.clone(),
        };
        let (mut h, s) = weighted::setup(
            &root(),
            "default",
            RouteBook::fixed("default").unwrap(),
            Arm::Cached,
            driver,
            None,
        )
        .unwrap();
        let req = h.backend().book().request(0).unwrap();
        let outcome = h.execute(&req, &s, &s, &CancellationToken::new(), |_| Ok(()));
        assert_eq!(
            *log.borrow(),
            [
                "begin",
                "gate",
                "up",
                "activation",
                "down",
                "retire",
                "finish"
            ]
        );
        let good = mode == "clean";
        assert_eq!(outcome.is_ok(), good);
        assert_eq!(h.state().position(), u64::from(good));
        assert_eq!(
            h.backend().snapshot()["weighted"],
            u64::from(good || mode == "finish_fpcr")
        );
        assert_eq!(h.backend().snapshot()["quarantined"], !good);
        assert_eq!(h.active_reservation_bytes(), 0);
        if good {
            state.borrow_mut().check("committed").unwrap();
        }
        assert_eq!(
            state.borrow().words.iter().any(|(n, _)| *n == "retired"),
            mode != "retire"
        );
    }
}
#[test]
#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
fn weighted_ledger_matches_the_independent_model_at_three_checkout_paths() {
    let base = std::env::temp_dir()
        .canonicalize()
        .unwrap()
        .join(format!("weighted-ledger-{}", std::process::id()));
    fs::create_dir(&base).unwrap();
    let source = root();
    let fixture = Path::new("fixtures/resident-expert-mlp");
    for suffix in ["s", "longer-canonical-root-é", "東京-utf8-checkout"] {
        let repo = base.join(suffix);
        fs::create_dir_all(repo.join(fixture)).unwrap();
        fs::copy(
            source.join(fixture).join("manifest.json"),
            repo.join(fixture).join("manifest.json"),
        )
        .unwrap();
        for profile in ["default", "mixed"] {
            let rel = fixture.join(format!("d128-h64-{profile}"));
            fs::create_dir(repo.join(&rel)).unwrap();
            for n in [
                "config.json",
                "model.safetensors.index.json",
                "model.safetensors",
            ] {
                fs::copy(source.join(&rel).join(n), repo.join(&rel).join(n)).unwrap();
            }
            for arm in [Arm::Allocating, Arm::Cached] {
                let driver = Synthetic {
                    log: Default::default(),
                    bad: false,
                };
                let (h, _) = weighted::setup(
                    &repo,
                    profile,
                    RouteBook::fixed(profile).unwrap(),
                    arm,
                    driver,
                    None,
                )
                .unwrap();
                let program = r#"import sys,json,pathlib
sys.path.insert(0,sys.argv[1]);import f020_weighted_native_check as check
repo=pathlib.Path(sys.argv[2]);p,a=sys.argv[3:];r=json.loads((repo/'fixtures/resident-expert-mlp/manifest.json').read_bytes())['recipes'][p]
print(json.dumps(check.ledger(repo,p,a,r)))"#;
                let o = Command::new("/usr/bin/python3")
                    .args(["-I", "-S", "-B", "-c", program])
                    .arg(source.join("scripts/research"))
                    .arg(&repo)
                    .args([profile, arm.name()])
                    .output()
                    .unwrap();
                assert!(o.status.success(), "{}", String::from_utf8_lossy(&o.stderr));
                let l: serde_json::Value = serde_json::from_slice(&o.stdout).unwrap();
                assert_eq!(h.backend().ledger(), &l);
                assert_eq!(l["W_total"], h.backend().working_bytes());
                println!(
                    "{suffix} {profile} {} M={} W={} harness={}",
                    arm.name(),
                    l["M"],
                    l["W_total"],
                    2 << 20
                );
            }
        }
    }
    fs::remove_dir_all(base).unwrap();
}
