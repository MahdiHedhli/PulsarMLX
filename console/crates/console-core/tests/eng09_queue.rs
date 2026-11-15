//! ENG-09: a request's wait in the FIFO (keep-alive pings, leaving the line on a cancel or a
//! dropped wait, the long-wait line), capacity changes, the over-release line and the queue
//! watchdog, on tokio's paused clock with captured log lines.
//!
//! These are the FIFO halves of the donor's GoneClients and QueuedKeepAlives tests; their
//! HTTP halves (a raw socket closed while queued, `: keep-alive` on the wire) belong to the
//! transport and stream packages, which own the ledger rows.
//!
//! Behavior reference: project-maya serve/server.py:172-187, 259-268, 364-375, 3239-3270,
//! 3842-3860, 4351-4364 and serve/test_server.py:2364-2460 at 7e68a30f.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use console_core::engine::ControlHandle;
use console_core::fifo::{
    EngineFifo, FifoLog, LogCapture, QueueStep, Units, WatchStatus, QUEUE_PING, QUEUE_TICK,
    QUEUE_WARN, QUEUE_WEDGED,
};
use tokio::time::Instant;

fn captured(n: usize) -> (EngineFifo, LogCapture) {
    let (log, cap) = FifoLog::capture();
    (EngineFifo::with_log(n, log), cap)
}

async fn until(cond: impl Fn() -> bool) {
    for _ in 0..100_000 {
        if cond() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    panic!("condition not reached");
}

#[tokio::test(start_paused = true)]
async fn a_queued_request_pings_at_its_interval_and_then_gets_its_turn() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let start = Instant::now();
    let mut wait = fifo.queue_wait(
        Units::ONE,
        control.probe(),
        Some(Duration::from_millis(100)),
    );
    let mut pings = Vec::new();
    for _ in 0..3 {
        match wait.next().await {
            QueueStep::Ping => pings.push(start.elapsed()),
            other => panic!("expected a ping, got {other:?}"),
        }
    }
    let ms = Duration::from_millis;
    assert_eq!(pings, vec![ms(100), ms(200), ms(300)]);
    assert_eq!(fifo.waiting(), 1);
    drop(held);
    let turn = match wait.next().await {
        QueueStep::Turn(g) => g,
        other => panic!("expected the turn, got {other:?}"),
    };
    assert_eq!(fifo.waiting(), 0);
    assert_eq!(fifo.used(), 1);
    assert!(matches!(wait.next().await, QueueStep::Ended));
    // A short wait writes no line.
    assert!(cap.lines().is_empty());
    drop(turn);
    assert!(!fifo.locked());
}

#[tokio::test(start_paused = true)]
async fn the_default_interval_pings_every_two_seconds() {
    let (fifo, _cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let start = Instant::now();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), Some(QUEUE_PING));
    assert!(matches!(wait.next().await, QueueStep::Ping));
    assert_eq!(start.elapsed(), QUEUE_PING);
    assert!(matches!(wait.next().await, QueueStep::Ping));
    assert_eq!(start.elapsed(), QUEUE_PING * 2);
    drop(held);
}

#[tokio::test(start_paused = true)]
async fn a_cancelled_request_leaves_the_line_promptly() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let c = control.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(500)).await;
        c.cancel();
    });
    let start = Instant::now();
    assert!(matches!(wait.next().await, QueueStep::Cancelled));
    // Seen at the next look, within one poll interval of the cancel.
    assert!(start.elapsed() <= Duration::from_millis(550));
    assert_eq!(fifo.waiting(), 0);
    assert!(matches!(wait.next().await, QueueStep::Ended));
    assert!(cap.lines().is_empty());
    drop(held);
    // Nobody reached the engine on its behalf.
    assert!(!fifo.locked());
}

#[tokio::test(start_paused = true)]
async fn a_dropped_wait_gives_up_its_place_in_line() {
    let (fifo, _cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    for _ in 0..2 {
        let mut wait = fifo.queue_wait(
            Units::ONE,
            control.probe(),
            Some(Duration::from_millis(100)),
        );
        assert!(matches!(wait.next().await, QueueStep::Ping));
        assert_eq!(fifo.waiting(), 1);
        // The client went away at a ping.
        drop(wait);
        assert_eq!(fifo.waiting(), 0);
    }
    // A wait dropped mid-step leaves the line too.
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    assert!(
        tokio::time::timeout(Duration::from_millis(120), wait.next())
            .await
            .is_err()
    );
    assert_eq!(fifo.waiting(), 1);
    drop(wait);
    assert_eq!(fifo.waiting(), 0);
    drop(held);
    assert!(!fifo.locked());
}

#[tokio::test(start_paused = true)]
async fn a_long_wait_logs_a_line_when_its_turn_comes() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let later = fifo.enqueue(Units::ONE);
    let f = fifo.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_secs(7)).await;
        drop(held);
        drop(f);
    });
    let turn = match wait.next().await {
        QueueStep::Turn(g) => g,
        other => panic!("expected the turn, got {other:?}"),
    };
    assert_eq!(
        cap.take(),
        vec![
            "[console] this request waited 7 s for the engine (1 request(s) behind it)".to_owned()
        ]
    );
    drop(turn);
    drop(later);
}

#[tokio::test(start_paused = true)]
async fn a_long_wait_ended_by_a_cancel_logs_the_line_too() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let c = control.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_secs(5)).await;
        c.cancel();
    });
    assert!(matches!(wait.next().await, QueueStep::Cancelled));
    assert_eq!(
        cap.take(),
        vec![
            "[console] this request waited 5 s for the engine (1 request(s) behind it)".to_owned()
        ]
    );
    drop(held);
}

#[tokio::test(start_paused = true)]
async fn a_long_cancelled_wait_counts_itself_and_those_behind_it() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let later = fifo.enqueue(Units::ONE);
    let c = control.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_secs(6)).await;
        c.cancel();
    });
    assert!(matches!(wait.next().await, QueueStep::Cancelled));
    assert_eq!(
        cap.take(),
        vec![
            "[console] this request waited 6 s for the engine (2 request(s) behind it)".to_owned()
        ]
    );
    assert_eq!(fifo.waiting(), 1);
    drop(later);
    drop(held);
}

#[tokio::test(start_paused = true)]
async fn a_turn_can_arrive_with_the_cancel_already_set() {
    // The turn driver must check the cancel after `Turn` (donor serve/server.py:4361-4363).
    let (fifo, _cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let probe = control.probe();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let c = control.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(10)).await;
        drop(held);
        c.cancel();
    });
    let turn = match wait.next().await {
        QueueStep::Turn(g) => g,
        other => panic!("expected the turn, got {other:?}"),
    };
    assert!(probe.is_cancelled());
    assert_eq!(fifo.used(), 1);
    // The driver answers with a cancelled finish and gives the place back unused.
    drop(turn);
    assert!(!fifo.locked());
}

#[tokio::test(start_paused = true)]
async fn a_wait_just_under_the_threshold_logs_nothing() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let control = ControlHandle::new();
    let mut wait = fifo.queue_wait(Units::ONE, control.probe(), None);
    let f = fifo.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(4_990)).await;
        drop(held);
        drop(f);
    });
    assert!(matches!(wait.next().await, QueueStep::Turn(_)));
    assert!(cap.lines().is_empty());
}

#[tokio::test(start_paused = true)]
async fn a_capacity_change_is_logged_and_clamps_the_places_in_use() {
    let (fifo, cap) = captured(4);
    let whole = fifo.acquire(Units::All).await;
    assert_eq!(fifo.used(), 4);
    fifo.set_capacity(4);
    assert!(cap.lines().is_empty(), "an unchanged capacity says nothing");
    fifo.set_capacity(2);
    assert_eq!(fifo.used(), 2);
    assert_eq!(fifo.held_by(), "2 of 2 place(s) in use");
    // The holder for "all of them" gives back what the smaller engine has.
    drop(whole);
    assert_eq!(fifo.used(), 0);
    assert_eq!(
        cap.take(),
        vec!["[console] the engine's places: 4 -> 2 (4 in use)".to_owned()]
    );
}

#[tokio::test(start_paused = true)]
async fn a_shrink_under_single_places_logs_the_over_release() {
    let (fifo, cap) = captured(3);
    let a = fifo.acquire(Units::ONE).await;
    let b = fifo.acquire(Units::ONE).await;
    let c = fifo.acquire(Units::ONE).await;
    fifo.set_capacity(1);
    assert_eq!(fifo.used(), 1);
    drop(a);
    drop(b);
    drop(c);
    assert_eq!(fifo.used(), 0);
    assert_eq!(
        cap.take(),
        vec![
            "[console] the engine's places: 3 -> 1 (3 in use)".to_owned(),
            "[console] a place was given back that is not held (1 of 0 in use, capacity 1): \
             the engine's conversations changed while it ran"
                .to_owned(),
            "[console] a place was given back that is not held (1 of 0 in use, capacity 1): \
             the engine's conversations changed while it ran"
                .to_owned(),
        ]
    );
}

#[tokio::test(start_paused = true)]
async fn a_whole_waiter_gets_every_place_once_they_are_free() {
    let (fifo, _cap) = captured(4);
    let parts: Vec<_> = (0..2)
        .filter_map(|_| fifo.try_acquire(Units::ONE))
        .collect();
    assert_eq!(parts.len(), 2);
    let f = fifo.clone();
    let whole = tokio::spawn(async move { f.acquire(Units::All).await.granted() });
    until(|| fifo.waiting() == 1).await;
    drop(parts);
    assert!(matches!(
        tokio::time::timeout(Duration::from_secs(1), whole).await,
        Ok(Ok(4))
    ));
    assert!(!fifo.locked());
}

#[tokio::test(start_paused = true)]
async fn the_watchdog_warns_when_the_line_stops_and_repeats_every_minute() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let start = Instant::now();
    let status = Arc::new(Mutex::new(WatchStatus::default()));
    let s = Arc::clone(&status);
    let watch = fifo.spawn_queue_watch(move || s.lock().map(|v| v.clone()).unwrap_or_default());
    let stuck = fifo.enqueue(Units::ONE);

    tokio::time::sleep_until(start + QUEUE_WEDGED - Duration::from_secs(1)).await;
    assert!(
        cap.lines().is_empty(),
        "nothing before the line is {QUEUE_WEDGED:?} old"
    );

    tokio::time::sleep_until(start + QUEUE_WEDGED + Duration::from_secs(1)).await;
    let first = cap.take();
    assert_eq!(
        first,
        vec![
            "[console] WARNING: 1 request(s) have waited for the engine for up to 120 s and \
             nothing is running; 1 of 1 place(s) in use, 0 request(s) counted active. A \
             request that holds the engine and waits on it for ever stops every request \
             behind it - PULSAR_CONSOLE_REQUEST_QUIET_S / PULSAR_CONSOLE_DRAIN_S bound those \
             waits, so this line is what a wedged FIFO would look like. Queue state: GET \
             /status, /metrics (queued, active)."
                .to_owned()
        ]
    );

    if let Ok(mut v) = status.lock() {
        *v = WatchStatus {
            busy: true,
            phase: Some("writing".to_owned()),
            generated: Some(12),
            active: 1,
        };
    }
    // Ticks at 135, 150 and 165 s stay quiet: the last warning is under a minute old.
    tokio::time::sleep_until(start + QUEUE_WEDGED + QUEUE_WARN - Duration::from_secs(1)).await;
    assert!(cap.lines().is_empty());
    tokio::time::sleep_until(start + QUEUE_WEDGED + QUEUE_WARN + Duration::from_secs(1)).await;
    let second = cap.take();
    assert_eq!(second.len(), 1);
    assert!(second.iter().all(|l| l.contains(
        "up to 180 s and a request is running (writing, 12 tokens so far); 1 of 1 place(s) in \
         use, 1 request(s) counted active."
    )));

    // The line moves: nothing more is said.
    drop(stuck);
    tokio::time::sleep(QUEUE_TICK * 8).await;
    assert!(cap.lines().is_empty());
    drop(watch);
    drop(held);
}

#[tokio::test(start_paused = true)]
async fn a_dropped_watchdog_stops() {
    let (fifo, cap) = captured(1);
    let held = fifo.acquire(Units::All).await;
    let _stuck = fifo.enqueue(Units::ONE);
    let watch = fifo.spawn_queue_watch(WatchStatus::default);
    drop(watch);
    tokio::time::sleep(QUEUE_WEDGED * 3).await;
    assert!(cap.lines().is_empty());
    drop(held);
}

#[tokio::test(start_paused = true)]
async fn oldest_wait_follows_the_first_in_line() {
    let (fifo, _cap) = captured(1);
    assert_eq!(fifo.oldest_wait(), Duration::ZERO);
    let held = fifo.acquire(Units::All).await;
    let first = fifo.enqueue(Units::ONE);
    tokio::time::sleep(Duration::from_secs(3)).await;
    let second = fifo.enqueue(Units::ONE);
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert_eq!(fifo.oldest_wait(), Duration::from_secs(5));
    drop(first);
    assert_eq!(fifo.oldest_wait(), Duration::from_secs(2));
    drop(second);
    assert_eq!(fifo.oldest_wait(), Duration::ZERO);
    drop(held);
}
