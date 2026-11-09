use super::*;

struct Script {
    arms: Vec<Arm>,
    decisions: Vec<String>,
    retries: bool,
    plan: &'static str,
    fail: usize,
}
impl Campaign for Script {
    fn arm(&mut self, a: Arm) -> R<f64> {
        self.arms.push(a.clone());
        if self.arms.len() == self.fail {
            return bad("process/resource failure");
        }
        let base = 1.;
        let mean = match a.stage {
            "baseline" if self.retries => 0.000001,
            "recalibration" if self.plan == "inconclusive" => 0.000001,
            "primary" if a.method == "adopted" && self.plan == "stop" => 0.97,
            "primary" if a.method == "adopted" && self.plan == "mixed" && a.pair == 2 => 1.,
            "heldout" if a.method == "adopted" && self.plan == "heldout" => 0.99,
            "resident" if a.method == "adopted" && self.plan == "regression" => 1.04,
            _ if a.method == "adopted" => 0.90,
            _ => base,
        };
        Ok(mean)
    }
    fn record(&mut self, k: &str, _: V) -> R<()> {
        self.decisions.push(k.into());
        Ok(())
    }
}
fn scripted(plan: &'static str, retries: bool) -> Script {
    Script {
        arms: vec![],
        decisions: vec![],
        retries,
        plan,
        fail: 0,
    }
}
#[test]
fn maximum_schedule_preserves_pair_order_and_release() {
    let mut s = scripted("mixed", true);
    assert_eq!(schedule(&mut s).unwrap(), "PASS_EXPERIMENTAL_ONLY");
    assert_eq!(s.arms.len(), 48);
    for (k, mode, n) in [
        (0, "fill", 128),
        (6, "fill", 512),
        (12, "resident", 4096),
        (18, "resident", 16384),
    ] {
        assert!(s.arms[k..k + 6]
            .iter()
            .all(|x| x.mode == mode && x.count == n && x.method == "copied"))
    }
    for (k, stage, case, arms) in [
        (24, "primary", A, "caacca"),
        (30, "followup", A, "acc aac"),
        (36, "heldout", B, "caacca"),
        (42, "resident", A, "caacca"),
    ] {
        assert_eq!(
            s.arms[k..k + 6]
                .iter()
                .map(|x| x.method.chars().next().unwrap())
                .collect::<String>(),
            arms.replace(' ', "")
        );
        assert!(s.arms[k..k + 6]
            .iter()
            .all(|x| x.stage == stage && x.case == case));
    }
    assert_eq!(
        s.decisions
            .iter()
            .filter(|x| *x == "calibration-freeze")
            .count(),
        1
    );
}
#[test]
fn decisions_stop_at_their_own_boundaries() {
    for (plan, n, out, retry) in [
        ("stop", 18, "NO_PROMOTION", false),
        ("heldout", 24, "NO_PROMOTION", false),
        ("regression", 30, "NO_PROMOTION", false),
        ("inconclusive", 12, "INCONCLUSIVE", true),
        ("pass", 30, "PASS_EXPERIMENTAL_ONLY", false),
    ] {
        let mut s = scripted(plan, retry);
        assert_eq!(schedule(&mut s).unwrap(), out);
        assert_eq!(s.arms.len(), n);
    }
}
#[test]
fn process_errors_never_buy_recalibration_or_the_next_arm() {
    for n in 1..=48 {
        let mut s = scripted("mixed", true);
        s.fail = n;
        assert!(schedule(&mut s).is_err());
        assert_eq!(s.arms.len(), n);
    }
}
fn synthetic(mode: &'static str, method: &'static str) -> (Arm, V, V, V, Vec<V>, V) {
    let count = if mode == "fill" { 128 } else { 4096 };
    let a = Arm {
        mode,
        method,
        count,
        stage: if mode == "fill" {
            "primary"
        } else {
            "resident"
        },
        pair: 0,
        case: A,
    };
    let q = json!({"output":"synthetic-output","preflight":{"phase":"original-preflight","id":A},"fill":{"phase":"verified-fill","receipt":"synthetic-verified-read","id":A},"setup":{"max_buffer_length":1_u64<<36},"config":{"arm":"copied","fixture_root":"synthetic","metadata_identities":{},"mode":"diagnostic","sequence":[A],"source_commit":"synthetic","source_tree":"test","binary_sha256":"bin","native_libraries":{"libmlx.dylib":"test"},"host":{"machine":"synthetic"},"fixture_manifest_sha256":"fixture","generator_hashes":{"g":"test"},"dependency_manifest_sha256":"deps"}});
    let c = a.config(&q).unwrap();
    let ad = usize::from(method == "adopted");
    let t = count + 4;
    let f = if mode == "fill" { t } else { 2 };
    let total = (6 + ad) * f + t + ad;
    let prov = json!({"native_libraries":c["native_libraries"],"binary_sha256":"bin","source_commit":"synthetic","source_tree":"test","native_prefix":"<NATIVE_PREFIX>","TF32":false,"loaded_images_verified":true});
    let setup = json!({"phase":"setup","adopted":ad==1,"registered_bytes":8388608,"page":16384,"max_buffer_length":1_u64<<36,"rust_capacity":9437184,"live_bound":20512768,"stream_id":0,"memory":[0,0,0]});
    let mut ev = vec![
        json!({"phase":"provenance","value":prov}),
        q["preflight"].clone(),
        setup,
    ];
    let mut samples = vec![];
    for i in 0..t {
        let g = if mode == "fill" { i / 2 + 1 } else { 1 };
        if i < f {
            let mut v = q["fill"].clone();
            v["slot"] = json!(i % 2);
            v["generation"] = json!(g);
            v["view_setup_seconds"] = json!(0.001);
            ev.push(v);
        }
        let s = 0.0001 + i as f64 * 1e-10;
        ev.push(json!({"phase":"operation","iteration":i,"warmup":i<4,"id":A,"slot":i%2,"generation":g,"seconds":s,"memory":[100,20,200],"output_sha256":"synthetic-output"}));
        if i >= 4 {
            samples.push(s)
        }
    }
    let r = json!({"config_sha256":"cfg","outputs":[],"host":{"vm_page_bytes":16384,"max_buffer_length":1_u64<<36},"identity":{"contract_sha256":packed_affine_adoption::CONTRACT,"fixture_manifest_sha256":"fixture"},"source_binding":{"source_commit":"synthetic","source_tree":"test","dependency_manifest_sha256":"deps","generator_hashes":{"g":"test"}},"frozen_host":c["host"],"provenance":prov,"adoption":{"method":if ad==1{"managed-flat-parent"}else{"copied"},"pointer_identity":ad==1,"registered_bytes":ad*8388608},"lifetime":{"created":total,"freed":total,"live":0,"parent_counts":[ad,ad],"view_counts":[(1+ad)*f,(1+ad)*f],"output_counts":[t,t],"retired_parents":ad,"completed_callbacks":ad,"early_free_count":0,"quarantine":false},"io":{"requested_bytes":4718592*f,"range_attempts":3*f,"read_policy":"buffered-exact","physical_device_bytes":null,"overread_bytes":0},"copies":{"packed_import_bytes":(1-ad)*4194304*f,"metadata_raw_bytes":524288*f,"metadata_widening_bytes":1048576*f,"output_bytes":8192*t,"layout_materialization_bytes":null,"unknown_materialization":true},"memory":{"raw_mlx_active_cache_peak":[100,20,200],"mlx_memory_limit_requested":33554432,"mlx_cache_limit_requested":33554432,"native_limit_calls_status":0,"live_working_bound":20512768,"combined_reservation":100663296,"adopted_capacity_constant_within_reset":ad*8388608,"reset_interval":"after four warmups","clear_events":1,"deduplicated_physical_usage":null,"rust_capacity":9437184,"adopted_overlap":ad*8388608,"wiring":"unknown"},"timing":{"samples":samples,"first_operation":0.0001,"setup_seconds":0.1,"startup_through_first_projection":0.1001,"total":2.,"block_wall_seconds":1.}});
    (
        a,
        q,
        c,
        r,
        ev,
        json!({"outcome":"EXIT_STATUS 0","reaped":true,"binary_sha256":"bin","config_sha256":"cfg"}),
    )
}
#[test]
fn four_timing_report_shapes_accept_sub_floor_candidate_samples() {
    for mode in ["fill", "resident"] {
        for method in ["copied", "adopted"] {
            let (a, q, c, r, e, o) = synthetic(mode, method);
            assert!(admit_report(&a, &q, &c, "cfg", &r, &e, &o).unwrap() > 0.);
        }
    }
}
#[test]
fn invalid_reports_and_events_refuse() {
    let (a, q, c, r, e, o) = synthetic("fill", "adopted");
    let admit = |r: &V, e: &[V]| admit_report(&a, &q, &c, "cfg", r, e, &o);
    for (p, x) in [
        ("/timing/samples/0", V::Null),
        ("/timing/first_operation", json!(0)),
        ("/copies/metadata_raw_bytes", json!(0)),
        ("/io/range_attempts", json!(0)),
        ("/lifetime/created", json!(1)),
        ("/lifetime/retired_parents", json!(0)),
        ("/lifetime/quarantine", json!(true)),
        ("/memory/raw_mlx_active_cache_peak", json!([0, 0, 33554433])),
        ("/frozen_host", V::Null),
        ("/source_binding/source_commit", json!("other")),
        ("/outputs", json!([{}])),
    ] {
        let mut v = r.clone();
        *v.pointer_mut(p).unwrap() = x;
        assert!(admit(&v, &e).is_err(), "{p}");
    }
    for (p, x) in [
        ("iteration", json!(9)),
        ("warmup", json!(false)),
        ("slot", json!(1)),
        ("generation", json!(2)),
        ("output_sha256", json!("bad")),
        ("seconds", json!("NaN")),
    ] {
        let mut v = e.clone();
        v[4][p] = x;
        assert!(admit(&r, &v).is_err(), "{p}");
    }
    let mut v = e.clone();
    v.swap(8, 10);
    assert!(admit(&r, &v).is_err());
    assert!(admit(&r, &e[1..]).is_err());
    v = e.clone();
    v.push(e[4].clone());
    assert!(admit(&r, &v).is_err());
    let mut v = r.clone();
    v["timing"]["samples"].as_array_mut().unwrap().reverse();
    assert!(admit(&v, &e).is_err());
    for (k, x) in [
        ("mode", json!("raw-length")),
        ("sequence", json!([B])),
        ("operations", json!(129)),
        ("arm", json!("copied")),
    ] {
        let mut v = c.clone();
        v[k] = x;
        assert!(admit_report(&a, &q, &v, "cfg", &r, &e, &o).is_err());
    }
    let (a, q, c, r, mut e, o) = synthetic("resident", "copied");
    e.insert(7, e[3].clone());
    assert!(admit_report(&a, &q, &c, "cfg", &r, &e, &o).is_err());
}
#[test]
fn subprocess_outcomes_and_deadline() {
    let end = || Instant::now() + Duration::from_secs(5);
    for (cmd, args, prefix) in [
        ("/usr/bin/true", vec![], "EXIT_STATUS 0"),
        ("/usr/bin/false", vec![], "EXIT_STATUS 1"),
        ("/does/not/exist", vec![], "SPAWN_FAILED"),
        ("/bin/sh", vec!["-c", "kill -TERM $$"], "SIGNAL 15"),
    ] {
        let (o, _) = spawn(Command::new(cmd).args(args), end(), false).unwrap();
        assert!(o["outcome"].as_str().unwrap().starts_with(prefix), "{o}");
    }
    let deadline = Instant::now() + Duration::from_millis(80);
    assert!(left(deadline, Duration::from_secs(120)).unwrap() < Duration::from_millis(81));
    let (o, _) = spawn(Command::new("/bin/sleep").arg("10"), deadline, false).unwrap();
    assert!(o["outcome"].as_str().unwrap().starts_with("TIMEOUT") && o["reaped"] == true);
    assert!(spawn(&mut Command::new("/usr/bin/true"), Instant::now(), false).is_err());
}
#[test]
fn wait_error_keeps_owned_handle_until_reap() {
    let mut child = Command::new("/bin/sleep")
        .arg("10")
        .process_group(0)
        .spawn()
        .unwrap();
    let o = observe(
        &mut child,
        Instant::now() + Duration::from_secs(5),
        Instant::now(),
        |_| Err(std::io::Error::other("injected wait observation")),
    );
    assert_eq!(o["outcome"], "WAIT_ERROR");
    assert_eq!(o["reaped"], true);
    assert!(child.try_wait().unwrap().is_some());
}
#[test]
fn stable_claim_cannot_be_refunded_by_new_output_name() {
    let root = std::env::temp_dir().join(format!("m1b-synthetic-claim-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let p = root.join("synthetic.claim");
    let (_, h) = claim(&p, &json!({"root":"first"})).unwrap();
    assert!(claim(&p, &json!({"root":"second"})).is_err());
    assert_eq!(file_sha256(&p).unwrap(), h);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn final_seal_drift_invalidates_a_pass() {
    let root = std::env::temp_dir()
        .canonicalize()
        .unwrap()
        .join(format!("m1b-synthetic-seals-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let p = root.join("arm.json");
    let h = write_new(&p, &json!({"decision":"PASS_EXPERIMENTAL_ONLY"})).unwrap();
    let seals = vec![(p.clone(), h)];
    verify_seals(&seals).unwrap();
    fs::write(&p, b"changed").unwrap();
    assert!(verify_seals(&seals).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn replaced_timing_root_is_not_a_failure_sink() {
    let root = std::env::temp_dir()
        .canonicalize()
        .unwrap()
        .join(format!("m1b-root-owner-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let owned = root.join("timing");
    fs::create_dir(&owned).unwrap();
    let id = root_id(&owned).unwrap();
    fs::rename(&owned, root.join("retained")).unwrap();
    fs::create_dir(&owned).unwrap();
    assert!(still_owned(&owned, id).is_err());
    assert!(!owned.join("result.json").exists());
    fs::remove_dir_all(root).unwrap();
}
