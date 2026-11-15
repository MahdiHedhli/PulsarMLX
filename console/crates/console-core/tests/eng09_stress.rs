//! ENG-09: a stress test of the FIFO on tokio's paused clock. Each run makes 1,000 random
//! operations (acquire one place, several or all, with and without a timeout; queued waits
//! that are cancelled or dropped; places in line that are given up; yield claims, yields and
//! unclaims; capacity changes in the mixed run) from 24 tasks and ends with no place in use,
//! nobody in line and no yield claim outstanding. The random source is seeded, so every run
//! is reproducible.
//!
//! The test keeps its own tally of the places the tasks really hold (`held`: what each guard
//! was granted, counted at the grant and uncounted just before the drop or the yield), so
//! it does not check the FIFO's counter against itself. The tests run on one thread, so the
//! tally and the FIFO are read between the same two awaits.
//!
//! - Without capacity changes, after every operation: `held <= capacity`, `held == used`,
//!   and no over-release line is ever logged.
//! - With capacity changes (the mixed run), the donor's release of `Units::All` at the
//!   capacity of the moment (see `PlaceGuard`) can legitimately make `held` exceed the
//!   capacity and differ from `used`, so those moments are counted and reported rather than
//!   failed; the end state (`held == 0`, `used == 0`) is still asserted. The deterministic
//!   case is `an_exclusive_release_after_growth_frees_other_holders_as_the_donor_does`.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use console_core::engine::ControlHandle;
use console_core::fifo::{EngineFifo, FifoLog, Place, PlaceGuard, QueueStep, TurnWait, Units};

const OPERATIONS: usize = 1_000;
const TASKS: u64 = 24;

/// xorshift64*: small, seeded, good enough to shuffle operations.
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
        self.next() % n.max(1)
    }

    fn ms(&mut self, n: u64) -> Duration {
        Duration::from_millis(self.below(n))
    }
}

struct Shared {
    fifo: EngineFifo,
    resize: bool,
    ops: AtomicUsize,
    held: AtomicUsize,
    over_capacity: AtomicUsize,
    mismatches: AtomicUsize,
    grants: AtomicUsize,
    yields: AtomicUsize,
    guard_claims: AtomicUsize,
    cancels: AtomicUsize,
    resizes: AtomicUsize,
}

impl Shared {
    fn check(&self) {
        let held = self.held.load(Ordering::Relaxed);
        if held > self.fifo.capacity() {
            self.over_capacity.fetch_add(1, Ordering::Relaxed);
        }
        if held != self.fifo.used() {
            self.mismatches.fetch_add(1, Ordering::Relaxed);
        }
    }
}

/// A guard counted in the test's own tally from its grant until just before its drop or
/// its yield.
struct Held<'a> {
    shared: &'a Shared,
    guard: Option<PlaceGuard>,
}

impl<'a> Held<'a> {
    fn new(shared: &'a Shared, guard: PlaceGuard) -> Self {
        shared.held.fetch_add(guard.granted(), Ordering::Relaxed);
        shared.grants.fetch_add(1, Ordering::Relaxed);
        Self {
            shared,
            guard: Some(guard),
        }
    }

    fn uncount(&mut self) -> Option<PlaceGuard> {
        let g = self.guard.take();
        if let Some(g) = &g {
            self.shared.held.fetch_sub(g.granted(), Ordering::Relaxed);
        }
        g
    }

    fn yield_place(mut self) -> Option<Place> {
        self.uncount().map(PlaceGuard::yield_place)
    }
}

impl Drop for Held<'_> {
    fn drop(&mut self) {
        drop(self.uncount());
    }
}

async fn hold(shared: &Shared, rng: &mut Rng, guard: PlaceGuard) {
    let mut held = Held::new(shared, guard);
    shared.check();
    tokio::time::sleep(rng.ms(15)).await;
    shared.check();
    let slice = rng.ms(10);
    let claimed = if rng.below(3) != 0 {
        false
    } else if rng.below(2) == 0 {
        shared.fifo.claim_yield(slice)
    } else {
        // The claim tied to the guard: dropping the guard ends it.
        let c = held.guard.as_mut().is_some_and(|g| g.claim_yield(slice));
        if c {
            shared.guard_claims.fetch_add(1, Ordering::Relaxed);
        }
        c
    };
    if claimed {
        let guard_claim = held.guard.as_ref().is_some_and(PlaceGuard::has_yield_claim);
        match rng.below(3) {
            0 => {
                let place = held.yield_place();
                shared.yields.fetch_add(1, Ordering::Relaxed);
                shared.check();
                if let Some(place) = place {
                    match place.wait_turn(Some(rng.ms(40))).await {
                        TurnWait::Granted(g) => {
                            let again = Held::new(shared, g);
                            shared.check();
                            tokio::time::sleep(rng.ms(5)).await;
                            drop(again);
                        }
                        TurnWait::TimedOut(t) => drop(t),
                        TurnWait::Gone => {}
                    }
                }
            }
            1 if guard_claim => {
                // The turn ends without yielding: the drop ends the claim.
                drop(held);
            }
            _ => {
                if guard_claim {
                    if let Some(g) = held.guard.as_mut() {
                        g.unclaim_yield();
                    }
                } else {
                    shared.fifo.unclaim_yield();
                }
                drop(held);
            }
        }
    } else {
        drop(held);
    }
    shared.check();
}

async fn worker(shared: Arc<Shared>, seed: u64) {
    let mut rng = Rng::new(seed);
    while shared.ops.fetch_add(1, Ordering::Relaxed) < OPERATIONS {
        let fifo = shared.fifo.clone();
        match rng.below(100) {
            0..=29 => {
                let g = fifo.acquire(Units::ONE).await;
                hold(&shared, &mut rng, g).await;
            }
            30..=44 => {
                if let Some(g) = fifo.acquire_timeout(Units::ONE, rng.ms(60)).await {
                    hold(&shared, &mut rng, g).await;
                }
            }
            45..=52 => {
                if let Some(g) = fifo.acquire_timeout(Units::All, rng.ms(80)).await {
                    hold(&shared, &mut rng, g).await;
                }
            }
            53..=57 => {
                let g = fifo.acquire(Units::All).await;
                hold(&shared, &mut rng, g).await;
            }
            58..=65 => {
                let g = fifo.acquire(Units::Places(2)).await;
                hold(&shared, &mut rng, g).await;
            }
            66..=79 => {
                let control = ControlHandle::new();
                let c = control.clone();
                let after = rng.ms(60);
                let cancel = tokio::spawn(async move {
                    tokio::time::sleep(after).await;
                    c.cancel();
                });
                let mut wait =
                    fifo.queue_wait(Units::ONE, control.probe(), Some(Duration::from_millis(7)));
                let give_up = rng.below(4) == 0;
                let mut pings = 0;
                loop {
                    match wait.next().await {
                        QueueStep::Ping => {
                            pings += 1;
                            if give_up && pings >= 2 {
                                // The client went away at a ping.
                                drop(wait);
                                break;
                            }
                        }
                        QueueStep::Turn(g) => {
                            hold(&shared, &mut rng, g).await;
                            break;
                        }
                        QueueStep::Cancelled => {
                            shared.cancels.fetch_add(1, Ordering::Relaxed);
                            break;
                        }
                        QueueStep::Ended => break,
                    }
                }
                cancel.abort();
            }
            80..=89 => {
                let t = fifo.enqueue(if rng.below(2) == 0 {
                    Units::ONE
                } else {
                    Units::All
                });
                match t.wait_turn(Some(rng.ms(20))).await {
                    TurnWait::Granted(g) => hold(&shared, &mut rng, g).await,
                    TurnWait::TimedOut(t) => drop(t),
                    TurnWait::Gone => {}
                }
            }
            _ => {
                if shared.resize {
                    let n = usize::try_from(rng.below(4) + 1).unwrap_or(1);
                    fifo.set_capacity(n);
                    shared.resizes.fetch_add(1, Ordering::Relaxed);
                }
                tokio::time::sleep(rng.ms(10)).await;
            }
        }
        shared.check();
    }
}

/// What a run saw at its checks, in the mixed run only reported.
struct Seen {
    over_capacity: usize,
    mismatches: usize,
}

async fn run(seed: u64, resize: bool) -> Seen {
    let (log, cap) = FifoLog::capture();
    let fifo = EngineFifo::with_log(3, log);
    let shared = Arc::new(Shared {
        fifo: fifo.clone(),
        resize,
        ops: AtomicUsize::new(0),
        held: AtomicUsize::new(0),
        over_capacity: AtomicUsize::new(0),
        mismatches: AtomicUsize::new(0),
        grants: AtomicUsize::new(0),
        yields: AtomicUsize::new(0),
        guard_claims: AtomicUsize::new(0),
        cancels: AtomicUsize::new(0),
        resizes: AtomicUsize::new(0),
    });
    let tasks: Vec<_> = (0..TASKS)
        .map(|i| tokio::spawn(worker(Arc::clone(&shared), seed * 1_000 + i)))
        .collect();
    for t in tasks {
        let done = tokio::time::timeout(Duration::from_secs(3_600), t).await;
        assert!(
            matches!(done, Ok(Ok(()))),
            "seed {seed}: a task did not finish"
        );
    }
    assert!(shared.ops.load(Ordering::Relaxed) >= OPERATIONS);
    // The run exercised every kind of operation, not only the fast path.
    let count = |c: &AtomicUsize| c.load(Ordering::Relaxed);
    assert!(
        count(&shared.grants) >= 300,
        "seed {seed}: grants {}",
        count(&shared.grants)
    );
    assert!(count(&shared.yields) > 0, "seed {seed}: no yield");
    assert!(
        count(&shared.guard_claims) > 0,
        "seed {seed}: no claim through a guard"
    );
    assert!(count(&shared.cancels) > 0, "seed {seed}: no cancel");
    assert_eq!(
        count(&shared.resizes) > 0,
        resize,
        "seed {seed}: capacity changes"
    );
    assert_eq!(count(&shared.held), 0, "seed {seed}: places left held");
    assert_eq!(fifo.used(), 0, "seed {seed}: places left in use");
    assert_eq!(fifo.waiting(), 0, "seed {seed}: entries left in line");
    assert_eq!(fifo.yield_claims(), 0, "seed {seed}: yield claims left");
    assert!(!fifo.locked());
    let seen = Seen {
        over_capacity: count(&shared.over_capacity),
        mismatches: count(&shared.mismatches),
    };
    if !resize {
        assert_eq!(
            seen.over_capacity, 0,
            "seed {seed}: places held above the capacity"
        );
        assert_eq!(
            seen.mismatches, 0,
            "seed {seed}: places held differ from places in use"
        );
        let over: Vec<String> = cap
            .lines()
            .into_iter()
            .filter(|l| l.contains("given back that is not held"))
            .collect();
        assert!(over.is_empty(), "seed {seed}: over-release: {over:?}");
    }
    seen
}

#[tokio::test(start_paused = true)]
async fn a_thousand_random_operations_never_exceed_capacity_and_end_empty() {
    run(1, false).await;
}

#[tokio::test(start_paused = true)]
async fn the_stress_holds_across_seeds() {
    for seed in 2..10 {
        run(seed, false).await;
    }
}

#[tokio::test(start_paused = true)]
async fn the_stress_with_capacity_changes_ends_empty() {
    let mut over = 0;
    let mut mismatched = 0;
    for seed in 1..10 {
        let seen = run(seed, true).await;
        over += seen.over_capacity;
        mismatched += seen.mismatches;
    }
    // Reported, not failed: the donor's release of `Units::All` at the capacity of the
    // moment makes these possible after a capacity change (see `PlaceGuard`).
    println!(
        "with capacity changes: {over} check(s) with more places held than the capacity, \
         {mismatched} with places held differing from places in use"
    );
}

#[tokio::test(start_paused = true)]
async fn an_exclusive_release_after_growth_frees_other_holders_as_the_donor_does() {
    // Donor: serve/server.py:364-375 (`release(units=None)` resolves at the capacity of the
    // moment). Kept as the donor has it; see the hazard note on `PlaceGuard`.
    let fifo = EngineFifo::with_log(1, FifoLog::new(|_| {}));
    let exclusive = fifo.try_acquire(Units::All);
    assert_eq!(exclusive.as_ref().map(PlaceGuard::granted), Some(1));
    // A restart under the exclusive hold brings up an engine with more places.
    fifo.set_capacity(4);
    let others: Vec<PlaceGuard> = (0..3)
        .filter_map(|_| fifo.try_acquire(Units::ONE))
        .collect();
    assert_eq!(others.len(), 3);
    assert_eq!(fifo.used(), 4);
    // The exclusive holder gives back the new capacity, not the place it was granted.
    drop(exclusive);
    assert_eq!(fifo.used(), 0);
    let second = fifo.try_acquire(Units::All);
    assert_eq!(second.as_ref().map(PlaceGuard::granted), Some(4));
    let held: usize = others.iter().map(PlaceGuard::granted).sum::<usize>()
        + second.as_ref().map_or(0, PlaceGuard::granted);
    assert_eq!(held, 7);
    assert!(held > fifo.capacity());
    drop((others, second));
}
