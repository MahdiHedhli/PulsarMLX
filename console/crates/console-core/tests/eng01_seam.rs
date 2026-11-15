//! ENG-01: the shape of the backend seam (contract sections 4, 8, 11 and 4.1): a
//! `Send + Sync` factory, an instance that is not `Send` and lives on its driver thread,
//! control through a probe, the ledgered generation, and the submit-and-pump form for
//! engines with several places. The engines here are synthetic test engines written for
//! these tests. No donor test exercises the seam alone.

use std::cell::Cell;
use std::collections::VecDeque;
use std::rc::Rc;
use std::sync::mpsc;
use std::sync::Arc;
use std::time::{Duration, Instant};

use console_core::engine::{
    generate_ledgered, generate_one, require_synthetic, CommittedToken, ControlHandle,
    ControlProbe, DeliveryRefused, EngineDescriptor, EngineEvent, EngineFactory, EngineFailure,
    EngineInstance, EngineKind, EngineStartConfig, EngineStop, EventSink, FailureKind, Finished,
    GenerationRequest, Health, LedgerSet, MultiEngine, Provenance, RequestId, ShutdownOutcome,
    TaggedSink, Terminal,
};

fn assert_send_sync<T: Send + Sync + 'static>() {}

#[test]
fn shared_types_cross_threads() {
    assert_send_sync::<ControlProbe>();
    assert_send_sync::<ControlHandle>();
    assert_send_sync::<GenerationRequest>();
    assert_send_sync::<EngineDescriptor>();
    assert_send_sync::<EngineEvent>();
    assert_send_sync::<EngineFailure>();
    assert_send_sync::<Terminal>();
    assert_send_sync::<Box<dyn EngineFactory>>();
    assert_send_sync::<Arc<dyn EngineFactory>>();
}

// ---------------------------------------------------------------- a single-place engine

/// A synthetic engine that writes `script` one token per step, checks cancel before each
/// step, and, like the engine track's coordinator, offers a refused token again and may
/// deliver the last accepted token a second time. Its `Rc` state makes it not `Send`.
struct StepEngine {
    desc: EngineDescriptor,
    script: Vec<u32>,
    calls: Rc<Cell<u32>>,
    replay_every_token: bool,
}

impl StepEngine {
    fn new(script: Vec<u32>, max_context: u32) -> Self {
        let mut desc = EngineDescriptor::new(EngineKind::CoordinatorAdapter, Provenance::Synthetic);
        desc.max_context = max_context;
        desc.vocab_size = Some(1000);
        desc.caps.stop = true;
        Self {
            desc,
            script,
            calls: Rc::new(Cell::new(0)),
            replay_every_token: false,
        }
    }
}

/// Offers `event` until it is not refused with `Backpressure`.
fn offer(sink: &mut dyn EventSink, event: EngineEvent) -> Result<(), DeliveryRefused> {
    loop {
        match sink.deliver(event.clone()) {
            Err(DeliveryRefused::Backpressure) => continue,
            other => return other,
        }
    }
}

impl EngineInstance for StepEngine {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.calls.set(self.calls.get() + 1);
        let admitted = EngineEvent::Admitted {
            prompt_tokens: req.prompt.len() as u32,
            reused_tokens: None,
        };
        if offer(sink, admitted).is_err() {
            return Ok(Terminal::bare(EngineStop::Cancelled));
        }
        let steps = self.script.iter().take(req.max_new as usize);
        for (i, &id) in steps.enumerate() {
            if control.is_cancelled() {
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
            let t = EngineEvent::Token(CommittedToken {
                index: i as u32,
                position: req.prompt.len() as u64 + i as u64,
                id,
                logprob: None,
            });
            if offer(sink, t.clone()).is_err() {
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
            if self.replay_every_token && offer(sink, t).is_err() {
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
        }
        if self.script.len() > req.max_new as usize {
            Ok(Terminal::bare(EngineStop::Length))
        } else {
            let end = self.script.last().copied();
            Ok(Terminal::bare(EngineStop::Stop { token: end }))
        }
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

struct StepFactory {
    script: Vec<u32>,
}

impl EngineFactory for StepFactory {
    fn kind(&self) -> EngineKind {
        EngineKind::CoordinatorAdapter
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(StepEngine::new(
            self.script.clone(),
            cfg.context.unwrap_or(4096),
        )))
    }
}

#[derive(Default)]
struct Collect {
    got: Vec<EngineEvent>,
}

impl EventSink for Collect {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        self.got.push(event);
        Ok(())
    }
}

fn ids(events: &[EngineEvent]) -> Vec<u32> {
    events
        .iter()
        .filter_map(|e| match e {
            EngineEvent::Token(t) => Some(t.id),
            _ => None,
        })
        .collect()
}

#[test]
fn a_ledgered_generation_returns_terminal_and_usage() {
    let factory: Box<dyn EngineFactory> = Box::new(StepFactory {
        script: vec![5, 6, 7, 2],
    });
    let mut engine = factory
        .start(&EngineStartConfig::new().with_context(8192))
        .expect("start");
    assert_eq!(engine.descriptor().max_context, 8192);
    require_synthetic(engine.descriptor()).expect("synthetic");
    let req = GenerationRequest::new(RequestId(1), vec![1, 2, 3], 16);
    let mut out = Collect::default();
    let (t, counts) = generate_ledgered(
        engine.as_mut(),
        &req,
        &ControlHandle::new().probe(),
        &mut out,
    )
    .expect("generation");
    assert_eq!(t.stop, EngineStop::Stop { token: Some(2) });
    assert_eq!(ids(&out.got), vec![5, 6, 7, 2]);
    assert_eq!(counts.prompt_tokens, 3);
    assert_eq!(counts.completion_tokens, 4);
    assert_eq!(engine.health(), Health::Alive);
    assert_eq!(
        engine.command(&console_core::engine::ControlCommand {
            line: "VLEND 1".into(),
            expect: "OK".into(),
            timeout: Duration::from_secs(1),
        }),
        Err(EngineFailure::unsupported("command"))
    );
    assert_eq!(engine.use_layout(None), Ok(()));
    assert!(engine.sample().is_none());
    assert!(engine.multi().is_none());
    assert_eq!(engine.shutdown(Instant::now()), ShutdownOutcome::Graceful);
}

#[test]
fn max_new_cuts_the_script_and_reports_length() {
    let mut engine = StepEngine::new(vec![5, 6, 7, 2], 4096);
    let req = GenerationRequest::new(RequestId(2), vec![1], 2);
    let mut out = Collect::default();
    let (t, counts) = generate_ledgered(&mut engine, &req, &ControlHandle::new().probe(), &mut out)
        .expect("generation");
    assert_eq!(t.stop, EngineStop::Length);
    assert_eq!(ids(&out.got), vec![5, 6]);
    assert_eq!(counts.completion_tokens, 2);
}

#[test]
fn a_starting_engine_is_refused_before_generate_is_called() {
    let mut engine = StepEngine::new(vec![5], 0);
    let calls = Rc::clone(&engine.calls);
    let req = GenerationRequest::new(RequestId(3), vec![1], 4);
    let mut out = Collect::default();
    let f = generate_ledgered(&mut engine, &req, &ControlHandle::new().probe(), &mut out)
        .expect_err("not ready");
    assert_eq!(f.kind, FailureKind::NotReady);
    assert_eq!(
        f.to_string(),
        "the model is starting; try again in a moment"
    );
    assert_eq!(calls.get(), 0);
    assert!(out.got.is_empty());
}

#[test]
fn replays_after_refused_deliveries_reach_the_consumer_once() {
    /// Refuses every other delivery with `Backpressure`.
    struct Flaky {
        n: u32,
        got: Vec<EngineEvent>,
    }
    impl EventSink for Flaky {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            self.n += 1;
            if self.n.is_multiple_of(2) {
                return Err(DeliveryRefused::Backpressure);
            }
            self.got.push(event);
            Ok(())
        }
    }
    let mut engine = StepEngine::new((10..30).collect(), 4096);
    engine.replay_every_token = true;
    let req = GenerationRequest::new(RequestId(4), vec![1, 2], 64);
    let mut out = Flaky {
        n: 0,
        got: Vec::new(),
    };
    let (_, counts) = generate_ledgered(&mut engine, &req, &ControlHandle::new().probe(), &mut out)
        .expect("generation");
    assert_eq!(ids(&out.got), (10..30).collect::<Vec<_>>());
    assert_eq!(counts.completion_tokens, 20);
}

#[test]
fn a_gone_consumer_ends_the_generation_cancelled() {
    struct GoneAfter(u32, Vec<EngineEvent>);
    impl EventSink for GoneAfter {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            if self.1.len() as u32 >= self.0 {
                return Err(DeliveryRefused::ConsumerGone);
            }
            self.1.push(event);
            Ok(())
        }
    }
    let mut engine = StepEngine::new((10..30).collect(), 4096);
    let req = GenerationRequest::new(RequestId(5), vec![1], 64);
    let mut out = GoneAfter(3, Vec::new());
    let (t, counts) = generate_ledgered(&mut engine, &req, &ControlHandle::new().probe(), &mut out)
        .expect("a refused delivery never turns a committed step into a failure");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(
        counts.completion_tokens, 2,
        "Admitted and two tokens were taken"
    );
}

#[test]
fn the_instance_lives_on_its_driver_thread_and_cancel_arrives_through_the_probe() {
    // The factory crosses to the driver thread; the instance is created there and never
    // leaves it. The server side holds only the control handle and a channel.
    let factory: Arc<dyn EngineFactory> = Arc::new(StepFactory {
        script: (100..200).collect(),
    });
    let handle = ControlHandle::new();
    let probe = handle.probe();
    let (tok_tx, tok_rx) = mpsc::sync_channel::<u32>(0);
    let (ack_tx, ack_rx) = mpsc::channel::<()>();

    /// Hands each token to the server and waits for its acknowledgement, so the test
    /// decides exactly when the cancel lands.
    struct Relay {
        tx: mpsc::SyncSender<u32>,
        ack: mpsc::Receiver<()>,
    }
    impl EventSink for Relay {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            if let EngineEvent::Token(t) = event {
                self.tx
                    .send(t.id)
                    .map_err(|_| DeliveryRefused::ConsumerGone)?;
                self.ack.recv().map_err(|_| DeliveryRefused::ConsumerGone)?;
            }
            Ok(())
        }
    }

    let driver = std::thread::spawn(move || {
        let mut engine = factory.start(&EngineStartConfig::new()).expect("start");
        require_synthetic(engine.descriptor()).expect("synthetic");
        let req = GenerationRequest::new(RequestId(6), vec![1, 2, 3], 1000);
        let mut relay = Relay {
            tx: tok_tx,
            ack: ack_rx,
        };
        let result = generate_ledgered(engine.as_mut(), &req, &probe, &mut relay);
        let outcome = engine.shutdown(Instant::now() + Duration::from_secs(1));
        (result, outcome)
    });

    let mut seen = Vec::new();
    while let Ok(id) = tok_rx.recv() {
        seen.push(id);
        if seen.len() == 2 {
            handle.cancel();
        }
        if ack_tx.send(()).is_err() {
            break;
        }
    }
    let (result, outcome) = driver.join().expect("driver thread");
    let (t, counts) = result.expect("generation");
    assert_eq!(seen, vec![100, 101]);
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 2);
    assert_eq!(outcome, ShutdownOutcome::Graceful);
}

// ---------------------------------------------------------------- several places

struct Running {
    rid: RequestId,
    prompt_len: usize,
    script: Vec<u32>,
    max_new: usize,
    next: usize,
    admitted: bool,
    control: ControlProbe,
}

/// A synthetic multi-conversation engine: each pump writes one step for every running
/// generation in submission order. A generation refused with `Backpressure` holds its
/// step; one refused with `ConsumerGone` or cancelled finishes `Cancelled`.
struct MultiStep {
    places: usize,
    script: Vec<u32>,
    running: VecDeque<Running>,
    die_after_pumps: Option<u32>,
    pumps: u32,
}

impl MultiStep {
    fn new(places: usize, script: Vec<u32>) -> Self {
        Self {
            places,
            script,
            running: VecDeque::new(),
            die_after_pumps: None,
            pumps: 0,
        }
    }
}

impl MultiEngine for MultiStep {
    fn submit(
        &mut self,
        req: &GenerationRequest,
        control: ControlProbe,
    ) -> Result<(), EngineFailure> {
        if self.running.iter().any(|r| r.rid == req.rid) {
            return Err(EngineFailure::protocol("request id already running"));
        }
        if self.running.len() >= self.places {
            return Err(EngineFailure::unsupported("no free place"));
        }
        self.running.push_back(Running {
            rid: req.rid,
            prompt_len: req.prompt.len(),
            script: self
                .script
                .iter()
                .map(|t| t + req.rid.0 as u32 * 1000)
                .collect(),
            max_new: req.max_new as usize,
            next: 0,
            admitted: false,
            control,
        });
        Ok(())
    }

    fn pump(
        &mut self,
        sink: &mut dyn TaggedSink,
        _wait: Duration,
    ) -> Result<Vec<Finished>, EngineFailure> {
        self.pumps += 1;
        if self.die_after_pumps.is_some_and(|n| self.pumps > n) {
            self.running.clear();
            return Err(EngineFailure::stopped_unexpectedly(Some(9)));
        }
        let mut finished = Vec::new();
        let mut keep = VecDeque::new();
        while let Some(mut r) = self.running.pop_front() {
            let end = |r: &Running, stop| Finished {
                rid: r.rid,
                outcome: Ok(Terminal::bare(stop)),
            };
            if r.control.is_cancelled() {
                finished.push(end(&r, EngineStop::Cancelled));
                continue;
            }
            let event = if !r.admitted {
                EngineEvent::Admitted {
                    prompt_tokens: r.prompt_len as u32,
                    reused_tokens: None,
                }
            } else if r.next >= r.max_new.min(r.script.len()) {
                let stop = if r.script.len() > r.max_new {
                    EngineStop::Length
                } else {
                    EngineStop::Stop { token: None }
                };
                finished.push(end(&r, stop));
                continue;
            } else {
                EngineEvent::Token(CommittedToken {
                    index: r.next as u32,
                    position: (r.prompt_len + r.next) as u64,
                    id: r.script[r.next],
                    logprob: None,
                })
            };
            match sink.deliver(r.rid, event) {
                Ok(()) => {
                    if r.admitted {
                        r.next += 1;
                    } else {
                        r.admitted = true;
                    }
                    keep.push_back(r);
                }
                Err(DeliveryRefused::Backpressure) => keep.push_back(r),
                Err(DeliveryRefused::ConsumerGone) => finished.push(end(&r, EngineStop::Cancelled)),
            }
        }
        self.running = keep;
        Ok(finished)
    }

    fn running(&self) -> usize {
        self.running.len()
    }
}

/// Records tagged events per request id; refuses one id's deliveries a set number of
/// times with `Backpressure`.
#[derive(Default)]
struct Tagged {
    got: Vec<(RequestId, EngineEvent)>,
    refuse: Option<(RequestId, u32)>,
}

impl TaggedSink for Tagged {
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused> {
        if let Some((r, n)) = &mut self.refuse {
            if *r == rid && *n > 0 {
                *n -= 1;
                return Err(DeliveryRefused::Backpressure);
            }
        }
        self.got.push((rid, event));
        Ok(())
    }
}

impl Tagged {
    fn ids_of(&self, rid: RequestId) -> Vec<u32> {
        self.got
            .iter()
            .filter(|(r, _)| *r == rid)
            .filter_map(|(_, e)| match e {
                EngineEvent::Token(t) => Some(t.id),
                _ => None,
            })
            .collect()
    }
}

fn desc_multi(places: u32) -> EngineDescriptor {
    let mut d = EngineDescriptor::new(EngineKind::LineProtocol, Provenance::Synthetic);
    d.max_context = 4096;
    d.caps.multi = Some(places);
    d
}

type Outcome = Result<(Terminal, console_core::engine::LedgerCounts), EngineFailure>;

/// Pumps until every open generation finished, closing each through the ledger set.
fn drive(
    engine: &mut MultiStep,
    ledgers: &mut LedgerSet,
    out: &mut Tagged,
) -> Vec<(RequestId, Outcome)> {
    let mut results = Vec::new();
    for _ in 0..10_000 {
        if ledgers.is_empty() {
            return results;
        }
        let finished = {
            let mut sink = ledgers.sink(out);
            engine.pump(&mut sink, Duration::from_millis(1))
        };
        match finished {
            Ok(done) => {
                for f in done {
                    let rid = f.rid;
                    results.push((rid, ledgers.finish(f)));
                }
            }
            Err(e) => {
                for (rid, f) in ledgers.fail_all(&e) {
                    results.push((rid, Err(f)));
                }
            }
        }
    }
    panic!("the engine never finished");
}

#[test]
fn interleaved_generations_are_tagged_and_ledgered_per_request() {
    let d = desc_multi(3);
    let mut engine = MultiStep::new(d.caps.places() as usize, vec![1, 2, 3, 4]);
    let mut ledgers = LedgerSet::new(d.caps.places());
    let handles: Vec<ControlHandle> = (0..3).map(|_| ControlHandle::new()).collect();
    for (i, h) in handles.iter().enumerate() {
        let req = GenerationRequest::new(RequestId(i as u64 + 1), vec![0; i + 1], 3 + i as u32);
        ledgers.open(&req, &d).expect("open");
        engine.submit(&req, h.probe()).expect("submit");
    }
    let mut out = Tagged {
        refuse: Some((RequestId(2), 3)),
        ..Tagged::default()
    };
    let results = drive(&mut engine, &mut ledgers, &mut out);
    assert_eq!(results.len(), 3);
    assert_eq!(out.ids_of(RequestId(1)), vec![1001, 1002, 1003]);
    assert_eq!(out.ids_of(RequestId(2)), vec![2001, 2002, 2003, 2004]);
    assert_eq!(out.ids_of(RequestId(3)), vec![3001, 3002, 3003, 3004]);
    for (rid, r) in results {
        let (t, counts) = r.unwrap_or_else(|f| panic!("{rid}: {f}"));
        match rid.0 {
            1 => {
                assert_eq!(t.stop, EngineStop::Length);
                assert_eq!(counts.completion_tokens, 3);
            }
            _ => {
                assert_eq!(t.stop, EngineStop::Stop { token: None });
                assert_eq!(counts.completion_tokens, 4);
                assert_eq!(counts.prompt_tokens as u64, rid.0);
            }
        }
    }
    assert!(ledgers.is_empty());
    assert_eq!(engine.running(), 0);
    // The events of different requests interleave.
    let first_rids: Vec<u64> = out.got.iter().take(3).map(|(r, _)| r.0).collect();
    assert_eq!(
        first_rids,
        vec![1, 3, 1],
        "request 2 was held by backpressure"
    );
}

#[test]
fn a_cancel_reaches_only_its_own_generation() {
    let d = desc_multi(2);
    let mut engine = MultiStep::new(2, (1..50).collect());
    let mut ledgers = LedgerSet::new(2);
    let a = ControlHandle::new();
    let b = ControlHandle::new();
    let ra = GenerationRequest::new(RequestId(1), vec![0], 40);
    let rb = GenerationRequest::new(RequestId(2), vec![0], 5);
    ledgers.open(&ra, &d).expect("open a");
    ledgers.open(&rb, &d).expect("open b");
    engine.submit(&ra, a.probe()).expect("submit a");
    engine.submit(&rb, b.probe()).expect("submit b");
    let mut out = Tagged::default();
    {
        let mut sink = ledgers.sink(&mut out);
        engine.pump(&mut sink, Duration::ZERO).expect("pump");
        engine.pump(&mut sink, Duration::ZERO).expect("pump");
    }
    a.cancel();
    let results = drive(&mut engine, &mut ledgers, &mut out);
    let mut by_rid: Vec<_> = results
        .into_iter()
        .map(|(rid, r)| (rid.0, r.expect("ok").0.stop))
        .collect();
    by_rid.sort_by_key(|(r, _)| *r);
    assert_eq!(
        by_rid,
        vec![(1, EngineStop::Cancelled), (2, EngineStop::Length)]
    );
    assert_eq!(out.ids_of(RequestId(1)), vec![1001]);
    assert_eq!(out.ids_of(RequestId(2)).len(), 5);
}

#[test]
fn submissions_beyond_places_or_with_a_running_id_are_refused() {
    let d = desc_multi(2);
    let mut engine = MultiStep::new(2, vec![1]);
    let mut ledgers = LedgerSet::new(2);
    let r1 = GenerationRequest::new(RequestId(1), vec![0], 4);
    let r2 = GenerationRequest::new(RequestId(2), vec![0], 4);
    let r3 = GenerationRequest::new(RequestId(3), vec![0], 4);
    ledgers.open(&r1, &d).expect("1");
    assert_eq!(
        ledgers.open(&r1, &d).expect_err("duplicate").kind,
        FailureKind::Protocol
    );
    ledgers.open(&r2, &d).expect("2");
    assert_eq!(
        ledgers.open(&r3, &d).expect_err("beyond places").kind,
        FailureKind::Unsupported
    );
    assert_eq!(ledgers.len(), 2);
    engine.submit(&r1, ControlHandle::new().probe()).expect("1");
    assert!(engine.submit(&r1, ControlHandle::new().probe()).is_err());
    engine.submit(&r2, ControlHandle::new().probe()).expect("2");
    assert!(engine.submit(&r3, ControlHandle::new().probe()).is_err());
    assert_eq!(engine.running(), 2);
}

#[test]
fn events_for_a_request_that_is_not_open_are_dropped() {
    let d = desc_multi(1);
    let mut ledgers = LedgerSet::new(1);
    let req = GenerationRequest::new(RequestId(1), vec![0], 4);
    ledgers.open(&req, &d).expect("open");
    let mut out = Tagged::default();
    let mut sink = ledgers.sink(&mut out);
    let stray = EngineEvent::Admitted {
        prompt_tokens: 1,
        reused_tokens: None,
    };
    assert_eq!(sink.deliver(RequestId(99), stray.clone()), Ok(()));
    assert_eq!(sink.deliver(RequestId(1), stray), Ok(()));
    assert_eq!(out.got.len(), 1);
    assert_eq!(out.got[0].0, RequestId(1));
}

#[test]
fn finishing_a_request_that_is_not_open_is_a_protocol_failure() {
    let mut ledgers = LedgerSet::new(1);
    let f = ledgers
        .finish(Finished {
            rid: RequestId(5),
            outcome: Ok(Terminal::bare(EngineStop::Length)),
        })
        .expect_err("not open");
    assert_eq!(f.kind, FailureKind::Protocol);
}

#[test]
fn an_engine_wide_failure_ends_every_running_generation() {
    let d = desc_multi(2);
    let mut engine = MultiStep::new(2, (1..50).collect());
    engine.die_after_pumps = Some(3);
    let mut ledgers = LedgerSet::new(2);
    for rid in 1..=2 {
        let req = GenerationRequest::new(RequestId(rid), vec![0], 40);
        ledgers.open(&req, &d).expect("open");
        engine
            .submit(&req, ControlHandle::new().probe())
            .expect("submit");
    }
    let mut out = Tagged::default();
    let results = drive(&mut engine, &mut ledgers, &mut out);
    assert_eq!(results.len(), 2);
    for (rid, r) in results {
        let f = r.expect_err("died");
        assert_eq!(f.kind, FailureKind::Died, "{rid}");
        assert!(f.poisoned);
        assert_eq!(
            f.after_tokens, 2,
            "Admitted, then two tokens in three pumps"
        );
    }
    assert!(ledgers.is_empty());
}

#[test]
fn a_ledger_fault_in_one_generation_stops_only_that_one() {
    /// Writes request 1's tokens with a gap; request 2's are fine.
    struct Gappy(MultiStep);
    impl MultiEngine for Gappy {
        fn submit(
            &mut self,
            req: &GenerationRequest,
            c: ControlProbe,
        ) -> Result<(), EngineFailure> {
            self.0.submit(req, c)
        }
        fn pump(
            &mut self,
            sink: &mut dyn TaggedSink,
            w: Duration,
        ) -> Result<Vec<Finished>, EngineFailure> {
            struct Skew<'a>(&'a mut dyn TaggedSink);
            impl TaggedSink for Skew<'_> {
                fn deliver(
                    &mut self,
                    rid: RequestId,
                    mut e: EngineEvent,
                ) -> Result<(), DeliveryRefused> {
                    if let (1, EngineEvent::Token(t)) = (rid.0, &mut e) {
                        if t.index == 2 {
                            t.index = 3;
                        }
                    }
                    self.0.deliver(rid, e)
                }
            }
            self.0.pump(&mut Skew(sink), w)
        }
        fn running(&self) -> usize {
            self.0.running()
        }
    }
    let d = desc_multi(2);
    let mut engine = Gappy(MultiStep::new(2, (1..8).collect()));
    let mut ledgers = LedgerSet::new(2);
    for rid in 1..=2 {
        let req = GenerationRequest::new(RequestId(rid), vec![0], 40);
        ledgers.open(&req, &d).expect("open");
        engine
            .submit(&req, ControlHandle::new().probe())
            .expect("submit");
    }
    let mut out = Tagged::default();
    let mut results = Vec::new();
    while !ledgers.is_empty() {
        let done = {
            let mut sink = ledgers.sink(&mut out);
            engine.pump(&mut sink, Duration::ZERO).expect("pump")
        };
        for f in done {
            results.push((f.rid, ledgers.finish(f)));
        }
    }
    results.sort_by_key(|(r, _)| *r);
    let f = results[0].1.clone().expect_err("request 1 has a gap");
    assert_eq!(f.kind, FailureKind::Protocol);
    assert_eq!(f.after_tokens, 2);
    let (_, counts) = results[1].1.clone().expect("request 2 is fine");
    assert_eq!(counts.completion_tokens, 7);
    assert_eq!(out.ids_of(RequestId(1)), vec![1001, 1002]);
}

#[test]
fn generate_one_is_the_single_conversation_case() {
    let mut engine = MultiStep::new(4, vec![7, 8, 2]);
    let req = GenerationRequest::new(RequestId(4), vec![0, 0], 10);
    let mut out = Collect::default();
    let t = generate_one(
        &mut engine,
        &req,
        &ControlHandle::new().probe(),
        &mut out,
        Duration::from_millis(1),
    )
    .expect("generation");
    assert_eq!(t.stop, EngineStop::Stop { token: None });
    assert_eq!(ids(&out.got), vec![4007, 4008, 4002]);
    assert!(matches!(
        out.got[0],
        EngineEvent::Admitted {
            prompt_tokens: 2,
            ..
        }
    ));

    // Refused while another generation runs.
    let other = GenerationRequest::new(RequestId(5), vec![0], 10);
    engine
        .submit(&other, ControlHandle::new().probe())
        .expect("submit");
    let f = generate_one(
        &mut engine,
        &req,
        &ControlHandle::new().probe(),
        &mut out,
        Duration::ZERO,
    )
    .expect_err("busy");
    assert_eq!(f.kind, FailureKind::Unsupported);
}

#[test]
fn an_engine_with_several_places_offers_the_pump_form_through_its_instance() {
    struct MultiInstance {
        desc: EngineDescriptor,
        inner: MultiStep,
    }
    impl EngineInstance for MultiInstance {
        fn descriptor(&self) -> &EngineDescriptor {
            &self.desc
        }
        fn generate(
            &mut self,
            req: &GenerationRequest,
            control: &ControlProbe,
            sink: &mut dyn EventSink,
        ) -> Result<Terminal, EngineFailure> {
            generate_one(
                &mut self.inner,
                req,
                control,
                sink,
                Duration::from_millis(1),
            )
        }
        fn multi(&mut self) -> Option<&mut dyn MultiEngine> {
            Some(&mut self.inner)
        }
        fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
            ShutdownOutcome::AlreadyEnded
        }
    }
    let mut engine: Box<dyn EngineInstance> = Box::new(MultiInstance {
        desc: desc_multi(2),
        inner: MultiStep::new(2, vec![3, 2]),
    });
    let req = GenerationRequest::new(RequestId(1), vec![0], 8);
    let mut out = Collect::default();
    let (t, counts) = generate_ledgered(
        engine.as_mut(),
        &req,
        &ControlHandle::new().probe(),
        &mut out,
    )
    .expect("blocking form");
    assert_eq!(t.stop, EngineStop::Stop { token: None });
    assert_eq!(counts.completion_tokens, 2);
    assert_eq!(engine.descriptor().caps.places(), 2);
    let multi = engine.multi().expect("pump form");
    assert_eq!(multi.running(), 0);
}

// ---------------------------------------------------------------- a consumer that leaves

#[test]
fn a_consumer_gone_at_admission_ends_a_single_place_generation_cancelled() {
    struct Gone;
    impl EventSink for Gone {
        fn deliver(&mut self, _event: EngineEvent) -> Result<(), DeliveryRefused> {
            Err(DeliveryRefused::ConsumerGone)
        }
    }
    let mut engine = StepEngine::new((10..30).collect(), 4096);
    let req = GenerationRequest::new(RequestId(7), vec![1, 2], 64);
    let (t, counts) =
        generate_ledgered(&mut engine, &req, &ControlHandle::new().probe(), &mut Gone)
            .expect("a client gone before admission is no engine fault");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 0);
    assert_eq!(counts.prompt_tokens, 2);
}

#[test]
fn a_cancel_between_submit_and_the_first_pump_is_no_engine_fault() {
    // MultiStep checks cancel before it delivers anything, so request 1 finishes
    // Cancelled with no Admitted at all; request 2 runs on.
    let d = desc_multi(2);
    let mut engine = MultiStep::new(2, vec![1, 2, 3]);
    let mut ledgers = LedgerSet::new(2);
    let a = ControlHandle::new();
    let ra = GenerationRequest::new(RequestId(1), vec![0, 0, 0], 8);
    let rb = GenerationRequest::new(RequestId(2), vec![0], 8);
    for (req, h) in [(&ra, a.probe()), (&rb, ControlHandle::new().probe())] {
        ledgers.open(req, &d).expect("open");
        engine.submit(req, h).expect("submit");
    }
    a.cancel();
    let mut out = Tagged::default();
    let mut results = drive(&mut engine, &mut ledgers, &mut out);
    results.sort_by_key(|(r, _)| *r);
    let (t, counts) = results[0]
        .1
        .clone()
        .expect("cancelled, not a Protocol failure");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 0);
    assert_eq!(counts.prompt_tokens, 3);
    let (t, counts) = results[1].1.clone().expect("request 2 is untouched");
    assert_eq!(t.stop, EngineStop::Stop { token: None });
    assert_eq!(counts.completion_tokens, 3);
    assert!(out.got.iter().all(|(r, _)| *r == RequestId(2)));
}

/// Answers `ConsumerGone` for one request id after it took `after` of its events; other
/// ids are accepted.
struct GoneFor {
    rid: RequestId,
    after: usize,
    got: Vec<(RequestId, EngineEvent)>,
}

impl TaggedSink for GoneFor {
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused> {
        let taken = self.got.iter().filter(|(r, _)| *r == rid).count();
        if rid == self.rid && taken >= self.after {
            return Err(DeliveryRefused::ConsumerGone);
        }
        self.got.push((rid, event));
        Ok(())
    }
}

fn token(index: u32, position: u64, id: u32) -> EngineEvent {
    EngineEvent::Token(CommittedToken {
        index,
        position,
        id,
        logprob: None,
    })
}

#[test]
fn a_consumer_gone_for_one_id_with_tokens_in_flight_finishes_it_cancelled() {
    let d = desc_multi(2);
    let mut ledgers = LedgerSet::new(2);
    for rid in 1..=2 {
        let req = GenerationRequest::new(RequestId(rid), vec![0, 0], 8);
        ledgers.open(&req, &d).expect("open");
    }
    let mut down = GoneFor {
        rid: RequestId(1),
        after: 2,
        got: Vec::new(),
    };
    let admitted = EngineEvent::Admitted {
        prompt_tokens: 2,
        reused_tokens: None,
    };
    {
        let mut sink = ledgers.sink(&mut down);
        for rid in [RequestId(1), RequestId(2)] {
            sink.deliver(rid, admitted.clone()).expect("admitted");
            sink.deliver(rid, token(0, 2, 5)).expect("0");
        }
        assert_eq!(
            sink.deliver(RequestId(1), token(1, 3, 5)),
            Err(DeliveryRefused::ConsumerGone)
        );
        // Request 1's next token was already in flight; request 2 goes on.
        assert_eq!(
            sink.deliver(RequestId(1), token(2, 4, 5)),
            Err(DeliveryRefused::ConsumerGone)
        );
        sink.deliver(RequestId(2), token(1, 3, 5)).expect("1");
    }
    let (t, counts) = ledgers
        .finish(Finished {
            rid: RequestId(1),
            outcome: Ok(Terminal::bare(EngineStop::Cancelled)),
        })
        .expect("one client leaving is no engine fault");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 1);
    let (_, counts) = ledgers
        .finish(Finished {
            rid: RequestId(2),
            outcome: Ok(Terminal::bare(EngineStop::Length)),
        })
        .expect("request 2");
    assert_eq!(counts.completion_tokens, 2);
    assert!(ledgers.is_empty());
}

#[test]
fn a_consumer_gone_through_the_pump_form_finishes_only_that_id_cancelled() {
    let d = desc_multi(2);
    for after in 0..4 {
        let mut engine = MultiStep::new(2, vec![1, 2, 3, 4, 5]);
        let mut ledgers = LedgerSet::new(2);
        for rid in 1..=2 {
            let req = GenerationRequest::new(RequestId(rid), vec![0], 8);
            ledgers.open(&req, &d).expect("open");
            engine
                .submit(&req, ControlHandle::new().probe())
                .expect("submit");
        }
        let mut down = GoneFor {
            rid: RequestId(1),
            after,
            got: Vec::new(),
        };
        let mut results = Vec::new();
        for _ in 0..100 {
            if ledgers.is_empty() {
                break;
            }
            let done = {
                let mut sink = ledgers.sink(&mut down);
                engine.pump(&mut sink, Duration::ZERO).expect("pump")
            };
            for f in done {
                results.push((f.rid, ledgers.finish(f)));
            }
        }
        results.sort_by_key(|(r, _)| *r);
        let (t, counts) = results[0].1.clone().expect("cancelled");
        assert_eq!(t.stop, EngineStop::Cancelled, "after {after}");
        assert_eq!(counts.completion_tokens as usize, after.saturating_sub(1));
        let (_, counts) = results[1].1.clone().expect("request 2");
        assert_eq!(counts.completion_tokens, 5, "after {after}");
    }
}

#[test]
fn generate_one_refuses_an_engine_that_drops_the_generation_without_a_finished() {
    /// Accepts the submission, then forgets it: every pump returns nothing and nothing
    /// is running.
    struct Forgetful {
        running: usize,
    }
    impl MultiEngine for Forgetful {
        fn submit(
            &mut self,
            _req: &GenerationRequest,
            _c: ControlProbe,
        ) -> Result<(), EngineFailure> {
            self.running = 1;
            Ok(())
        }
        fn pump(
            &mut self,
            _sink: &mut dyn TaggedSink,
            _w: Duration,
        ) -> Result<Vec<Finished>, EngineFailure> {
            self.running = 0;
            Ok(Vec::new())
        }
        fn running(&self) -> usize {
            self.running
        }
    }
    let req = GenerationRequest::new(RequestId(3), vec![0], 4);
    let f = generate_one(
        &mut Forgetful { running: 0 },
        &req,
        &ControlHandle::new().probe(),
        &mut Collect::default(),
        Duration::ZERO,
    )
    .expect_err("no Finished");
    assert_eq!(f.kind, FailureKind::Protocol);
    assert!(f.poisoned);
    assert!(
        f.to_string()
            .contains("request id 3 ended without a Finished"),
        "{f}"
    );
}
