use super::*;
use packed_affine_adoption::policy::{self, Screen};
use std::time::Instant;
pub fn run(campaign: &Path, prefix: &Path, freeze: &Value) {
    assert_eq!(
        freeze["host_role"], "m1-ultra-studio",
        "performance belongs only to physical Studio"
    );
    let studio = read(&campaign.join("m1a-acceptance.json"));
    let ci = read(Path::new(freeze["native_ci_acceptance"].as_str().unwrap()));
    assert_eq!(
        sha256_hex(&fs::read(freeze["native_ci_acceptance"].as_str().unwrap()).unwrap()),
        freeze["native_ci_acceptance_sha256"]
    );
    for receipt in [&studio, &ci] {
        for field in [
            "contract_sha256",
            "source_commit",
            "source_tree",
            "fixture_manifest_sha256",
        ] {
            assert_eq!(receipt[field], freeze[field]);
        }
        assert_eq!(receipt["mechanism"], "PASS");
        assert_eq!(receipt["correctness"], "PASS");
    }
    assert_eq!(studio["binary_sha256"], freeze["binary_sha256"]);
    assert_eq!(studio["native_libraries"], freeze["native_libraries"]);
    assert_eq!(
        studio["mechanism_sha256"],
        sha256_hex(&fs::read(campaign.join("m1a/mechanism.json")).unwrap())
    );
    for row in studio["reports"].as_array().unwrap() {
        let path = packed_affine_adoption::cases::confined(
            &campaign.join("m1a"),
            row["report"].as_str().unwrap(),
        )
        .unwrap();
        assert_eq!(row["report_sha256"], sha256_hex(&fs::read(path).unwrap()));
    }
    assert_eq!(studio["host_role"], "m1-ultra-studio");
    assert_eq!(ci["host_role"], "native-ci");
    let root = campaign.join("m1b");
    fs::create_dir(&root).expect("reconcile existing timing campaign; no new budget");
    let started = Instant::now();
    let portable = read(Path::new(freeze["portable_report"].as_str().unwrap()));
    let identities: serde_json::Map<String, Value> = portable["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| {
            (
                v["id"].as_str().unwrap().into(),
                v["receipt"]["metadata_snapshot_sha256"].clone(),
            )
        })
        .collect();
    let mechanism = read(&campaign.join("m1a/mechanism.json"));
    let mut expected = std::collections::BTreeMap::new();
    for entry in mechanism["reports"].as_array().unwrap() {
        let r = read(&campaign.join("m1a").join(entry["report"].as_str().unwrap()));
        if let Some(outputs) = r["outputs"].as_array() {
            for o in outputs {
                expected.insert(o["id"].as_str().unwrap().to_string(), o["sha256"].clone());
            }
        }
    }
    let arm = |label: &str, case: &str, mode: &str, method: &str, count: usize| -> f64 {
        assert!(
            started.elapsed().as_secs() < policy::DEADLINE_SECONDS,
            "timing campaign deadline"
        );
        let config = json!({"mode":mode,"arm":method,"sequence":[case],"fixture_root":freeze["fixture_root"],"fixture_manifest_sha256":freeze["fixture_manifest_sha256"],"metadata_identities":identities,"operations":count});
        let r = child(&root, prefix, label, config, 120);
        let samples = r["timing"]["samples"].as_array().unwrap();
        assert_eq!(samples.len(), count);
        let values: Vec<_> = samples
            .iter()
            .map(|v| v.as_f64().filter(|x| x.is_finite() && *x > 0.0).unwrap())
            .collect();
        let events = fs::read_to_string(root.join(label).join("events.jsonl")).unwrap();
        let ops: Vec<Value> = events
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .filter(|v: &Value| v["phase"] == "operation")
            .collect();
        assert_eq!(ops.len(), count + 4);
        for op in ops {
            assert_eq!(
                op["output_sha256"], expected[case],
                "timing correctness must match the qualified output"
            );
        }
        assert!(
            started.elapsed().as_secs() <= policy::DEADLINE_SECONDS,
            "timing campaign exceeded deadline"
        );
        values.iter().sum::<f64>() / count as f64
    };
    let mut calibrations = serde_json::Map::new();
    let mut settings = Vec::new();
    for (mode, initial, retry) in [
        ("fill", policy::FILL, policy::FILL_RETRY),
        ("resident", policy::RESIDENT, policy::RESIDENT_RETRY),
    ] {
        let mut accepted = None;
        for (attempt, count) in [initial, retry].into_iter().enumerate() {
            let means: [f64; 6] = std::array::from_fn(|i| {
                arm(
                    &format!("aa-{mode}-{attempt}-{i}"),
                    "full-positive-A-gate",
                    mode,
                    "copied",
                    count,
                )
            });
            let durations = means.map(|v| v * count as f64);
            let noise = policy::noise(means, durations);
            let record = json!({"attempt":attempt,"count":count,"means":means,"durations":durations,"noise":noise.as_ref().ok(),"result":noise.as_ref().err()});
            create(&root.join(format!("aa-{mode}-{attempt}.json")), &record);
            if let Ok(e) = noise {
                calibrations.insert(mode.into(), record);
                accepted = Some((count, e));
                break;
            }
        }
        let Some(setting) = accepted else {
            create(
                &root.join("decision.json"),
                &json!({"performance_screen":"INCONCLUSIVE","stop_reason":"baseline unsuitable after one retry","shipping_default":"copied"}),
            );
            return;
        };
        settings.push(setting);
    }
    create(
        &root.join("calibration-freeze.json"),
        &Value::Object(calibrations),
    );
    let (fill_count, fill_e) = settings[0];
    let (resident_count, resident_e) = settings[1];
    let pairs = |label: &str, case: &str, mode: &str, count: usize, reverse: bool| -> [f64; 3] {
        std::array::from_fn(|i| {
            let candidate_first = (i % 2 == 1) ^ reverse;
            let order = if candidate_first {
                ["adopted", "copied"]
            } else {
                ["copied", "adopted"]
            };
            let mut c = 0.0;
            let mut a = 0.0;
            for method in order {
                let t = arm(&format!("{label}-{i}-{method}"), case, mode, method, count);
                if method == "copied" {
                    c = t;
                } else {
                    a = t;
                }
            }
            1.0 - a / c
        })
    };
    let primary = pairs("primary", "full-positive-A-gate", "fill", fill_count, false);
    create(&root.join("primary.json"), &json!({"gains":primary}));
    let mut followup_used = false;
    let pass = match policy::primary(primary, fill_e).unwrap() {
        Screen::Pass => true,
        Screen::Stop => false,
        Screen::Followup => {
            followup_used = true;
            let more = pairs("followup", "full-positive-A-gate", "fill", fill_count, true);
            create(&root.join("followup.json"), &json!({"gains":more}));
            policy::followup(
                [
                    primary[0], primary[1], primary[2], more[0], more[1], more[2],
                ],
                fill_e,
            )
            .unwrap()
        }
    };
    if !pass {
        create(
            &root.join("decision.json"),
            &json!({"performance_screen":"NO_PROMOTION","stop_reason":"primary practical benefit/noise rule","followup_used":followup_used,"shipping_default":"copied"}),
        );
        return;
    }
    let heldout = pairs("heldout", "full-positive-B-up", "fill", fill_count, false);
    let heldout_pass = policy::primary(heldout, fill_e).unwrap() == Screen::Pass;
    create(
        &root.join("heldout.json"),
        &json!({"gains":heldout,"pass":heldout_pass}),
    );
    if !heldout_pass {
        create(
            &root.join("decision.json"),
            &json!({"performance_screen":"NO_PROMOTION","stop_reason":"held-out confirmation","followup_used":followup_used,"shipping_default":"copied"}),
        );
        return;
    }
    let resident = pairs(
        "resident",
        "full-positive-A-gate",
        "resident",
        resident_count,
        false,
    )
    .map(|gain| -gain);
    let pass = policy::resident(resident, resident_e).unwrap();
    create(
        &root.join("decision.json"),
        &json!({"performance_screen":if pass{"PASS_EXPERIMENTAL_ONLY"}else{"NO_PROMOTION"},"resident_regressions":resident,"followup_used":followup_used,"elapsed_seconds":started.elapsed().as_secs_f64(),"shipping_default":"copied","M2_M4_started":false}),
    );
}
