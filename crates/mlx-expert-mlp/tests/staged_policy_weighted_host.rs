//! Real fixed-descriptor reads with the original, owner-thread synthetic Driver.
#[cfg(target_os = "macos")]
mod qualification {
    include!("staged_weighted_host.rs");
    use staged::Policy;

    fn policy_host(
        profile: &str,
        mode: Mode,
        policy: Policy,
        fault: &'static str,
        capacity: Option<u64>,
    ) -> (Host, InputStore, Log, CancellationToken) {
        let (driver, log, token) = Synthetic::new(profile, fault);
        let (host, store) = staged::setup_with_policy(
            &root(),
            profile,
            RouteBook::fixed(profile).unwrap(),
            mode,
            policy,
            driver,
            capacity,
        )
        .unwrap();
        (host, store, log, token)
    }

    fn policy_export(name: &str, report: Value, limit: usize) {
        let Some(dir) = std::env::var_os("STAGED_POLICY_EXPORT") else {
            return;
        };
        let bytes = serde_json::to_vec(&report).unwrap();
        assert!(bytes.len() <= limit);
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(Path::new(&dir).join(format!("{name}.json")))
            .unwrap()
            .write_all(&bytes)
            .unwrap();
    }

    fn policy_rows(host: &Host) -> Vec<Value> {
        host.backend()
            .policy_journal()
            .map(|b| serde_json::from_slice(b).unwrap())
            .collect()
    }

    fn ticket_rows(host: &Host) -> Vec<Value> {
        host.backend()
            .transport_records()
            .map(|b| serde_json::from_slice(b).unwrap())
            .collect()
    }

    #[test]
    fn fixed_policy_eight_weighted_arms() {
        let golden = fixture("expected.json");
        let matrix: Value = serde_json::from_slice(include_bytes!(
            "../../../docs/research/f020/m4c-staged-policy-host/matrix.json"
        ))
        .unwrap();
        for profile in ["default", "mixed"] {
            for mode in [Mode::Serial, Mode::Overlap] {
                for policy in [Policy::BufferedRequested, Policy::NoCacheRequested] {
                    let (mut h, store, log, token) = policy_host(profile, mode, policy, "", None);
                    let ledger = h.backend().ledger().clone();
                    let standing = h.backend().working_bytes();
                    assert_eq!(ledger["W_total"], standing);
                    assert_eq!(
                        h.backend().book().digest(),
                        golden["profiles"][profile]["book"]
                    );
                    let mut replay = Value::Null;
                    let mut steps = Vec::new();
                    for i in 0..5 {
                        let pos = i as u64;
                        let req = h.backend().book().request(pos).unwrap();
                        assert_eq!(
                            h.backend().book().plan_digest(pos).unwrap(),
                            golden["plan_sha256"][i]
                        );
                        let result = h
                            .execute(&req, &store, &store, &token, |_| {
                                if i == 0 {
                                    return Err(ContractError::new(
                                        ErrorCategory::InvalidStateTransition,
                                        "delivery",
                                        "lost delivery",
                                    ));
                                }
                                Ok(())
                            })
                            .unwrap();
                        assert!(!result.replayed);
                        assert_eq!(result.delivery_error.is_some(), i == 0);
                        assert_eq!(result.committed.token, 0);
                        let bits = lanes(&result.committed.bytes);
                        let digest = sha256_hex(&result.committed.bytes);
                        let expected = &golden["profiles"][profile]["outputs"][i];
                        assert_eq!(json!(bits), expected["bits"]);
                        assert_eq!(digest, expected["sha256"]);
                        assert_eq!(h.peak_reservation_bytes(), standing + PEAK[i]);
                        assert_eq!(
                            (h.active_reservations(), h.active_reservation_bytes()),
                            (0, 0)
                        );
                        assert_eq!(h.state().position(), pos + 1);
                        assert_eq!(store.reads(), pos + 1);
                        let snap = h.backend().snapshot();
                        let observed = log.borrow().clone();
                        for (key, target) in [
                            ("weighted", "occurrences"),
                            ("records", "occurrences"),
                            ("fills", "fills"),
                            ("hits", "hits"),
                            ("evictions", "evictions"),
                            ("cache_reads", "logical_attempts"),
                        ] {
                            assert_eq!(snap[key], matrix["cumulative"][target][i], "{key}");
                        }
                        let tickets = ticket_rows(&h);
                        let journal = policy_rows(&h);
                        assert_eq!(tickets.len(), i + 1);
                        assert_eq!(journal.len(), i + 1);
                        assert_eq!(tickets[i]["residents"], matrix["residents"][i]);
                        let role_bytes = serde_json::to_vec(h.backend().policy_records()).unwrap();
                        assert_eq!(h.backend().policy_journal().last().unwrap(), role_bytes);
                        let stamps = &matrix["miss_tickets"][i];
                        let role_count = stamps.as_array().unwrap().len() * 3;
                        assert_eq!(journal[i].as_array().unwrap().len(), role_count);
                        assert_eq!(
                            json!(observed.retired),
                            matrix["cumulative"]["occurrences"][i]
                        );
                        assert_eq!(
                            json!(observed.imports),
                            matrix["cumulative"]["driver_imports"][i]
                        );
                        assert_eq!(
                            json!(observed.projections),
                            matrix["cumulative"]["driver_projections"][i]
                        );
                        assert_eq!(
                            json!(observed.activations),
                            matrix["cumulative"]["driver_activations"][i]
                        );
                        if i == 0 {
                            let occurrences = records(&h);
                            let again =
                                h.execute(&req, &store, &store, &token, |_| Ok(())).unwrap();
                            let same = Arc::ptr_eq(&again.committed, &result.committed);
                            assert!(again.replayed && same);
                            assert_eq!(h.state().position(), pos + 1);
                            assert_eq!(store.reads(), pos + 1);
                            assert_eq!(*log.borrow(), observed);
                            assert_eq!(h.backend().snapshot(), snap);
                            assert_eq!(records(&h), occurrences);
                            assert_eq!(ticket_rows(&h), tickets);
                            assert_eq!(policy_rows(&h), journal);
                            assert_eq!(
                                serde_json::to_vec(h.backend().policy_records()).unwrap(),
                                role_bytes
                            );
                            replay = json!({"lost_delivery":result.delivery_error.is_some(),"same_arc":same,
                                "replayed":again.replayed,"position":h.state().position(),"input_reads":store.reads(),
                                "events":log.borrow().events,"snapshot":h.backend().snapshot(),
                                "role_journal_sha256":sha256_hex(&role_bytes)});
                        }
                        steps.push(json!({"position":pos,"semantic_position":h.state().position(),
                            "request_id":req.id,"input_reads":store.reads(),"token":result.committed.token,
                            "bits":bits,"sha256":digest,"peak":h.peak_reservation_bytes(),"active":h.active_reservation_bytes(),
                            "snapshot":snap,"events":observed.events,"imports":observed.imports,
                            "projections":observed.projections,"activations":observed.activations,
                            "retired":observed.retired,"role_journal_bytes":role_bytes.len(),"role_journal_sha256":sha256_hex(&role_bytes)}));
                    }
                    policy_export(
                        &format!("positive-{profile}-{mode:?}-{policy:?}"),
                        json!({
                        "schema":"staged-policy-host/1","profile":profile,"mode":mode,"policy":policy,"ledger":ledger,
                        "book":h.backend().book().digest(),"steps":steps,"occurrences":records(&h),
                        "transport":ticket_rows(&h),"role_json":h.backend().policy_journal()
                            .map(|b| std::str::from_utf8(b).unwrap()).collect::<Vec<_>>(),"replay":replay}),
                        2 << 20,
                    );
                }
            }
        }
    }

    #[test]
    fn fixed_policy_coordinator_capacity_and_failures() {
        let mut controls = Vec::new();
        for (mode, policy) in [
            (Mode::Serial, Policy::BufferedRequested),
            (Mode::Overlap, Policy::NoCacheRequested),
        ] {
            let w = policy_host("mixed", mode, policy, "", None)
                .0
                .backend()
                .working_bytes();
            for i in [0, 4] {
                let cap = w + PEAK[i] - 1;
                let (mut h, s, log, token) = policy_host("mixed", mode, policy, "", Some(cap));
                for pos in 0..i {
                    let req = h.backend().book().request(pos as u64).unwrap();
                    h.execute(&req, &s, &s, &token, |_| Ok(())).unwrap();
                }
                let before = h.backend().snapshot();
                let journal = policy_rows(&h);
                let prior = log.borrow().clone();
                let req = h.backend().book().request(i as u64).unwrap();
                let failure = h.execute(&req, &s, &s, &token, |_| Ok(())).unwrap_err();
                assert_eq!(s.reads(), i as u64);
                assert_eq!(h.state().position(), i as u64);
                assert_eq!(policy_rows(&h), journal);
                assert_eq!(h.backend().snapshot(), before);
                assert_eq!(*log.borrow(), prior);
                assert_eq!(h.active_reservation_bytes(), 0);
                controls.push(json!({"kind":"short","mode":mode,"policy":policy,"position":i,
                    "capacity":cap,"standing":w,"input_reads":s.reads(),"active":h.active_reservation_bytes(),
                    "error":failure.error.code(),"role_rows":journal.len()}));
            }
            let (mut h, s, log, token) = policy_host("mixed", mode, policy, "double", None);
            let req = h.backend().book().request(0).unwrap();
            let fault = h.execute(&req, &s, &s, &token, |_| Ok(())).unwrap_err();
            assert!(fault.error.message().contains("partial up"));
            let cleanup = fault.cleanup_error.as_ref().unwrap().message();
            assert!(cleanup.contains("retirement failure"));
            let snap = h.backend().snapshot();
            assert_eq!(snap["quarantined"], true);
            assert_eq!(snap["weighted"], 0);
            assert_eq!(snap["activity"]["joined"], 1);
            assert_eq!(snap["activity"]["banks_home"], true);
            assert_eq!(snap["activity"]["outstanding"], false);
            assert!(h.retained().is_none());
            assert_eq!(h.state().position(), 0);
            assert_eq!(h.active_reservation_bytes(), 0);
            let rows = policy_rows(&h);
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0].as_array().unwrap().len(), 3);
            controls.push(
                json!({"kind":"double","mode":mode,"policy":policy,"position":h.state().position(),
                "events":log.borrow().events,"primary":fault.error.message(),"cleanup":cleanup,
                "snapshot":snap,"roles":rows,"active":h.active_reservation_bytes()}),
            );
        }
        policy_export("controls", json!(controls), 1 << 20);
    }
}
