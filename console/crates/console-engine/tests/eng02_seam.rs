//! ENG-02: the scripted engine and its test doubles behind the backend seam of
//! `console_core::engine`, as a server drives them: factories that cross threads, an
//! instance started and used on one driver thread, generations through the ledger, the
//! synthetic-only guard before serving, a restart after a death, and the submit-and-pump
//! form. These tests are written for this package; no donor test exercises the engine
//! alone. The tests sit in a module named `fake` so that `cargo test -p console-engine
//! fake` runs them.

mod fake {
    use std::sync::mpsc;
    use std::sync::Arc;
    use std::time::{Duration, Instant};

    use console_core::engine::{
        generate_ledgered, generate_one, require_synthetic, ControlHandle, DeliveryRefused,
        EngineEvent, EngineFactory, EngineFailure, EngineStartConfig, EngineStop, EventSink,
        FailureKind, GenerationRequest, Health, LedgerCounts, Provenance, RequestId, Terminal,
    };
    use console_engine::fake::doubles::{
        BrokenEngine, BudgetEngine, ClockedEngine, DyingEngine, ErrEngine, HalfDeadEngine,
        HeldEngine, LifecycleEngine, LpEngine, NonFiniteEngine, NotSyntheticEngine, PacedEngine,
        PausingEngine, ResumingEngine,
    };
    use console_engine::fake::{
        FakeFactory, FakeScript, ManualClock, DEFAULT_MODEL_NAME, DEFAULT_SCRIPT_TEXT,
    };

    fn assert_factory<T: EngineFactory + Clone + Send + Sync + 'static>() {}

    #[derive(Default)]
    struct Tokens(Vec<u32>);

    impl EventSink for Tokens {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            if let EngineEvent::Token(t) = event {
                self.0.push(t.id);
            }
            Ok(())
        }
    }

    fn script() -> FakeScript {
        FakeScript::new(vec![10, 11, 12, 13])
    }

    /// Starts `factory` on a driver thread, refuses it unless it is synthetic, and runs
    /// one generation of `req` there, as the server does.
    fn serve_once(
        factory: Arc<dyn EngineFactory>,
        req: GenerationRequest,
    ) -> Result<(Vec<u32>, Terminal, LedgerCounts), EngineFailure> {
        let (tx, rx) = mpsc::channel();
        let driver = std::thread::spawn(move || {
            let out = (|| {
                let mut engine = factory.start(&EngineStartConfig::new())?;
                if let Err(refused) = require_synthetic(engine.descriptor()) {
                    engine.shutdown(Instant::now());
                    return Err(refused.to_failure());
                }
                let h = ControlHandle::new();
                let mut sink = Tokens::default();
                let (t, c) = generate_ledgered(engine.as_mut(), &req, &h.probe(), &mut sink)?;
                engine.shutdown(Instant::now());
                Ok((sink.0, t, c))
            })();
            let _ = tx.send(out);
        });
        let out = rx
            .recv_timeout(Duration::from_secs(30))
            .unwrap_or_else(|_| Err(EngineFailure::died("the driver thread did not answer")));
        let _ = driver.join();
        out
    }

    #[test]
    fn factories_cross_threads() {
        assert_factory::<FakeFactory>();
        assert_factory::<DyingEngine>();
        assert_factory::<NonFiniteEngine>();
        assert_factory::<HalfDeadEngine>();
        assert_factory::<ErrEngine>();
        assert_factory::<BrokenEngine>();
        assert_factory::<ClockedEngine>();
        assert_factory::<PacedEngine>();
        assert_factory::<LpEngine>();
        assert_factory::<LifecycleEngine>();
        assert_factory::<HeldEngine>();
        assert_factory::<BudgetEngine>();
        assert_factory::<ResumingEngine>();
        assert_factory::<PausingEngine>();
        assert_factory::<NotSyntheticEngine>();
    }

    #[test]
    fn the_scripted_engine_serves_on_its_driver_thread() {
        let f = script().build().expect("valid");
        let probe = f.probe();
        let (tokens, t, counts) = serve_once(
            Arc::new(f),
            GenerationRequest::new(RequestId(1), vec![1, 2], 3),
        )
        .expect("serves");
        assert_eq!(tokens, vec![10, 11, 12]);
        assert_eq!(t.stop, EngineStop::Length);
        assert_eq!((counts.prompt_tokens, counts.completion_tokens), (2, 3));
        assert_eq!(probe.last_prompt(), Some(vec![1, 2]));
    }

    #[test]
    fn every_double_but_one_is_synthetic_and_admitted() {
        let factories: Vec<(&str, Arc<dyn EngineFactory>)> = vec![
            ("FakeFactory", Arc::new(script().build().expect("valid"))),
            (
                "DyingEngine",
                Arc::new(DyingEngine::new(script()).expect("valid")),
            ),
            (
                "NonFiniteEngine",
                Arc::new(NonFiniteEngine::new(script(), vec![]).expect("valid")),
            ),
            (
                "HalfDeadEngine",
                Arc::new(HalfDeadEngine::new(script()).expect("valid")),
            ),
            (
                "ErrEngine",
                Arc::new(ErrEngine::new(script()).expect("valid")),
            ),
            (
                "BrokenEngine",
                Arc::new(BrokenEngine::new(script()).expect("valid")),
            ),
            (
                "ClockedEngine",
                Arc::new(ClockedEngine::new(script()).expect("valid")),
            ),
            (
                "PacedEngine",
                Arc::new(PacedEngine::new(script()).expect("valid")),
            ),
            (
                "LpEngine",
                Arc::new(LpEngine::new(script()).expect("valid")),
            ),
            (
                "LifecycleEngine",
                Arc::new(LifecycleEngine::new(script()).expect("valid")),
            ),
            (
                "BudgetEngine",
                Arc::new(BudgetEngine::new(vec![1], vec![2], 3).expect("valid")),
            ),
            (
                "ResumingEngine",
                Arc::new(ResumingEngine::new(vec![(vec![], vec![5])], vec![6]).expect("valid")),
            ),
            (
                "PausingEngine",
                Arc::new(ResumingEngine::pausing(vec![(vec![], vec![5])], vec![6]).expect("valid")),
            ),
        ];
        for (name, f) in factories {
            let e = f.start(&EngineStartConfig::new()).expect("starts");
            assert_eq!(e.descriptor().provenance, Provenance::Synthetic, "{name}");
            assert!(require_synthetic(e.descriptor()).is_ok(), "{name}");
            e.shutdown(Instant::now());
        }
    }

    #[test]
    fn the_not_synthetic_double_is_refused_before_it_serves() {
        for f in [
            NotSyntheticEngine::declaring("a real model"),
            NotSyntheticEngine::undeclared(),
        ] {
            let err = serve_once(
                Arc::new(f.clone()),
                GenerationRequest::new(RequestId(1), vec![1], 4),
            )
            .expect_err("refused");
            assert_eq!(err.kind, FailureKind::StartFailed);
            assert!(err.poisoned);
            assert!(err
                .to_string()
                .contains("docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md"));
            assert_eq!(f.starts(), 1);
            assert_eq!(f.shutdowns(), 1, "the refused engine is closed");
            assert_eq!(f.generate_calls(), 0, "and never served");
        }
    }

    #[test]
    fn the_decided_names_hold() {
        // Deviation PLAN-2: the scripted engine's default model name (owner decision of
        // 2026-11-14, OPEN-03).
        assert_eq!(DEFAULT_MODEL_NAME, "pulsar-console-synthetic");
        assert!(DEFAULT_SCRIPT_TEXT.ends_with("Hello from the mock engine."));
    }

    #[test]
    fn a_dead_engine_is_restarted_by_shutdown_and_start() {
        let f = DyingEngine::new(FakeScript::new((0..20).collect())).expect("valid");
        let h = ControlHandle::new();
        let req = GenerationRequest::new(RequestId(1), vec![1], 50);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let err = generate_ledgered(e.as_mut(), &req, &h.probe(), &mut Tokens::default())
            .expect_err("dies");
        assert_eq!(err.kind, FailureKind::Died);
        assert!(err.poisoned);
        assert!(matches!(
            e.health(),
            Health::Ended {
                exit_code: Some(-9),
                ..
            }
        ));
        e.shutdown(Instant::now());
        let mut e = f.start(&EngineStartConfig::new()).expect("restarts");
        require_synthetic(e.descriptor()).expect("still synthetic");
        let req = GenerationRequest::new(RequestId(2), vec![1], 50);
        let (_, counts) = generate_ledgered(e.as_mut(), &req, &h.probe(), &mut Tokens::default())
            .expect("answers");
        assert_eq!(counts.completion_tokens, 20);
        assert_eq!(f.restarts(), 1);
    }

    #[test]
    fn a_context_reload_restarts_with_the_new_context() {
        let clock = ManualClock::new();
        let f = FakeScript::new(vec![1])
            .reload_delay(Duration::from_secs(2))
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        let e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().max_context, 32_768);
        e.shutdown(Instant::now());
        let e = f
            .start(&EngineStartConfig::new().with_context(16_384))
            .expect("reloads");
        assert_eq!(e.descriptor().max_context, 16_384);
        assert_eq!(clock.sleeps(), vec![Duration::from_secs(2)]);
    }

    #[test]
    fn a_multi_place_double_also_runs_one_blocking_generation() {
        let f = ResumingEngine::new(vec![(vec![], vec![5, 6, 7])], vec![9])
            .expect("valid")
            .delay(Duration::ZERO)
            .places(4);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().caps.places(), 4);
        let h = ControlHandle::new();
        let req = GenerationRequest::new(RequestId(3), vec![1], 10);
        let mut sink = Tokens::default();
        let m = e.multi().expect("four places");
        let t =
            generate_one(m, &req, &h.probe(), &mut sink, Duration::from_millis(1)).expect("runs");
        assert_eq!(t.stop, EngineStop::Stop { token: None });
        assert_eq!(sink.0, vec![5, 6, 7, 9]);
        // And the blocking form of the instance itself.
        let mut sink = Tokens::default();
        let req = GenerationRequest::new(RequestId(4), vec![2], 2);
        let (t, _) = generate_ledgered(e.as_mut(), &req, &h.probe(), &mut sink).expect("runs");
        assert_eq!(t.stop, EngineStop::Length);
        assert_eq!(sink.0, vec![5, 6]);
    }

    #[test]
    fn a_held_engine_blocks_its_driver_until_released() {
        let f = HeldEngine::new(FakeScript::new(vec![3, 4])).expect("valid");
        let (tx, rx) = mpsc::channel();
        let driver = {
            let f = f.clone();
            std::thread::spawn(move || {
                let mut e = f.start(&EngineStartConfig::new()).expect("starts");
                let h = ControlHandle::new();
                let mut sink = Tokens::default();
                let req = GenerationRequest::new(RequestId(1), vec![1], 8);
                let out = generate_ledgered(e.as_mut(), &req, &h.probe(), &mut sink);
                let _ = tx.send((sink.0, out.map(|(t, _)| t.stop)));
            })
        };
        assert!(f.wait_held(Duration::from_secs(10)));
        assert!(
            rx.try_recv().is_err(),
            "nothing is answered while the engine is held"
        );
        f.release();
        let (tokens, stop) = rx.recv_timeout(Duration::from_secs(10)).expect("answers");
        assert_eq!(tokens, vec![3, 4]);
        assert_eq!(stop, Ok(EngineStop::Stop { token: None }));
        driver.join().expect("joins");
    }
}
