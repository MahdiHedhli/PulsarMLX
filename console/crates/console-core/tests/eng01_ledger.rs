//! ENG-01: the event ledger of contract section 7.1 (FR-029): delivery at least once and
//! keyed by position, exact replays of the most recent token dropped, gaps and rewinds
//! rejected. Property-style tests run as plain loops over generated sequences. No donor
//! test exists for the ledger.

use std::sync::Arc;

use console_core::engine::{
    BoundedText, CommittedToken, DeliveryRefused, EngineCounts, EngineDescriptor, EngineEvent,
    EngineFailure, EngineKind, EngineSample, EngineStop, EngineTimings, EventLedger, EventSink,
    FailureKind, GenerationRequest, LedgeredSink, PromptProgress, Provenance, RequestId, Terminal,
    TokenLogprob, Verdict,
};

/// A small deterministic generator (xorshift64*), so the tests need no dependency.
struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Self {
        Self(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    fn below(&mut self, n: u64) -> u64 {
        if n == 0 {
            0
        } else {
            self.next() % n
        }
    }
    fn chance(&mut self, one_in: u64) -> bool {
        self.below(one_in) == 0
    }
}

fn desc(vocab: Option<u32>) -> EngineDescriptor {
    let mut d = EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic);
    d.max_context = 1 << 20;
    d.vocab_size = vocab;
    d
}

fn request(prompt_len: usize, max_new: u32, logprobs: Option<u8>) -> GenerationRequest {
    let prompt: Vec<u32> = (0..prompt_len as u32).collect();
    let mut r = GenerationRequest::new(RequestId(1), prompt, max_new);
    r.logprobs = logprobs;
    r
}

fn admitted(n: u32) -> EngineEvent {
    EngineEvent::Admitted {
        prompt_tokens: n,
        reused_tokens: None,
    }
}

fn tok(index: u32, position: u64, id: u32) -> EngineEvent {
    EngineEvent::Token(CommittedToken {
        index,
        position,
        id,
        logprob: None,
    })
}

fn tok_lp(index: u32, position: u64, id: u32, logprob: f64, top: Vec<(u32, f64)>) -> EngineEvent {
    EngineEvent::Token(CommittedToken {
        index,
        position,
        id,
        logprob: Some(TokenLogprob { logprob, top }),
    })
}

fn protocol(result: Result<Verdict, EngineFailure>) -> EngineFailure {
    let f = result.expect_err("expected a failure");
    assert_eq!(f.kind, FailureKind::Protocol, "{f}");
    assert!(f.poisoned);
    f
}

/// A ledger over a prompt of 3 tokens and max_new 8, admitted, with tokens 0..n accepted
/// at positions 10.. and ids 100+i.
fn ledger_with(n: u32) -> EventLedger {
    let mut l = EventLedger::new(&request(3, 8, None), &desc(Some(1000)));
    assert_eq!(l.observe(&admitted(3)), Ok(Verdict::Accepted));
    for i in 0..n {
        assert_eq!(
            l.observe(&tok(i, 10 + u64::from(i), 100 + i)),
            Ok(Verdict::Accepted)
        );
    }
    l
}

// ---------------------------------------------------------------- the observe table

#[test]
fn next_index_at_the_next_position_is_accepted() {
    let l = ledger_with(3);
    assert_eq!(l.accepted(), 3);
}

#[test]
fn an_exact_repeat_of_the_last_token_is_a_replay() {
    let mut l = ledger_with(2);
    assert_eq!(l.observe(&tok(1, 11, 101)), Ok(Verdict::Replay));
    assert_eq!(l.observe(&tok(1, 11, 101)), Ok(Verdict::Replay));
    assert_eq!(l.accepted(), 2);
    assert_eq!(l.observe(&tok(2, 12, 102)), Ok(Verdict::Accepted));
}

#[test]
fn a_repeat_of_an_earlier_token_is_a_rewind() {
    // Q3: only the most recently accepted token may be replayed.
    let mut l = ledger_with(3);
    let f = protocol(l.observe(&tok(0, 10, 100)));
    assert!(f.to_string().contains("rewind"), "{f}");
    assert_eq!(f.after_tokens, 3);
}

#[test]
fn a_changed_id_at_the_last_committed_position_is_refused() {
    let mut l = ledger_with(2);
    protocol(l.observe(&tok(1, 11, 999)));
}

#[test]
fn a_changed_logprob_at_the_last_committed_position_is_refused() {
    let mut l = EventLedger::new(&request(1, 4, Some(2)), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    l.observe(&tok_lp(0, 1, 5, -0.5, vec![(5, -0.5)]))
        .expect("token");
    protocol(l.observe(&tok_lp(0, 1, 5, -0.25, vec![(5, -0.25)])));
}

#[test]
fn a_gap_is_refused() {
    let mut l = ledger_with(1);
    let f = protocol(l.observe(&tok(2, 12, 102)));
    assert!(f.to_string().contains("gap"), "{f}");
    assert_eq!(f.after_tokens, 1);
}

#[test]
fn a_token_before_admitted_is_refused() {
    let mut l = EventLedger::new(&request(3, 8, None), &desc(None));
    protocol(l.observe(&tok(0, 3, 1)));
}

#[test]
fn admitted_twice_is_refused_even_when_identical() {
    let mut l = ledger_with(0);
    protocol(l.observe(&admitted(3)));
}

#[test]
fn admitted_with_another_prompt_length_is_refused() {
    let mut l = EventLedger::new(&request(3, 8, None), &desc(None));
    let f = protocol(l.observe(&admitted(4)));
    assert!(
        f.to_string().contains("4 prompt tokens for a prompt of 3"),
        "{f}"
    );
}

#[test]
fn an_index_at_max_new_is_refused() {
    let mut l = EventLedger::new(&request(1, 2, None), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    l.observe(&tok(0, 1, 1)).expect("0");
    l.observe(&tok(1, 2, 1)).expect("1");
    let f = protocol(l.observe(&tok(2, 3, 1)));
    assert!(f.to_string().contains("max_new"), "{f}");
    let mut zero = EventLedger::new(&request(1, 0, None), &desc(None));
    zero.observe(&admitted(1)).expect("admitted");
    protocol(zero.observe(&tok(0, 1, 1)));
}

#[test]
fn an_id_beyond_the_vocabulary_is_an_invalid_token() {
    let mut l = EventLedger::new(&request(1, 4, None), &desc(Some(50)));
    l.observe(&admitted(1)).expect("admitted");
    l.observe(&tok(0, 1, 49)).expect("last id in range");
    let f = l.observe(&tok(1, 2, 50)).expect_err("out of vocabulary");
    assert_eq!(f.kind, FailureKind::InvalidToken);
    assert_eq!(f.after_tokens, 1);
    assert_eq!(
        f.to_string(),
        "the engine wrote the token id 50, outside its vocabulary of 50 ids"
    );
    // Without a known vocabulary nothing is checked.
    let mut open = EventLedger::new(&request(1, 4, None), &desc(None));
    open.observe(&admitted(1)).expect("admitted");
    assert_eq!(open.observe(&tok(0, 1, u32::MAX)), Ok(Verdict::Accepted));
}

#[test]
fn a_logprob_that_was_not_asked_is_refused() {
    let mut l = ledger_with(0);
    protocol(l.observe(&tok_lp(0, 10, 1, 0.0, vec![])));
}

#[test]
fn more_alternatives_than_asked_are_cut_to_the_asked_number() {
    // The donor keeps every alternative of an LP line and renders lp[1][:n_top]
    // (serve/server.py:594 at 7e68a30f), so the answer is served with n alternatives.
    let req = request(1, 4, Some(1));
    let d = desc(None);
    let mut down = Downstream::new(1, 0);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(1)).expect("admitted");
    let three = tok_lp(0, 1, 7, -0.25, vec![(7, -0.25), (8, -1.0), (9, -2.0)]);
    sink.deliver(three.clone()).expect("accepted and cut");
    // The engine's replay of the token as it wrote it is still the same token.
    sink.deliver(three)
        .expect("a replay of the uncut token is dropped");
    assert_eq!(sink.ledger().accepted(), 1);
    // A changed alternative beyond the cut does not make it a different token either.
    sink.deliver(tok_lp(0, 1, 7, -0.25, vec![(7, -0.25), (5, -9.0)]))
        .expect("the same token once cut");
    let (_, counts) = sink
        .finish(Ok(Terminal::bare(EngineStop::Length)))
        .expect("finish");
    assert_eq!(counts.completion_tokens, 1);
    assert_eq!(
        down.got,
        vec![admitted(1), tok_lp(0, 1, 7, -0.25, vec![(7, -0.25)])]
    );
}

#[test]
fn logprobs_zero_cuts_every_alternative() {
    // The scripted engine's shape for top_logprobs 0: (0.0, []); an engine that writes
    // alternatives anyway is served with none, as the donor's lp[1][:0] is empty.
    let req = request(1, 4, Some(0));
    let d = desc(None);
    let mut down = Downstream::new(1, 0);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(1)).expect("admitted");
    sink.deliver(tok_lp(0, 1, 7, 0.0, vec![]))
        .expect("no alternatives");
    sink.deliver(tok_lp(1, 2, 104, -0.1, vec![(104, -0.1)]))
        .expect("alternatives cut");
    assert_eq!(
        down.tokens(),
        vec![
            CommittedToken {
                index: 0,
                position: 1,
                id: 7,
                logprob: Some(TokenLogprob {
                    logprob: 0.0,
                    top: vec![]
                }),
            },
            CommittedToken {
                index: 1,
                position: 2,
                id: 104,
                logprob: Some(TokenLogprob {
                    logprob: -0.1,
                    top: vec![]
                }),
            },
        ]
    );
}

#[test]
fn the_observe_form_cuts_alternatives_too() {
    let mut l = EventLedger::new(&request(1, 4, Some(1)), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    let three = tok_lp(0, 1, 7, 0.0, vec![(7, 0.0), (8, -1.0), (9, -2.0)]);
    let c = l.check(&three).expect("check");
    assert_eq!(
        c.forwarded(three.clone()),
        tok_lp(0, 1, 7, 0.0, vec![(7, 0.0)])
    );
    l.commit(c).expect("commit");
    assert_eq!(l.observe(&three), Ok(Verdict::Replay));
    // A side event is forwarded as offered.
    let note = EngineEvent::Note(BoundedText::note("n"));
    let c = l.check(&note).expect("check");
    assert_eq!(c.forwarded(note.clone()), note);
}

#[test]
fn a_token_without_a_logprob_is_accepted_when_one_was_asked() {
    let mut l = EventLedger::new(&request(1, 4, Some(3)), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    assert_eq!(l.observe(&tok(0, 1, 7)), Ok(Verdict::Accepted));
}

#[test]
fn the_first_token_fixes_position0() {
    let mut l = EventLedger::new(&request(3, 8, None), &desc(None));
    l.observe(&admitted(3)).expect("admitted");
    // An engine with prefix reuse may start anywhere.
    l.observe(&tok(0, 500, 1)).expect("0");
    l.observe(&tok(1, 501, 1)).expect("1");
    let f = protocol(l.observe(&tok(2, 503, 1)));
    assert!(f.to_string().contains("expected position 502"), "{f}");
}

#[test]
fn a_position_overflow_is_refused() {
    let mut l = EventLedger::new(&request(1, 8, None), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    l.observe(&tok(0, u64::MAX, 1)).expect("0");
    protocol(l.observe(&tok(1, 0, 1)));
}

#[test]
fn side_events_are_accepted_at_any_time_before_the_terminal() {
    let mut l = EventLedger::new(&request(2, 4, None), &desc(None));
    let pp = EngineEvent::PromptProgress(PromptProgress {
        read: 1,
        total: 2,
        reused: 0,
        ms: 1.0,
        tok_s: None,
    });
    let note = EngineEvent::Note(BoundedText::note("loading"));
    let sample = EngineEvent::Sample(EngineSample::from_stat_fields(["hit=1"]));
    for e in [&pp, &note, &sample] {
        assert_eq!(l.observe(e), Ok(Verdict::Accepted));
    }
    l.observe(&admitted(2)).expect("admitted");
    l.observe(&tok(0, 2, 1)).expect("token");
    for e in [&pp, &note, &sample, &pp] {
        assert_eq!(l.observe(e), Ok(Verdict::Accepted));
    }
    assert_eq!(l.accepted(), 1);
}

#[test]
fn a_replay_with_a_nan_logprob_is_still_a_replay() {
    let mut l = EventLedger::new(&request(1, 4, Some(1)), &desc(None));
    l.observe(&admitted(1)).expect("admitted");
    let t = tok_lp(0, 1, 3, f64::NAN, vec![(3, f64::NAN)]);
    assert_eq!(l.observe(&t), Ok(Verdict::Accepted));
    assert_eq!(l.observe(&t), Ok(Verdict::Replay));
}

#[test]
fn failures_are_sticky() {
    let mut l = ledger_with(2);
    let first = protocol(l.observe(&tok(5, 15, 1)));
    // Even a perfectly good next token is refused now, with the same failure.
    assert_eq!(l.observe(&tok(2, 12, 102)), Err(first.clone()));
    assert_eq!(l.observe(&admitted(3)), Err(first.clone()));
    assert_eq!(l.failure(), Some(&first));
    assert_eq!(l.close(&Terminal::bare(EngineStop::Length)), Err(first));
}

#[test]
fn a_stale_check_cannot_be_committed() {
    let mut l = ledger_with(0);
    let a = l.check(&tok(0, 10, 1)).expect("check a");
    let b = l.check(&tok(0, 10, 1)).expect("check b");
    l.commit(a).expect("commit a");
    let f = l.commit(b).expect_err("b is stale");
    assert_eq!(f.kind, FailureKind::Protocol);
}

#[test]
fn check_alone_records_nothing() {
    let mut l = ledger_with(0);
    for _ in 0..3 {
        let c = l.check(&tok(0, 10, 1)).expect("check");
        assert_eq!(c.verdict(), Verdict::Accepted);
    }
    assert_eq!(l.accepted(), 0);
}

// ---------------------------------------------------------------- close

#[test]
fn close_returns_the_ledger_figures() {
    let mut l = ledger_with(4);
    let counts = l
        .close(&Terminal::bare(EngineStop::Stop { token: Some(103) }))
        .expect("close");
    assert_eq!(counts.prompt_tokens, 3);
    assert_eq!(counts.completion_tokens, 4, "the stop token is counted");
    assert_eq!(counts.reused_tokens, None);
    assert_eq!(counts.stop, EngineStop::Stop { token: Some(103) });
    assert_eq!(counts.engine, None);
    assert_eq!(counts.timings, None);
    assert!(l.is_closed());
}

#[test]
fn close_passes_the_engine_counts_through_unchecked() {
    // Q4: the donor's own fixtures report DONE figures that differ from the tokens taken
    // (serve/test_server.py:1047 reports 2 generated after an invalid and one good token;
    // serve/fake_multi_engine.py:73 reports 0 generated on a cancel, and its prompt count
    // is "its own"). The ledger keeps its own counts and passes the engine's through.
    let mut l = ledger_with(1);
    let engine = EngineCounts {
        generated: 2,
        prompt_tokens: 12_000,
        reused_tokens: Some(8),
        drafts: Some((1, 2)),
        hits_lookups: None,
    };
    let timings = EngineTimings {
        prompt_ms: 4000.0,
        decode_ms: 10.0,
    };
    let t = Terminal {
        stop: EngineStop::Cancelled,
        counts: Some(engine),
        timings: Some(timings),
    };
    let counts = l.close(&t).expect("close");
    assert_eq!(counts.prompt_tokens, 3);
    assert_eq!(counts.completion_tokens, 1);
    assert_eq!(counts.reused_tokens, Some(8));
    assert_eq!(counts.engine, Some(engine));
    assert_eq!(counts.timings, Some(timings));
}

#[test]
fn close_takes_reuse_from_the_terminal_counts_only() {
    // The donor reads cached tokens from the DONE line only (serve/server.py:1197, :4712,
    // :5005 at 7e68a30f); reuse in progress events or in Admitted is not usage.
    let progress = |reused| {
        EngineEvent::PromptProgress(PromptProgress {
            read: 3,
            total: 3,
            reused,
            ms: 1.0,
            tok_s: Some(3.0),
        })
    };
    let req = request(3, 4, None);
    // Progress only: no cached tokens (the donor's request record shows null).
    let mut l = EventLedger::new(&req, &desc(None));
    l.observe(&admitted(3)).expect("admitted");
    l.observe(&progress(1)).expect("pp");
    l.observe(&progress(2)).expect("pp");
    let c = l.close(&Terminal::bare(EngineStop::Length)).expect("close");
    assert_eq!(c.reused_tokens, None, "progress reuse is not usage");
    // Admitted's reuse is not usage either.
    let admitted_with_reuse = EngineEvent::Admitted {
        prompt_tokens: 3,
        reused_tokens: Some(1),
    };
    let mut l = EventLedger::new(&req, &desc(None));
    l.observe(&admitted_with_reuse).expect("admitted");
    l.observe(&progress(2)).expect("pp");
    let c = l.close(&Terminal::bare(EngineStop::Length)).expect("close");
    assert_eq!(c.reused_tokens, None);
    // A 5-figure DONE (counts without reuse) reports none, whatever came before.
    let mut l = EventLedger::new(&req, &desc(None));
    l.observe(&admitted_with_reuse).expect("admitted");
    l.observe(&progress(2)).expect("pp");
    let mut t = Terminal::bare(EngineStop::Length);
    t.counts = Some(EngineCounts::default());
    assert_eq!(l.close(&t).expect("close").reused_tokens, None);
    // An 8-figure DONE's reuse is the figure.
    let mut l = EventLedger::new(&req, &desc(None));
    l.observe(&admitted_with_reuse).expect("admitted");
    l.observe(&progress(2)).expect("pp");
    t.counts = Some(EngineCounts {
        reused_tokens: Some(3),
        ..EngineCounts::default()
    });
    assert_eq!(l.close(&t).expect("close").reused_tokens, Some(3));
}

#[test]
fn a_stop_or_length_terminal_before_admitted_is_refused() {
    for stop in [EngineStop::Stop { token: None }, EngineStop::Length] {
        let mut l = EventLedger::new(&request(1, 4, None), &desc(None));
        let f = l.close(&Terminal::bare(stop)).expect_err("refused");
        assert_eq!(f.kind, FailureKind::Protocol);
        assert!(f.poisoned);
        assert!(f.to_string().contains("before Admitted"), "{f}");
    }
}

#[test]
fn a_cancelled_or_paused_terminal_before_admitted_simply_ends() {
    // A generation cancelled before it started ends, as the donor's generate returns on
    // cancel.is_set() before any token (serve/server.py:228-229, :1393-1394 at 7e68a30f).
    for stop in [EngineStop::Cancelled, EngineStop::Paused] {
        let mut l = EventLedger::new(&request(2, 4, None), &desc(None));
        let mut t = Terminal::bare(stop);
        t.counts = Some(EngineCounts {
            reused_tokens: Some(1),
            ..EngineCounts::default()
        });
        let c = l.close(&t).expect("ends without a failure");
        assert_eq!(c.prompt_tokens, 2);
        assert_eq!(c.completion_tokens, 0);
        assert_eq!(c.reused_tokens, Some(1));
        assert_eq!(c.stop, stop);
        assert!(l.is_closed());
        // Nothing follows it.
        protocol(l.observe(&admitted(2)));
    }
}

#[test]
fn nothing_follows_the_terminal() {
    let mut l = ledger_with(1);
    l.close(&Terminal::bare(EngineStop::Length)).expect("close");
    let f = protocol(l.observe(&tok(1, 11, 101)));
    assert!(f.to_string().contains("after the terminal"), "{f}");
    let mut l = ledger_with(1);
    l.close(&Terminal::bare(EngineStop::Length)).expect("close");
    assert!(l.close(&Terminal::bare(EngineStop::Length)).is_err());
    // Even an exact replay of the last token is refused after the terminal.
    let mut l = ledger_with(1);
    l.close(&Terminal::bare(EngineStop::Length)).expect("close");
    protocol(l.observe(&tok(0, 10, 100)));
}

// ---------------------------------------------------------------- the ledgered sink

/// A downstream that refuses each event with `Backpressure` according to a script or a
/// generator, and records what it accepted.
struct Downstream {
    got: Vec<EngineEvent>,
    rng: Rng,
    refuse_one_in: u64,
}

impl Downstream {
    fn new(seed: u64, refuse_one_in: u64) -> Self {
        Self {
            got: Vec::new(),
            rng: Rng::new(seed),
            refuse_one_in,
        }
    }
    fn tokens(&self) -> Vec<CommittedToken> {
        self.got
            .iter()
            .filter_map(|e| match e {
                EngineEvent::Token(t) => Some(t.clone()),
                _ => None,
            })
            .collect()
    }
}

impl EventSink for Downstream {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        if self.refuse_one_in > 0 && self.rng.chance(self.refuse_one_in) {
            return Err(DeliveryRefused::Backpressure);
        }
        self.got.push(event);
        Ok(())
    }
}

/// Offers `event` until it is not refused with `Backpressure` (bounded, so a broken
/// sink fails the test instead of hanging it).
fn offer(sink: &mut dyn EventSink, event: &EngineEvent) -> Result<(), DeliveryRefused> {
    for _ in 0..10_000 {
        match sink.deliver(event.clone()) {
            Err(DeliveryRefused::Backpressure) => continue,
            other => return other,
        }
    }
    panic!("the sink never accepted the event");
}

#[test]
fn an_event_refused_with_backpressure_is_forwarded_when_offered_again() {
    struct RefuseFirst {
        refused: bool,
        got: Vec<EngineEvent>,
    }
    impl EventSink for RefuseFirst {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            if matches!(event, EngineEvent::Token(_)) && !self.refused {
                self.refused = true;
                return Err(DeliveryRefused::Backpressure);
            }
            self.got.push(event);
            Ok(())
        }
    }
    let req = request(2, 4, None);
    let d = desc(None);
    let mut down = RefuseFirst {
        refused: false,
        got: Vec::new(),
    };
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(2)).expect("admitted");
    assert_eq!(
        sink.deliver(tok(0, 2, 9)),
        Err(DeliveryRefused::Backpressure)
    );
    assert_eq!(sink.ledger().accepted(), 0, "not committed while refused");
    sink.deliver(tok(0, 2, 9)).expect("offered again");
    sink.deliver(tok(0, 2, 9))
        .expect("an exact replay is dropped");
    let (t, counts) = sink
        .finish(Ok(Terminal::bare(EngineStop::Length)))
        .expect("finish");
    assert_eq!(t.stop, EngineStop::Length);
    assert_eq!(counts.completion_tokens, 1);
    assert_eq!(down.got, vec![admitted(2), tok(0, 2, 9)]);
}

#[test]
fn a_ledger_failure_tells_the_engine_the_consumer_is_gone_and_wins_at_finish() {
    let req = request(2, 4, None);
    let d = desc(None);
    let mut down = Downstream::new(1, 0);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(2)).expect("admitted");
    sink.deliver(tok(0, 2, 9)).expect("0");
    assert_eq!(
        sink.deliver(tok(2, 4, 9)),
        Err(DeliveryRefused::ConsumerGone)
    );
    assert_eq!(
        sink.deliver(tok(1, 3, 9)),
        Err(DeliveryRefused::ConsumerGone)
    );
    // The engine stops as told and returns Cancelled; the ledger's failure is the answer.
    let f = sink
        .finish(Ok(Terminal::bare(EngineStop::Cancelled)))
        .expect_err("ledger failure");
    assert_eq!(f.kind, FailureKind::Protocol);
    assert_eq!(f.after_tokens, 1);
    assert_eq!(down.tokens().len(), 1);
}

#[test]
fn an_engine_failure_carries_the_accepted_token_count() {
    let req = request(2, 4, None);
    let d = desc(None);
    let mut down = Downstream::new(1, 0);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(2)).expect("admitted");
    sink.deliver(tok(0, 2, 9)).expect("0");
    sink.deliver(tok(1, 3, 9)).expect("1");
    let f = sink
        .finish(Err(EngineFailure::stopped_unexpectedly(Some(9))))
        .expect_err("engine failure");
    assert_eq!(f.kind, FailureKind::Died);
    assert_eq!(f.after_tokens, 2);
}

/// A downstream that accepts `after` events, then answers `ConsumerGone` for good.
struct GoneAfter {
    after: usize,
    got: Vec<EngineEvent>,
    refusals: usize,
}

impl GoneAfter {
    fn new(after: usize) -> Self {
        Self {
            after,
            got: Vec::new(),
            refusals: 0,
        }
    }
    fn tokens(&self) -> Vec<CommittedToken> {
        self.got
            .iter()
            .filter_map(|e| match e {
                EngineEvent::Token(t) => Some(t.clone()),
                _ => None,
            })
            .collect()
    }
}

impl EventSink for GoneAfter {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        if self.got.len() >= self.after {
            self.refusals += 1;
            return Err(DeliveryRefused::ConsumerGone);
        }
        self.got.push(event);
        Ok(())
    }
}

#[test]
fn a_consumer_gone_at_admission_ends_cancelled() {
    let req = request(2, 8, None);
    let d = desc(None);
    let mut down = GoneAfter::new(0);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    assert_eq!(
        sink.deliver(admitted(2)),
        Err(DeliveryRefused::ConsumerGone)
    );
    assert!(sink.ledger().failure().is_none());
    assert!(sink.ledger().consumer_gone());
    let (t, counts) = sink
        .finish(Ok(Terminal::bare(EngineStop::Cancelled)))
        .expect("a refused delivery never turns a committed step into a failure");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 0);
    assert_eq!(counts.prompt_tokens, 2);
    assert!(down.got.is_empty());
}

#[test]
fn a_consumer_gone_mid_stream_with_tokens_in_flight_ends_cancelled() {
    let req = request(2, 8, None);
    let d = desc(None);
    let mut down = GoneAfter::new(2);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(2)).expect("admitted");
    sink.deliver(tok(0, 2, 7)).expect("0");
    assert_eq!(
        sink.deliver(tok(1, 3, 7)),
        Err(DeliveryRefused::ConsumerGone)
    );
    // Token 2 was already in flight; it is recorded, not forwarded, and still answered
    // ConsumerGone. So is an exact replay of it.
    assert_eq!(
        sink.deliver(tok(2, 4, 7)),
        Err(DeliveryRefused::ConsumerGone)
    );
    assert_eq!(
        sink.deliver(tok(2, 4, 7)),
        Err(DeliveryRefused::ConsumerGone)
    );
    assert!(sink.ledger().failure().is_none());
    assert_eq!(sink.ledger().accepted(), 3);
    assert_eq!(sink.ledger().delivered(), 1);
    let (t, counts) = sink
        .finish(Ok(Terminal::bare(EngineStop::Cancelled)))
        .expect("cancelled");
    assert_eq!(t.stop, EngineStop::Cancelled);
    assert_eq!(counts.completion_tokens, 1, "only what the consumer took");
    assert_eq!(down.got, vec![admitted(2), tok(0, 2, 7)]);
    assert_eq!(down.refusals, 1, "nothing is forwarded after ConsumerGone");
}

#[test]
fn a_fault_after_the_consumer_left_is_still_caught() {
    let req = request(2, 8, None);
    let d = desc(None);
    let mut down = GoneAfter::new(2);
    let mut sink = LedgeredSink::new(&req, &d, &mut down);
    sink.deliver(admitted(2)).expect("admitted");
    sink.deliver(tok(0, 2, 7)).expect("0");
    assert_eq!(
        sink.deliver(tok(1, 3, 7)),
        Err(DeliveryRefused::ConsumerGone)
    );
    assert_eq!(
        sink.deliver(tok(3, 5, 7)),
        Err(DeliveryRefused::ConsumerGone)
    );
    let f = sink
        .finish(Ok(Terminal::bare(EngineStop::Cancelled)))
        .expect_err("the gap decides the outcome");
    assert_eq!(f.kind, FailureKind::Protocol);
    assert!(f.to_string().contains("gap"), "{f}");
    assert_eq!(f.after_tokens, 2);
}

// ---------------------------------------------------------------- property loops

/// One generated well-formed generation.
struct Script {
    req: GenerationRequest,
    tokens: Vec<CommittedToken>,
}

fn script(rng: &mut Rng) -> Script {
    let prompt_len = 1 + rng.below(12) as usize;
    let n = rng.below(48) as u32;
    let max_new = n + rng.below(4) as u32;
    let logprobs = if rng.chance(2) {
        Some(rng.below(6) as u8)
    } else {
        None
    };
    let position0 = prompt_len as u64 + rng.below(1000);
    let mut req = request(prompt_len, max_new, logprobs);
    req.rid = RequestId(rng.next());
    req.stop_ids = Arc::from(vec![2u32]);
    let tokens = (0..n)
        .map(|i| CommittedToken {
            index: i,
            position: position0 + u64::from(i),
            id: rng.below(1000) as u32,
            logprob: logprobs.and_then(|k| {
                if rng.chance(5) {
                    None
                } else {
                    let alts = rng.below(u64::from(k) + 1) as usize;
                    Some(TokenLogprob {
                        logprob: -(rng.below(100) as f64) / 10.0,
                        top: (0..alts).map(|j| (j as u32, -(j as f64))).collect(),
                    })
                }
            }),
        })
        .collect();
    Script { req, tokens }
}

fn side_event(rng: &mut Rng) -> EngineEvent {
    match rng.below(3) {
        0 => EngineEvent::PromptProgress(PromptProgress {
            read: rng.below(10) as u32,
            total: 10,
            reused: rng.below(5) as u32,
            ms: 1.5,
            tok_s: None,
        }),
        1 => EngineEvent::Note(BoundedText::note("note")),
        _ => EngineEvent::Sample(EngineSample::from_stat_fields(["k=1"])),
    }
}

#[test]
fn property_at_least_once_delivery_yields_each_token_exactly_once_in_order() {
    for seed in 0..600u64 {
        let mut rng = Rng::new(seed);
        let s = script(&mut rng);
        let d = desc(Some(1000));
        let mut down = Downstream::new(seed ^ 0xABCD, 2 + rng.below(4));
        let mut sink = LedgeredSink::new(&s.req, &d, &mut down);
        if rng.chance(3) {
            offer(&mut sink, &side_event(&mut rng)).expect("early side event");
        }
        offer(&mut sink, &admitted(s.req.prompt.len() as u32)).expect("admitted");
        for t in &s.tokens {
            while rng.chance(4) {
                offer(&mut sink, &side_event(&mut rng)).expect("side event");
            }
            let e = EngineEvent::Token(t.clone());
            offer(&mut sink, &e).expect("token");
            // At least once: the engine may deliver the same token again, any number of
            // times, as the coordinator does after a refused delivery.
            while rng.chance(3) {
                offer(&mut sink, &e).expect("replay");
            }
        }
        let stop = if s.tokens.len() as u32 == s.req.max_new {
            EngineStop::Length
        } else {
            EngineStop::Stop { token: None }
        };
        let (_, counts) = sink
            .finish(Ok(Terminal::bare(stop)))
            .unwrap_or_else(|f| panic!("seed {seed}: {f}"));
        assert_eq!(down.tokens(), s.tokens, "seed {seed}");
        assert_eq!(
            counts.completion_tokens as usize,
            s.tokens.len(),
            "seed {seed}"
        );
        assert_eq!(
            counts.prompt_tokens as usize,
            s.req.prompt.len(),
            "seed {seed}"
        );
        let admitted_count = down
            .got
            .iter()
            .filter(|e| matches!(e, EngineEvent::Admitted { .. }))
            .count();
        assert_eq!(admitted_count, 1, "seed {seed}");
    }
}

#[test]
fn property_a_consumer_leaving_at_any_event_ends_cancelled() {
    // The downstream leaves at a random event (at admission included); the engine still
    // delivers 0 to 2 further in-flight events, with replays, before it returns Cancelled.
    // The outcome is never a failure, the consumer gets a prefix of the tokens, and usage
    // counts that prefix.
    let mut left_at_admission = 0;
    let mut left_mid_stream = 0;
    for seed in 0..1500u64 {
        let mut rng = Rng::new(seed);
        let s = script(&mut rng);
        let d = desc(Some(1000));
        let mut events = vec![admitted(s.req.prompt.len() as u32)];
        events.extend(s.tokens.iter().cloned().map(EngineEvent::Token));
        let leave_at = rng.below(events.len() as u64 + 1) as usize;
        let mut down = GoneAfter::new(leave_at);
        let mut sink = LedgeredSink::new(&s.req, &d, &mut down);
        let mut in_flight: Option<u64> = None;
        for e in &events {
            match in_flight.as_mut() {
                Some(0) => break,
                Some(left) => *left -= 1,
                None => {}
            }
            if sink.deliver(e.clone()) == Err(DeliveryRefused::ConsumerGone) && in_flight.is_none()
            {
                in_flight = Some(rng.below(3));
            }
            // Only a token may be replayed; a second Admitted is a fault.
            if matches!(e, EngineEvent::Token(_)) && rng.chance(4) {
                let replay = sink.deliver(e.clone());
                if in_flight.is_some() {
                    assert_eq!(replay, Err(DeliveryRefused::ConsumerGone), "seed {seed}");
                }
            }
        }
        let gone = sink.ledger().consumer_gone();
        assert_eq!(gone, leave_at < events.len(), "seed {seed}");
        if leave_at == 0 {
            left_at_admission += 1;
        } else if gone {
            left_mid_stream += 1;
        }
        let stop = if gone {
            EngineStop::Cancelled
        } else if s.tokens.len() as u32 == s.req.max_new {
            EngineStop::Length
        } else {
            EngineStop::Stop { token: None }
        };
        let (t, counts) = sink
            .finish(Ok(Terminal::bare(stop)))
            .unwrap_or_else(|f| panic!("seed {seed}: {f}"));
        assert_eq!(t.stop, stop, "seed {seed}");
        let got = down.tokens();
        assert_eq!(got[..], s.tokens[..got.len()], "seed {seed}");
        assert_eq!(counts.completion_tokens as usize, got.len(), "seed {seed}");
        assert_eq!(
            got.len(),
            leave_at.saturating_sub(1).min(s.tokens.len()),
            "seed {seed}"
        );
    }
    assert!(left_at_admission >= 50, "{left_at_admission}");
    assert!(left_mid_stream >= 500, "{left_mid_stream}");
}

/// The faults an engine can make after accepting `k` tokens.
#[derive(Debug, Clone, Copy)]
enum Fault {
    Gap,
    RewindToEarlier,
    ChangedIdAtLast,
    WrongPosition,
    AdmittedAgain,
    BeyondMaxNew,
    UnaskedLogprob,
}

const FAULTS: [Fault; 7] = [
    Fault::Gap,
    Fault::RewindToEarlier,
    Fault::ChangedIdAtLast,
    Fault::WrongPosition,
    Fault::AdmittedAgain,
    Fault::BeyondMaxNew,
    Fault::UnaskedLogprob,
];

/// The faulty event after `k` accepted tokens of `s`, or `None` when this fault cannot
/// happen at that point (for example a rewind before two tokens).
fn faulty(s: &Script, k: usize, fault: Fault, rng: &mut Rng) -> Option<EngineEvent> {
    let p0 = s
        .tokens
        .first()
        .map_or(s.req.prompt.len() as u64, |t| t.position);
    let next = k as u32;
    match fault {
        Fault::Gap => {
            let index = next + 1 + rng.below(3) as u32;
            (index < s.req.max_new).then(|| tok(index, p0 + u64::from(index), 1))
        }
        Fault::RewindToEarlier => {
            (k >= 2).then(|| EngineEvent::Token(s.tokens[rng.below(k as u64 - 1) as usize].clone()))
        }
        Fault::ChangedIdAtLast => (k >= 1).then(|| {
            let mut t = s.tokens[k - 1].clone();
            t.id = t.id.wrapping_add(1) % 1000;
            EngineEvent::Token(t)
        }),
        Fault::WrongPosition => (k >= 1 && k < s.tokens.len()).then(|| {
            let mut t = s.tokens[k].clone();
            t.position += 1 + rng.below(5);
            EngineEvent::Token(t)
        }),
        Fault::AdmittedAgain => Some(admitted(s.req.prompt.len() as u32)),
        Fault::BeyondMaxNew => {
            (k == s.req.max_new as usize).then(|| tok(next, p0 + u64::from(next), 1))
        }
        Fault::UnaskedLogprob => (s.req.logprobs.is_none() && k < s.req.max_new as usize)
            .then(|| tok_lp(next, p0 + u64::from(next), 1, 0.0, vec![])),
    }
}

#[test]
fn property_every_fault_is_refused_with_the_accepted_count_and_nothing_leaks() {
    let mut exercised = [0usize; FAULTS.len()];
    for seed in 0..2000u64 {
        let mut rng = Rng::new(seed);
        let s = script(&mut rng);
        let fault_at = FAULTS.len() as u64;
        let which = rng.below(fault_at) as usize;
        let fault = FAULTS[which];
        let k = if matches!(fault, Fault::BeyondMaxNew) {
            s.tokens.len()
        } else {
            rng.below(s.tokens.len() as u64 + 1) as usize
        };
        let Some(bad) = faulty(&s, k, fault, &mut rng) else {
            continue;
        };
        exercised[which] += 1;
        let d = desc(Some(1000));
        let mut down = Downstream::new(seed, 2 + rng.below(5));
        let mut sink = LedgeredSink::new(&s.req, &d, &mut down);
        offer(&mut sink, &admitted(s.req.prompt.len() as u32)).expect("admitted");
        for t in &s.tokens[..k] {
            offer(&mut sink, &EngineEvent::Token(t.clone())).expect("token");
        }
        assert_eq!(
            offer(&mut sink, &bad),
            Err(DeliveryRefused::ConsumerGone),
            "seed {seed} {fault:?} at {k}"
        );
        // Nothing else gets through afterwards, not even the correct next token.
        if let Some(t) = s.tokens.get(k) {
            assert_eq!(
                offer(&mut sink, &EngineEvent::Token(t.clone())),
                Err(DeliveryRefused::ConsumerGone)
            );
        }
        let f = sink
            .finish(Ok(Terminal::bare(EngineStop::Cancelled)))
            .expect_err("the fault decides the outcome");
        assert_eq!(f.kind, FailureKind::Protocol, "seed {seed} {fault:?}");
        assert!(f.poisoned);
        assert_eq!(f.after_tokens as usize, k, "seed {seed} {fault:?}");
        assert_eq!(
            down.tokens(),
            s.tokens[..k].to_vec(),
            "seed {seed} {fault:?}"
        );
    }
    for (fault, n) in FAULTS.iter().zip(exercised) {
        assert!(n >= 10, "{fault:?} exercised only {n} times");
    }
}

#[test]
fn property_observe_and_check_commit_agree() {
    // The two ways of driving the ledger reach the same verdicts and state on random
    // streams that mix valid tokens, replays and faults.
    for seed in 0..400u64 {
        let mut rng = Rng::new(seed);
        let s = script(&mut rng);
        let d = desc(Some(1000));
        let mut a = EventLedger::new(&s.req, &d);
        let mut b = EventLedger::new(&s.req, &d);
        let mut stream = vec![admitted(s.req.prompt.len() as u32)];
        for t in &s.tokens {
            stream.push(EngineEvent::Token(t.clone()));
            if rng.chance(3) {
                stream.push(EngineEvent::Token(t.clone()));
            }
            if rng.chance(40) {
                stream.push(tok(t.index + 2, t.position + 2, 1));
            }
        }
        for e in &stream {
            let va = a.observe(e);
            let vb = b.check(e).and_then(|c| {
                let v = c.verdict();
                b.commit(c).map(|()| v)
            });
            assert_eq!(va, vb, "seed {seed}");
            assert_eq!(a.accepted(), b.accepted(), "seed {seed}");
        }
    }
}
