mod adapter {
    // Keep the exact same hash-checking CPU-only Driver used for the four staged controls.
    include!("staged_weighted_host.rs");

    use mlx_expert_mlp::policy_qualification::{self as qual, Arm as QualificationArm, ArmFiles};

    struct Temporary(PathBuf);
    impl Temporary {
        fn new() -> Self {
            let base = std::env::temp_dir().canonicalize().unwrap();
            static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            Self::under(&base, || {
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            })
        }

        fn under(base: &std::path::Path, mut next: impl FnMut() -> u64) -> Self {
            loop {
                let path = base.join(format!(
                    "policy-qualification-{}-{}",
                    std::process::id(),
                    next()
                ));
                match fs::create_dir(&path) {
                    Ok(()) => return Self(path),
                    Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => continue,
                    Err(err) => panic!("cannot create qualification test directory: {err}"),
                }
            }
        }
    }
    impl Drop for Temporary {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn policy_qualification_round_trips() {
        let temporary = Temporary::new();
        let root_dir = std::env::var_os("RUST027_CAPTURE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| temporary.0.clone());
        let golden = fixture("expected.json");
        for profile in ["default", "mixed"] {
            for mode in ["Serial", "Overlap"] {
                for label in [None, Some("BufferedRequested"), Some("NoCacheRequested")] {
                    let arm = QualificationArm::parse(profile, mode, label).unwrap();
                    let directory =
                        root_dir.join(format!("{profile}-{mode}-{}", label.unwrap_or("Exact")));
                    fs::create_dir(&directory).unwrap();
                    let mut files = ArmFiles::new(&directory);
                    let (driver, log, t) = Synthetic::new(profile, "");
                    let (mut h, s) = arm.setup(&root(), driver).unwrap();
                    let mut steps = Vec::new();
                    let mut replay = Value::Null;
                    for pos in 0..5 {
                        let req = h.backend().book().request(pos).unwrap();
                        let result = h
                            .execute(&req, &s, &s, &t, |_| {
                                if pos == 0 {
                                    Err(ContractError::new(
                                        ErrorCategory::InvalidStateTransition,
                                        "delivery",
                                        "lost fixture delivery",
                                    ))
                                } else {
                                    Ok(())
                                }
                            })
                            .unwrap();
                        let digest = sha256_hex(&result.committed.bytes);
                        let output = &golden["profiles"][profile]["outputs"][pos as usize];
                        assert_eq!(output["bits"], json!(lanes(&result.committed.bytes)));
                        assert_eq!(output["sha256"], digest);
                        assert!(!result.replayed);
                        assert_eq!(result.committed.position, pos + 1);
                        assert_eq!(result.committed.token, 0);
                        assert_eq!(result.delivery_error.is_some(), pos == 0);
                        files.vector(pos, &result.committed.bytes).unwrap();
                        let snapshot = h.backend().snapshot();
                        steps.push(json!({"position":pos,"request":req.id,"token":result.committed.token,
                            "input_reads":s.reads(),"snapshot":snapshot,"peak":h.peak_reservation_bytes(),
                            "active":h.active_reservation_bytes(),"sha256":digest}));
                        if pos == 0 {
                            let before = log.borrow().clone();
                            let policy_sha =
                                label.map(|_| qual::journal_digest(h.backend(), 0).unwrap());
                            let before_records = records(&h);
                            let again = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap();
                            let same = Arc::ptr_eq(&result.committed, &again.committed);
                            assert!(same && again.replayed);
                            assert_eq!(snapshot, h.backend().snapshot());
                            assert_eq!(*log.borrow(), before);
                            assert_eq!(before_records, records(&h));
                            assert_eq!(
                                label.map(|_| qual::journal_digest(h.backend(), 0).unwrap()),
                                policy_sha
                            );
                            assert_eq!(h.state().position(), 1);
                            assert_eq!(s.reads(), 1);
                            replay = json!({"same_commit":same,"lost_delivery":result.delivery_error.is_some(),
                                "position":h.state().position(),"input_reads":s.reads(),"snapshot":snapshot,
                                "driver_retirements":log.borrow().retired,"policy_sha256":policy_sha});
                        }
                    }
                    let (count, journals) = files.records(h.backend()).unwrap();
                    assert_eq!(count, 12);
                    assert_eq!(journals.len(), if label.is_some() { 5 } else { 0 });
                    assert_eq!(log.borrow().retired, 12);
                    let report = json!({"schema":qual::HOST_SCHEMA,"profile":profile,"arm":mode,"policy":label,
                        "ordinal":arm.ordinal(),"book":h.backend().book().digest(),"steps":steps,"replay":replay,
                        "ledger":h.backend().ledger(),"standing":h.backend().working_bytes(),"final":h.backend().snapshot(),
                        "row_count":count,"policy_journals":journals,"payload_before_report":files.bytes()});
                    files.report(&report).unwrap();
                    assert!(files.bytes() <= qual::PAYLOAD_LIMIT);
                    assert_eq!(
                        report,
                        serde_json::from_slice::<Value>(
                            &fs::read(directory.join("report.json")).unwrap()
                        )
                        .unwrap()
                    );
                    for (i, j) in journals.iter().enumerate() {
                        let bytes = fs::read(directory.join(format!("policy-{i}.json"))).unwrap();
                        assert_eq!(bytes, h.backend().policy_journal().nth(i).unwrap());
                        assert_eq!(json!({"bytes":bytes.len(),"sha256":sha256_hex(&bytes)}), *j);
                    }
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn policy_qualification_real_hit_and_failed_compute() {
        use mlx_expert_ranges::residency::overlap::StagedResidency;
        use staged::Policy;
        let tmp = Temporary::new();
        let p = Population::load("mixed").unwrap();
        let (cache, _) = p.open(&root(), Arm::Cached).unwrap();
        let mut r = StagedResidency::with_policy_capacity(
            cache,
            Mode::Serial,
            Policy::BufferedRequested,
            u64::MAX,
            3,
        )
        .unwrap();
        let demand = r.demand(0).unwrap();
        let mut count = 0;
        for expected in [3, 0] {
            r.consume(
                &[demand],
                || false,
                |_| {
                    count += 1;
                    Ok(())
                },
            )
            .unwrap();
            assert_eq!(r.policy_records().len(), expected);
        }
        assert_eq!(count, 2);
        let mut files = ArmFiles::new(&tmp.0);
        files
            .policy_journal(1, &serde_json::to_vec(r.policy_records()).unwrap())
            .unwrap();
        assert_eq!(fs::read(tmp.0.join("policy-1.json")).unwrap(), b"[]");

        let fault_dir = tmp.0.join("failure");
        fs::create_dir(&fault_dir).unwrap();
        let mut files = ArmFiles::new(&fault_dir);
        let arm = QualificationArm::parse("mixed", "Overlap", Some("NoCacheRequested")).unwrap();
        let (driver, _, t) = Synthetic::new("mixed", "double");
        let (mut h, s) = arm.setup(&root(), driver).unwrap();
        let req = h.backend().book().request(0).unwrap();
        let failure = h.execute(&req, &s, &s, &t, |_| Ok(())).unwrap_err();
        assert!(failure.error.message().contains("partial up"));
        assert!(failure
            .cleanup_error
            .unwrap()
            .message()
            .contains("retirement failure"));
        assert!(h.retained().is_none());
        let (_, records) = files.records(h.backend()).unwrap();
        assert_eq!(records.len(), 1);
        assert_eq!(
            fs::read(fault_dir.join("policy-0.json")).unwrap(),
            h.backend().policy_journal().next().unwrap()
        );
    }

    #[test]
    fn policy_qualification_refuses_wrong_pages_and_noncanonical_startup() {
        let hash = "1".repeat(64);
        // Deliberately fabricated observations for the pure codec. No address or binary is produced.
        let images = json!({"test_fixture":true});
        let cap = json!({"schema":"staged-policy-startup/1","run":hash,"ordinal":7,"profile":"mixed",
            "arm":"Overlap","policy":"NoCacheRequested","page_size":16384,"closure_sha256":hash,
            "input_sha256":hash,"reference":hash,"intent_sha256":hash,"source":"1".repeat(40),
            "tree":"1".repeat(40),"binary_sha256":hash,"build_sha256":hash,"images":images});
        let name = "7-mixed-Overlap-NoCacheRequested";
        fn encode(v: &Value, pretty: bool) -> Vec<u8> {
            let mut b = if pretty {
                serde_json::to_vec_pretty(v)
            } else {
                serde_json::to_vec(v)
            }
            .unwrap();
            b.push(b'\n');
            b
        }
        let check = |v: &Value, p, dir: &str| {
            qual::fixed_startup(
                &encode(v, false),
                &encode(v, true),
                dir,
                p,
                &hash,
                &hash,
                &images,
            )
        };
        for page in [4096, 16384] {
            let mut v = cap.clone();
            v["page_size"] = json!(page);
            assert_eq!(check(&v, page, name).unwrap().0.ordinal(), 7);
        }
        for (k, bad) in [
            ("run", json!("1")),
            ("ordinal", json!(7.0)),
            ("source", json!("x".repeat(40))),
            ("schema", json!(qual::HOST_SCHEMA)),
            ("policy", json!("Exact")),
            ("extra", json!(true)),
            ("page_size", json!(8192)),
            ("intent_sha256", json!("0".repeat(64))),
        ] {
            let mut v = cap.clone();
            v[k] = bad;
            assert!(check(&v, 16384, name).is_err(), "{k}");
        }
        assert!(check(&cap, 4096, name).is_err());
        assert!(check(&cap, 16384, "6-mixed-Overlap-BufferedRequested").is_err());
        let wire = encode(&cap, false);
        let duplicate = String::from_utf8(wire)
            .unwrap()
            .replacen("{", r#"{"ordinal":7,"#, 1);
        assert!(qual::fixed_startup(
            duplicate.as_bytes(),
            &encode(&cap, true),
            name,
            16384,
            &hash,
            &hash,
            &images
        )
        .is_err());
    }

    #[test]
    fn policy_qualification_file_limits_and_unknown_progress() {
        let tmp = Temporary::new();
        {
            let occupied = Temporary::under(&tmp.0, || 0);
            let witness = occupied.0.join("owner");
            fs::write(&witness, b"previous owner").unwrap();
            let mut sequence = 0u64..;
            let other = Temporary::under(&tmp.0, || sequence.next().unwrap());
            assert_ne!(occupied.0, other.0);
            drop(other);
            assert_eq!(fs::read(witness).unwrap(), b"previous owner");
        }
        let mut files = ArmFiles::new(&tmp.0);
        assert!(files.vector(0, &[0; 511]).is_err());
        assert!(files
            .policy_journal(0, &vec![0; qual::JOURNAL_SLOT + 1])
            .is_err());
        assert_eq!(files.bytes(), 0);
        assert_eq!(tmp.0.read_dir().unwrap().count(), 0);
        // Deliberately fabricated failure bytes exercise the opaque exporter only.
        let raw=br#"[{"outcome":{"kind":"setup_failure","setup":{"released":2,"live":0,"slots":[{"setter":{"returned":0}},{"fresh_owned":true,"setter":null},null]}}},{"outcome":{"kind":"transfer","receipt":{"effects":[{"attempted":true,"returned_bytes":null,"copied":0}]}}}]"#;
        files.policy_journal(0, raw).unwrap();
        assert_eq!(fs::read(tmp.0.join("policy-0.json")).unwrap(), raw);
        assert!(files.policy_journal(0, b"[]").is_err());
        assert_eq!(fs::read(tmp.0.join("policy-0.json")).unwrap(), raw);
    }
}
