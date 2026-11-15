//! ENG-09: the FIFO's order, its places and the fair slices' yield claims, on tokio's
//! paused clock. Threads of the donor tests are tokio tasks here; `lock.release()` is the
//! drop of the place guard that `lock.acquire()` returned.
//!
//! Provenance: translated from project-maya serve/test_fair.py::FairLockOrder, serve/test_fair.py::FairLockYields and serve/test_multi.py::Places at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use console_core::fifo::{EngineFifo, FifoLog, PlaceGuard, TurnWait, Units};

fn fifo(n: usize) -> EngineFifo {
    EngineFifo::with_log(n, FifoLog::new(|_| {}))
}

/// Waits, a millisecond of paused time at a time, until `cond` holds.
async fn until(cond: impl Fn() -> bool) {
    for _ in 0..100_000 {
        if cond() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    panic!("condition not reached");
}

fn record() -> Arc<Mutex<Vec<String>>> {
    Arc::new(Mutex::new(Vec::new()))
}

fn seen(r: &Arc<Mutex<Vec<String>>>) -> Vec<String> {
    r.lock().map(|v| v.clone()).unwrap_or_default()
}

fn push(r: &Arc<Mutex<Vec<String>>>, s: &str) {
    if let Ok(mut v) = r.lock() {
        v.push(s.to_owned());
    }
}

// Donor: serve/test_fair.py::FairLockOrder::test_waiters_get_it_in_arrival_order
#[tokio::test(start_paused = true)]
async fn fair_lock_order_waiters_get_it_in_arrival_order() {
    let lock = fifo(1);
    let order = record();
    let held = lock.acquire(Units::All).await;
    let mut tasks = Vec::new();
    for i in 0..6 {
        let (l, o) = (lock.clone(), Arc::clone(&order));
        tasks.push(tokio::spawn(async move {
            let g = l.acquire(Units::All).await;
            push(&o, &i.to_string());
            drop(g);
        }));
        // The next one asks only once this one is in line.
        until(|| lock.waiting() > i).await;
    }
    drop(held);
    for t in tasks {
        assert!(matches!(
            tokio::time::timeout(Duration::from_secs(5), t).await,
            Ok(Ok(()))
        ));
    }
    let want: Vec<String> = (0..6).map(|i: i32| i.to_string()).collect();
    assert_eq!(seen(&order), want);
    assert!(!lock.locked());
}

// Donor: serve/test_fair.py::FairLockOrder::test_a_timeout_gives_up_its_place
#[tokio::test(start_paused = true)]
async fn fair_lock_order_a_timeout_gives_up_its_place() {
    let lock = fifo(1);
    let held = lock.acquire(Units::All).await;
    let start = tokio::time::Instant::now();
    assert!(lock
        .acquire_timeout(Units::All, Duration::from_millis(50))
        .await
        .is_none());
    assert_eq!(start.elapsed(), Duration::from_millis(50));
    assert_eq!(lock.waiting(), 0);
    drop(held);
    let again = lock.try_acquire(Units::All);
    assert!(again.is_some());
    drop(again);
    assert!(!lock.locked());
}

// Donor: serve/test_fair.py::FairLockOrder::test_a_place_survives_its_wakeups
#[tokio::test(start_paused = true)]
async fn fair_lock_order_a_place_survives_its_wakeups() {
    let lock = fifo(1);
    let held = lock.acquire(Units::All).await;
    let mine = lock.enqueue(Units::All);
    let mine = match mine.wait_turn(Some(Duration::from_millis(20))).await {
        TurnWait::TimedOut(t) => t,
        other => panic!("expected a timeout, got {other:?}"),
    };
    let l = lock.clone();
    let other = tokio::spawn(async move {
        drop(l.acquire(Units::All).await);
    });
    until(|| lock.waiting() >= 2).await;
    drop(held);
    // Still first in line, before the later task.
    let turn = match mine.wait_turn(Some(Duration::from_secs(5))).await {
        TurnWait::Granted(g) => g,
        other => panic!("expected the turn, got {other:?}"),
    };
    assert_eq!(lock.waiting(), 1);
    drop(turn);
    assert!(matches!(
        tokio::time::timeout(Duration::from_secs(5), other).await,
        Ok(Ok(()))
    ));
    assert!(!lock.locked());
}

/// A FIFO of `n` places, every one held by a runner.
fn full(n: usize) -> (EngineFifo, Vec<PlaceGuard>) {
    let lock = fifo(n);
    let guards: Vec<PlaceGuard> = (0..n)
        .filter_map(|_| lock.try_acquire(Units::ONE))
        .collect();
    assert_eq!(guards.len(), n);
    (lock, guards)
}

// Donor: serve/test_fair.py::FairLockYields::test_one_waiter_takes_one_place
#[tokio::test(start_paused = true)]
async fn fair_lock_yields_one_waiter_takes_one_place() {
    let (lock, _runners) = full(4);
    let _waiter = lock.enqueue(Units::ONE);
    assert!(lock.claim_yield(Duration::ZERO));
    // The others stay: it is covered.
    assert!(!lock.claim_yield(Duration::ZERO));
    // That runner went on instead.
    lock.unclaim_yield();
    assert!(lock.claim_yield(Duration::ZERO));
}

// Donor: serve/test_fair.py::FairLockYields::test_two_waiters_take_two
#[tokio::test(start_paused = true)]
async fn fair_lock_yields_two_waiters_take_two() {
    let (lock, _runners) = full(4);
    let _a = lock.enqueue(Units::ONE);
    let _b = lock.enqueue(Units::ONE);
    let claims: Vec<bool> = (0..3).map(|_| lock.claim_yield(Duration::ZERO)).collect();
    assert_eq!(claims, vec![true, true, false]);
}

// Donor: serve/test_fair.py::FairLockYields::test_nobody_waiting_or_a_place_free_nobody_yields
#[tokio::test(start_paused = true)]
async fn fair_lock_yields_nobody_waiting_or_a_place_free_nobody_yields() {
    let (lock, mut runners) = full(4);
    assert!(!lock.claim_yield(Duration::ZERO));
    // A place is free: the waiter takes it.
    drop(runners.pop());
    let _waiter = lock.enqueue(Units::ONE);
    assert!(!lock.claim_yield(Duration::ZERO));
    assert_eq!(lock.yield_claims(), 0);
}

// Donor: serve/test_fair.py::FairLockYields::test_yielding_frees_the_place_and_ends_the_claim
#[tokio::test(start_paused = true)]
async fn fair_lock_yields_yielding_frees_the_place_and_ends_the_claim() {
    let (lock, mut runners) = full(4);
    let first = lock.enqueue(Units::ONE);
    assert!(lock.claim_yield(Duration::ZERO));
    let yielder = runners.pop();
    assert!(yielder.is_some());
    let again = yielder.map(PlaceGuard::yield_place);
    assert_eq!(lock.yield_claims(), 0);
    // The waiter first, the runner behind it.
    let turn = match first.wait_turn(Some(Duration::from_secs(1))).await {
        TurnWait::Granted(g) => g,
        other => panic!("expected the turn, got {other:?}"),
    };
    assert_eq!(lock.waiting(), 1);
    // A runner put back is no reason yet to cut another...
    assert!(!lock.claim_yield(Duration::from_secs(30)));
    // ...after its own slice it is: long answers take turns.
    assert!(lock.claim_yield(Duration::ZERO));
    drop(again);
    assert_eq!(lock.waiting(), 0);
    drop(turn);
}

// Donor: serve/test_fair.py::FairLockYields::test_a_request_for_all_places_takes_all
#[tokio::test(start_paused = true)]
async fn fair_lock_yields_a_request_for_all_places_takes_all() {
    let (lock, _runners) = full(4);
    // An image encode, a reload.
    let _whole = lock.enqueue(Units::All);
    let claims: Vec<bool> = (0..5).map(|_| lock.claim_yield(Duration::ZERO)).collect();
    assert_eq!(claims, vec![true, true, true, true, false]);
}

// Donor: serve/test_multi.py::Places::test_n_requests_hold_n_places_and_a_whole_waits_for_all
#[tokio::test(start_paused = true)]
async fn places_n_requests_hold_n_places_and_a_whole_waits_for_all() {
    let lock = fifo(3);
    let mut held = Vec::new();
    for _ in 0..3 {
        let g = lock
            .acquire_timeout(Units::ONE, Duration::from_secs(1))
            .await;
        assert!(g.is_some());
        held.extend(g);
    }
    assert!(lock.try_acquire(Units::ONE).is_none());
    let got = record();
    let (l, r) = (lock.clone(), Arc::clone(&got));
    let whole = tokio::spawn(async move {
        let g = l.acquire(Units::All).await;
        push(&r, "all");
        drop(g);
    });
    until(|| lock.waiting() >= 1).await;
    drop(held.pop());
    tokio::time::sleep(Duration::from_millis(50)).await;
    // The exclusive waiter needs every place.
    assert!(seen(&got).is_empty());
    drop(held.pop());
    drop(held.pop());
    assert!(matches!(
        tokio::time::timeout(Duration::from_secs(5), whole).await,
        Ok(Ok(()))
    ));
    assert_eq!(seen(&got), vec!["all".to_owned()]);
    assert!(!lock.locked());
}

// Donor: serve/test_multi.py::Places::test_a_waiter_for_all_holds_back_later_ones
#[tokio::test(start_paused = true)]
async fn places_a_waiter_for_all_holds_back_later_ones() {
    let lock = fifo(2);
    let one = lock.acquire(Units::ONE).await;
    let order = record();
    let (l, o) = (lock.clone(), Arc::clone(&order));
    let a = tokio::spawn(async move {
        let g = l.acquire(Units::All).await;
        push(&o, "all");
        drop(g);
    });
    until(|| lock.waiting() >= 1).await;
    let (l, o) = (lock.clone(), Arc::clone(&order));
    let b = tokio::spawn(async move {
        let g = l.acquire(Units::ONE).await;
        push(&o, "one");
        drop(g);
    });
    until(|| lock.waiting() >= 2).await;
    tokio::time::sleep(Duration::from_millis(50)).await;
    // A free place, but the first in line wants both.
    assert!(seen(&order).is_empty());
    drop(one);
    assert!(matches!(
        tokio::time::timeout(Duration::from_secs(5), a).await,
        Ok(Ok(()))
    ));
    assert!(matches!(
        tokio::time::timeout(Duration::from_secs(5), b).await,
        Ok(Ok(()))
    ));
    assert_eq!(seen(&order), vec!["all".to_owned(), "one".to_owned()]);
    assert!(!lock.locked());
}
