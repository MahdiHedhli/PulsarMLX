//! The FIFO itself: places in arrival order, exclusive holders, yields and introspection.
//!
//! Behavior reference: project-maya serve/server.py:243-393 at 7e68a30f (`FairLock`).
//!
//! The state is a plain `std::sync::Mutex` (never held across an `.await`) and the
//! condition variable is a `tokio::sync::Notify` whose `notify_waiters` plays
//! `notify_all`. A waiter enables its `Notified` future before it looks at the state, so a
//! release between the look and the wait is never lost. Releasing a place is synchronous,
//! which is what lets [`PlaceGuard`] give it back in `Drop` on any thread.

use std::collections::VecDeque;
use std::fmt;
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::Duration;

use tokio::sync::Notify;
use tokio::time::Instant;

use super::log::FifoLog;

/// How many places a holder asks for.
///
/// Behavior reference: project-maya serve/server.py:270-271 at 7e68a30f (`_units`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Units {
    /// Every place the engine has, resolved against the capacity at the moment it is used
    /// (the donor's `units=None`): exclusive work such as an image encode, a context
    /// reload, an unload, a restart for a switch, or shutdown.
    All,
    /// This many places, clamped to between 1 and the capacity when used. A request takes
    /// `Places(1)`.
    Places(usize),
}

impl Units {
    /// One place: what a request takes.
    pub const ONE: Units = Units::Places(1);

    fn resolve(self, capacity: usize) -> usize {
        match self {
            Units::All => capacity,
            Units::Places(n) => n.clamp(1, capacity.max(1)),
        }
    }
}

/// One entry in line. `requeued` marks a runner a fair slice put back in line.
#[derive(Debug)]
struct Entry {
    id: u64,
    units: usize,
    asked: Instant,
    requeued: bool,
}

/// What a look at the line found for one entry.
enum Look {
    /// First in line and its places are free: they are now held, this many.
    Granted(usize),
    /// Still in line.
    NotYet,
    /// No longer in line.
    Gone,
}

#[derive(Debug)]
struct State {
    /// Sorted by id: entries are only ever pushed at the back with an id from `next_id`,
    /// which only grows (a u64 does not wrap in practice), and removals keep the order.
    queue: VecDeque<Entry>,
    capacity: usize,
    used: usize,
    yields: usize,
    next_id: u64,
}

impl State {
    fn enqueue(&mut self, units: usize, requeued: bool) -> u64 {
        let id = self.next_id;
        self.next_id = self.next_id.wrapping_add(1);
        self.queue.push_back(Entry {
            id,
            units,
            asked: Instant::now(),
            requeued,
        });
        id
    }

    /// Where entry `id` is in line, found in O(log n) since the line is sorted by id.
    fn position(&self, id: u64) -> Option<usize> {
        if self.queue.front().map(|e| e.id) == Some(id) {
            return Some(0);
        }
        self.queue.binary_search_by_key(&id, |e| e.id).ok()
    }

    fn look(&mut self, id: u64) -> Look {
        let Some(pos) = self.position(id) else {
            return Look::Gone;
        };
        if pos != 0 {
            return Look::NotYet;
        }
        let want = self.queue.front().map_or(1, |e| e.units.min(self.capacity));
        if self.used.saturating_add(want) > self.capacity {
            return Look::NotYet;
        }
        self.queue.pop_front();
        self.used += want;
        Look::Granted(want)
    }

    fn remove(&mut self, id: u64) -> bool {
        match self.position(id) {
            Some(pos) => {
                self.queue.remove(pos);
                true
            }
            None => false,
        }
    }

    fn held_by(&self) -> String {
        format!("{} of {} place(s) in use", self.used, self.capacity)
    }
}

pub(super) struct Inner {
    state: Mutex<State>,
    notify: Notify,
    log: FifoLog,
}

impl Inner {
    fn lock(&self) -> MutexGuard<'_, State> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Gives back places: `release(units)` of the donor, synchronous.
    ///
    /// Behavior reference: project-maya serve/server.py:364-375 at 7e68a30f.
    fn release(&self, units: Units) {
        let note = {
            let mut st = self.lock();
            let mut k = units.resolve(st.capacity);
            let mut note = None;
            if st.used < k {
                note = Some(format!(
                    "[console] a place was given back that is not held ({k} of {} in use, \
                     capacity {}): the engine's conversations changed while it ran",
                    st.used, st.capacity
                ));
                k = st.used;
            }
            st.used -= k;
            note
        };
        self.notify.notify_waiters();
        if let Some(line) = note {
            self.log.line(&line);
        }
    }

    /// Ends one yield claim, never going below zero.
    fn end_claim(&self) {
        let mut st = self.lock();
        st.yields = st.yields.saturating_sub(1);
    }

    fn leave(&self, id: u64) {
        let removed = self.lock().remove(id);
        if removed {
            // The next one may now be first in line.
            self.notify.notify_waiters();
        }
    }

    /// Waits until entry `id` holds its places (`Granted`), until `deadline` (`TimedOut`),
    /// or finds it no longer in line (`Gone`). Cancel-safe: dropping the future leaves the
    /// entry in line, holding nothing.
    ///
    /// Behavior reference: project-maya serve/server.py:336-355 at 7e68a30f (`wait_turn`).
    pub(super) async fn wait_entry(&self, id: u64, deadline: Option<Instant>) -> EntryWait {
        loop {
            let notified = self.notify.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            let look = self.lock().look(id);
            match look {
                Look::Granted(k) => {
                    // The next in line may fit in what is left.
                    self.notify.notify_waiters();
                    return EntryWait::Granted(k);
                }
                Look::Gone => return EntryWait::Gone,
                Look::NotYet => {}
            }
            match deadline {
                None => notified.await,
                Some(d) => {
                    if Instant::now() >= d {
                        return EntryWait::TimedOut;
                    }
                    tokio::select! {
                        () = &mut notified => {}
                        () = tokio::time::sleep_until(d) => {}
                    }
                }
            }
        }
    }
}

/// What [`Inner::wait_entry`] ended with.
pub(super) enum EntryWait {
    Granted(usize),
    TimedOut,
    Gone,
}

/// The engine's FIFO: requests get the engine in the order they asked, a holder can see
/// that someone waits, and an engine with several conversations has that many places.
///
/// Capacity is `max(1, n)`. A request takes one place; exclusive work takes them all
/// ([`Units::All`]). Places go in arrival order: a waiter for every place holds back the
/// waiters behind it, so it is never starved. With nobody in line and the places free,
/// acquisition takes the fast path without queueing.
///
/// Cloning gives another handle to the same FIFO. `Send + Sync`.
///
/// Behavior reference: project-maya serve/server.py:243-393 at 7e68a30f.
#[derive(Clone)]
pub struct EngineFifo {
    pub(super) inner: Arc<Inner>,
}

impl fmt::Debug for EngineFifo {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let st = self.inner.lock();
        f.debug_struct("EngineFifo")
            .field("capacity", &st.capacity)
            .field("used", &st.used)
            .field("waiting", &st.queue.len())
            .field("yields", &st.yields)
            .finish()
    }
}

impl EngineFifo {
    /// A FIFO with `max(1, capacity)` places, logging to standard output.
    ///
    /// Behavior reference: project-maya serve/server.py:252-257 at 7e68a30f.
    pub fn new(capacity: usize) -> Self {
        Self::with_log(capacity, FifoLog::stdout())
    }

    /// A FIFO with `max(1, capacity)` places, logging to `log`.
    pub fn with_log(capacity: usize, log: FifoLog) -> Self {
        Self {
            inner: Arc::new(Inner {
                state: Mutex::new(State {
                    queue: VecDeque::new(),
                    capacity: capacity.max(1),
                    used: 0,
                    yields: 0,
                    next_id: 0,
                }),
                notify: Notify::new(),
                log,
            }),
        }
    }

    pub(super) fn log(&self) -> &FifoLog {
        &self.inner.log
    }

    /// Follows the engine's places after a restart or reload: logs a change, and clamps the
    /// places in use to the new capacity, so a holder sized by the old capacity cannot jam
    /// the line (its release is then clamped too, with a line).
    ///
    /// Behavior reference: project-maya serve/server.py:259-268 at 7e68a30f.
    pub fn set_capacity(&self, n: usize) {
        let note = {
            let mut st = self.inner.lock();
            let n = n.max(1);
            let note = (n != st.capacity).then(|| {
                format!(
                    "[console] the engine's places: {} -> {n} ({} in use)",
                    st.capacity, st.used
                )
            });
            st.capacity = n;
            st.used = st.used.min(n);
            note
        };
        self.inner.notify.notify_waiters();
        if let Some(line) = note {
            self.inner.log.line(&line);
        }
    }

    /// The places taken at once, or `None` without queueing: the fast path only (the
    /// donor's `acquire(blocking=False)`).
    ///
    /// Behavior reference: project-maya serve/server.py:273-279 at 7e68a30f.
    pub fn try_acquire(&self, units: Units) -> Option<PlaceGuard> {
        let mut st = self.inner.lock();
        let k = units.resolve(st.capacity);
        if st.queue.is_empty() && st.used.saturating_add(k) <= st.capacity {
            st.used += k;
            drop(st);
            return Some(PlaceGuard::new(self.clone(), units, k));
        }
        None
    }

    /// The places, waiting in line as long as it takes.
    ///
    /// Cancel-safe: dropping the future gives up the place in line and holds nothing.
    ///
    /// Behavior reference: project-maya serve/server.py:273-285 at 7e68a30f.
    pub async fn acquire(&self, units: Units) -> PlaceGuard {
        loop {
            if let Some(g) = self.try_acquire(units) {
                return g;
            }
            match self.enqueue(units).wait_turn(None).await {
                TurnWait::Granted(g) => return g,
                // Not reachable without a deadline, and the place in line is ours alone; asking
                // again keeps the call total.
                TurnWait::TimedOut(_) | TurnWait::Gone => continue,
            }
        }
    }

    /// The places, or `None` after `timeout` in line; on a timeout the place in line is
    /// given up (the donor's `acquire(timeout=...)`).
    ///
    /// Behavior reference: project-maya serve/server.py:273-285 at 7e68a30f.
    pub async fn acquire_timeout(&self, units: Units, timeout: Duration) -> Option<PlaceGuard> {
        if let Some(g) = self.try_acquire(units) {
            return Some(g);
        }
        match self.enqueue(units).wait_turn(Some(timeout)).await {
            TurnWait::Granted(g) => Some(g),
            // The place in line is dropped here, which leaves the line.
            TurnWait::TimedOut(_) | TurnWait::Gone => None,
        }
    }

    /// A place in line. A waiter that wakes now and then (to send a heartbeat) keeps it;
    /// dropping the place in line gives it up.
    ///
    /// Behavior reference: project-maya serve/server.py:287-293 at 7e68a30f.
    pub fn enqueue(&self, units: Units) -> Place {
        let (id, k) = {
            let mut st = self.inner.lock();
            let k = units.resolve(st.capacity);
            (st.enqueue(k, false), k)
        };
        Place::new(self.clone(), id, units, k)
    }

    /// The fair slices' decision, made one runner at a time: true when this runner should
    /// give its place up now, and then counted until it does ([`PlaceGuard::yield_place`])
    /// or says it did not ([`EngineFifo::unclaim_yield`]).
    ///
    /// The waiters that count are those that never ran, and those a slice put back in line
    /// once they have waited `slice` themselves; what they need, less the free places and
    /// the runners already on their way out, is how many more runners yield.
    ///
    /// A claim made here is not tied to any guard: the caller must end it on every path,
    /// cancellation and a dropped task included, with [`PlaceGuard::yield_place`] or
    /// [`EngineFifo::unclaim_yield`], or one fewer runner ever yields afterwards. The turn
    /// driver should use [`PlaceGuard::claim_yield`] instead, whose claim ends when the guard
    /// is dropped.
    ///
    /// Behavior reference: project-maya serve/server.py:295-312 at 7e68a30f.
    pub fn claim_yield(&self, slice: Duration) -> bool {
        let now = Instant::now();
        let mut st = self.inner.lock();
        let cap = st.capacity;
        let need: usize = st
            .queue
            .iter()
            .filter(|e| !e.requeued || now.saturating_duration_since(e.asked) >= slice)
            .map(|e| e.units.min(cap))
            .fold(0usize, usize::saturating_add);
        let free = cap.saturating_sub(st.used);
        if need > free.saturating_add(st.yields) {
            st.yields += 1;
            return true;
        }
        false
    }

    /// A claimed yield that did not happen (the runner went on instead).
    ///
    /// Behavior reference: project-maya serve/server.py:314-316 at 7e68a30f.
    pub fn unclaim_yield(&self) {
        self.inner.end_claim();
    }

    /// Requests in line, exclusive waiters and requeued runners included.
    ///
    /// Behavior reference: project-maya serve/server.py:380-381 at 7e68a30f.
    pub fn waiting(&self) -> usize {
        self.inner.lock().queue.len()
    }

    /// How long the first in line has waited; zero when nobody waits.
    ///
    /// Behavior reference: project-maya serve/server.py:383-389 at 7e68a30f.
    pub fn oldest_wait(&self) -> Duration {
        let st = self.inner.lock();
        st.queue.front().map_or(Duration::ZERO, |e| {
            Instant::now().saturating_duration_since(e.asked)
        })
    }

    /// `"<used> of <capacity> place(s) in use"`, for the queue watchdog's line.
    ///
    /// Behavior reference: project-maya serve/server.py:391-394 at 7e68a30f.
    pub fn held_by(&self) -> String {
        self.inner.lock().held_by()
    }

    /// True while any place is held.
    ///
    /// Behavior reference: project-maya serve/server.py:377-378 at 7e68a30f.
    pub fn locked(&self) -> bool {
        self.inner.lock().used > 0
    }

    /// The engine's places.
    pub fn capacity(&self) -> usize {
        self.inner.lock().capacity
    }

    /// The places in use; never above [`EngineFifo::capacity`].
    pub fn used(&self) -> usize {
        self.inner.lock().used
    }

    /// Runners that claimed a yield and have not yet yielded or unclaimed it.
    pub fn yield_claims(&self) -> usize {
        self.inner.lock().yields
    }

    #[cfg(test)]
    pub(super) fn remove_for_test(&self, ticket: &Place) {
        self.inner.leave(ticket.id);
    }
}

/// A place in line, from [`EngineFifo::enqueue`] or [`PlaceGuard::yield_place`]. Dropping
/// it gives the place in line up (the donor's `leave`). `Send`.
#[derive(Debug)]
pub struct Place {
    fifo: EngineFifo,
    id: u64,
    units: Units,
    entry_units: usize,
    live: bool,
}

/// What [`Place::wait_turn`] ended with.
#[derive(Debug)]
pub enum TurnWait {
    /// First in line with the places free: they are held now.
    Granted(PlaceGuard),
    /// The timeout passed; the place in line is still in line, in the same place.
    TimedOut(Place),
    /// The entry was no longer in line (the donor returns false at once).
    Gone,
}

impl Place {
    fn new(fifo: EngineFifo, id: u64, units: Units, entry_units: usize) -> Self {
        Self {
            fifo,
            id,
            units,
            entry_units,
            live: true,
        }
    }

    /// The places this place in line asked for.
    pub fn units(&self) -> Units {
        self.units
    }

    /// The places counted for this place in line (resolved against the capacity when it
    /// joined).
    pub fn entry_units(&self) -> usize {
        self.entry_units
    }

    /// Waits until this place is first in line and its places are free, then holds them.
    /// `None` waits for ever. On a timeout the place comes back, still in line.
    ///
    /// Cancel-safe: dropping the future drops the place in line, which leaves the line.
    ///
    /// Behavior reference: project-maya serve/server.py:336-355 at 7e68a30f.
    pub async fn wait_turn(self, timeout: Option<Duration>) -> TurnWait {
        let deadline = timeout.map(|t| deadline_after(Instant::now(), t));
        let mut me = self;
        match me.fifo.inner.wait_entry(me.id, deadline).await {
            EntryWait::Granted(k) => TurnWait::Granted(me.into_guard(k)),
            EntryWait::TimedOut => TurnWait::TimedOut(me),
            EntryWait::Gone => {
                me.live = false;
                TurnWait::Gone
            }
        }
    }

    pub(super) fn id(&self) -> u64 {
        self.id
    }

    /// Turns a granted place in line into the guard of the `k` places it now holds.
    pub(super) fn into_guard(mut self, k: usize) -> PlaceGuard {
        self.live = false;
        PlaceGuard::new(self.fifo.clone(), self.units, k)
    }

    /// Marks a place in line whose entry is already gone, so dropping it does nothing.
    pub(super) fn forget(mut self) {
        self.live = false;
    }
}

impl Drop for Place {
    fn drop(&mut self) {
        if self.live {
            self.fifo.inner.leave(self.id);
        }
    }
}

/// Thirty years: the stand-in for a deadline too far to represent.
const FAR_FUTURE: Duration = Duration::from_secs(86_400 * 365 * 30);

/// `start + d`, saturating far in the future instead of overflowing.
pub(super) fn deadline_after(start: Instant, d: Duration) -> Instant {
    start
        .checked_add(d)
        .or_else(|| start.checked_add(FAR_FUTURE))
        .unwrap_or(start)
}

/// Places held. Dropping the guard gives them back at once, synchronously and on any
/// thread, so a cancelled waiter, a dropped stream or a panicking turn never leaks a place.
/// `Send + 'static`: the turn driver can hand it to the engine's driver thread and drop it
/// there after the engine call has really returned (contracts/backend-seam.md section 4,
/// rule 4).
///
/// The release resolves [`Units`] against the capacity at release time, as the donor's
/// `release(units)` does, and a release of more than is held after a capacity change gives
/// back what is held, with a log line.
///
/// Known donor hazard, kept as the donor has it: the release is not the `granted` count. A
/// holder of [`Units::All`] whose capacity grew while it held (a restart or a model switch
/// that brings up an engine with more conversations, then `set_capacity`) gives back the
/// new capacity, which frees the places of requests granted after the growth. The FIFO's
/// count then reads lower than the places really held, and a second exclusive holder can
/// be granted beside running requests. `tests/eng09_stress.rs` shows the case; whether to
/// release `granted` instead is a question for the lead (it would need a deviation).
///
/// Behavior reference: project-maya serve/server.py:364-375 at 7e68a30f.
pub struct PlaceGuard {
    fifo: EngineFifo,
    units: Units,
    granted: usize,
    given_back: bool,
    claimed: bool,
}

impl fmt::Debug for PlaceGuard {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PlaceGuard")
            .field("units", &self.units)
            .field("granted", &self.granted)
            .field("claimed", &self.claimed)
            .finish()
    }
}

impl PlaceGuard {
    fn new(fifo: EngineFifo, units: Units, granted: usize) -> Self {
        Self {
            fifo,
            units,
            granted,
            given_back: false,
            claimed: false,
        }
    }

    /// The places this guard asked for.
    pub fn units(&self) -> Units {
        self.units
    }

    /// The places counted when they were granted.
    pub fn granted(&self) -> usize {
        self.granted
    }

    /// Gives the places back now (the same as dropping the guard).
    pub fn release(self) {
        drop(self);
    }

    /// [`EngineFifo::claim_yield`] for the runner that holds this guard, with the claim
    /// tied to the guard: it ends with [`PlaceGuard::yield_place`],
    /// [`PlaceGuard::unclaim_yield`], or the drop of the guard (a cancelled or dropped turn
    /// task included), which is what the donor's `finally` guarantees. A guard holds at most
    /// one claim: asked again while it holds one, it answers true and counts nothing more.
    ///
    /// Behavior reference: project-maya serve/server.py:295-312, 4161-4177 at 7e68a30f.
    pub fn claim_yield(&mut self, slice: Duration) -> bool {
        if self.claimed {
            return true;
        }
        self.claimed = self.fifo.claim_yield(slice);
        self.claimed
    }

    /// Ends this guard's claim without yielding (the runner went on instead); nothing
    /// happens when it holds none.
    ///
    /// Behavior reference: project-maya serve/server.py:314-316 at 7e68a30f.
    pub fn unclaim_yield(&mut self) {
        if self.claimed {
            self.claimed = false;
            self.fifo.inner.end_claim();
        }
    }

    /// True while this guard holds a yield claim.
    pub fn has_yield_claim(&self) -> bool {
        self.claimed
    }

    /// A runner's places given up, and a place in line behind whoever waits now, in one
    /// step; a claim ends with it (one claim, whether made with
    /// [`PlaceGuard::claim_yield`] or with [`EngineFifo::claim_yield`]). The places
    /// are resolved against the capacity now, and the release is clamped to what is in use
    /// without a log line.
    ///
    /// Behavior reference: project-maya serve/server.py:318-334 at 7e68a30f.
    pub fn yield_place(mut self) -> Place {
        self.given_back = true;
        self.claimed = false;
        let fifo = self.fifo.clone();
        let (id, k) = {
            let mut st = fifo.inner.lock();
            let k = self.units.resolve(st.capacity);
            let id = st.enqueue(k, true);
            st.used -= k.min(st.used);
            st.yields = st.yields.saturating_sub(1);
            (id, k)
        };
        fifo.inner.notify.notify_waiters();
        Place::new(fifo, id, self.units, k)
    }
}

impl Drop for PlaceGuard {
    fn drop(&mut self) {
        if self.claimed {
            self.claimed = false;
            self.fifo.inner.end_claim();
        }
        if !self.given_back {
            self.given_back = true;
            self.fifo.inner.release(self.units);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn quiet(n: usize) -> EngineFifo {
        EngineFifo::with_log(n, FifoLog::new(|_| {}))
    }

    fn assert_send_sync<T: Send + Sync + 'static>() {}
    fn assert_send<T: Send + 'static>() {}

    #[test]
    fn handles_cross_threads() {
        assert_send_sync::<EngineFifo>();
        assert_send::<PlaceGuard>();
        assert_send::<Place>();
    }

    #[test]
    fn units_resolve_like_the_donor() {
        assert_eq!(Units::All.resolve(3), 3);
        assert_eq!(Units::Places(0).resolve(3), 1);
        assert_eq!(Units::Places(2).resolve(3), 2);
        assert_eq!(Units::Places(9).resolve(3), 3);
        assert_eq!(Units::ONE.resolve(1), 1);
    }

    #[test]
    fn capacity_is_at_least_one() {
        let f = quiet(0);
        assert_eq!(f.capacity(), 1);
        f.set_capacity(0);
        assert_eq!(f.capacity(), 1);
    }

    #[test]
    fn held_by_and_locked() {
        let f = quiet(3);
        assert!(!f.locked());
        assert_eq!(f.held_by(), "0 of 3 place(s) in use");
        let g = f.try_acquire(Units::Places(2));
        assert!(g.is_some());
        assert!(f.locked());
        assert_eq!(f.held_by(), "2 of 3 place(s) in use");
        drop(g);
        assert!(!f.locked());
    }

    #[test]
    fn fast_path_is_refused_while_anyone_waits() {
        let f = quiet(2);
        let g = f.try_acquire(Units::All);
        assert!(g.is_some());
        let t = f.enqueue(Units::ONE);
        drop(g);
        // A place is free, but someone is in line: no fast path past it.
        assert!(f.try_acquire(Units::ONE).is_none());
        drop(t);
        assert_eq!(f.waiting(), 0);
        assert!(f.try_acquire(Units::ONE).is_some());
    }

    #[test]
    fn a_panicking_holder_gives_its_place_back() {
        let f = quiet(1);
        let g = f.try_acquire(Units::All);
        let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
            let _held = g;
            panic!("turn failed");
        }));
        assert!(r.is_err());
        assert!(!f.locked());
    }

    #[test]
    fn a_guard_dropped_on_another_thread_gives_its_place_back() {
        let f = quiet(1);
        let g = f.try_acquire(Units::All);
        assert!(f.locked());
        let t = std::thread::spawn(move || drop(g));
        assert!(t.join().is_ok());
        assert!(!f.locked());
    }

    #[test]
    fn over_release_is_clamped_with_a_line() {
        let (log, cap) = FifoLog::capture();
        let f = EngineFifo::with_log(4, log);
        f.inner.release(Units::ONE);
        assert_eq!(f.used(), 0);
        assert_eq!(
            cap.take(),
            vec![
                "[console] a place was given back that is not held (1 of 0 in use, capacity \
                 4): the engine's conversations changed while it ran"
                    .to_owned()
            ]
        );
    }

    #[tokio::test(start_paused = true)]
    async fn a_removed_ticket_returns_at_once() {
        let f = quiet(1);
        let g = f.try_acquire(Units::All);
        let t = f.enqueue(Units::All);
        f.remove_for_test(&t);
        let start = Instant::now();
        assert!(matches!(t.wait_turn(None).await, TurnWait::Gone));
        assert_eq!(Instant::now(), start);
        drop(g);
    }

    #[tokio::test(start_paused = true)]
    async fn a_dropped_wait_leaves_the_line() {
        let f = quiet(1);
        let g = f.try_acquire(Units::All);
        let t = f.enqueue(Units::All);
        let r = tokio::time::timeout(Duration::from_millis(10), t.wait_turn(None)).await;
        assert!(r.is_err());
        assert_eq!(f.waiting(), 0);
        drop(g);
        assert!(!f.locked());
    }

    #[test]
    fn yield_place_requeues_behind_the_waiters() {
        let f = quiet(2);
        let a = f.try_acquire(Units::ONE);
        let b = f.try_acquire(Units::ONE);
        let waiter = f.enqueue(Units::ONE);
        assert!(f.claim_yield(Duration::ZERO));
        assert_eq!(f.yield_claims(), 1);
        let again = a.map(PlaceGuard::yield_place);
        assert_eq!(f.yield_claims(), 0);
        assert_eq!(f.used(), 1);
        assert_eq!(f.waiting(), 2);
        let front = f.inner.lock().queue.front().map(|e| e.id);
        assert_eq!(front, Some(waiter.id));
        drop((again, b, waiter));
        assert_eq!(f.used(), 0);
        assert_eq!(f.waiting(), 0);
    }

    #[test]
    fn a_dropped_guard_ends_its_yield_claim() {
        let f = quiet(1);
        let mut g = f.try_acquire(Units::ONE);
        let waiter = f.enqueue(Units::ONE);
        assert_eq!(
            g.as_mut().map(|g| g.claim_yield(Duration::ZERO)),
            Some(true)
        );
        // Asked again, the claim stands and is not counted twice.
        assert_eq!(
            g.as_mut().map(|g| g.claim_yield(Duration::ZERO)),
            Some(true)
        );
        assert_eq!(f.yield_claims(), 1);
        assert_eq!(g.as_ref().map(PlaceGuard::has_yield_claim), Some(true));
        // The turn task is dropped between the claim and the yield.
        drop(g);
        assert_eq!(f.yield_claims(), 0);
        assert_eq!(f.used(), 0);
        drop(waiter);
    }

    #[test]
    fn a_guard_claim_ends_with_an_unclaim_or_a_yield() {
        let f = quiet(2);
        let mut a = f.try_acquire(Units::ONE);
        let mut b = f.try_acquire(Units::ONE);
        let waiter = f.enqueue(Units::ONE);
        assert_eq!(
            a.as_mut().map(|g| g.claim_yield(Duration::ZERO)),
            Some(true)
        );
        // Covered by the first claim: the second runner stays.
        assert_eq!(
            b.as_mut().map(|g| g.claim_yield(Duration::ZERO)),
            Some(false)
        );
        if let Some(g) = a.as_mut() {
            g.unclaim_yield();
            g.unclaim_yield();
        }
        assert_eq!(f.yield_claims(), 0);
        assert_eq!(
            b.as_mut().map(|g| g.claim_yield(Duration::ZERO)),
            Some(true)
        );
        let again = b.map(PlaceGuard::yield_place);
        assert_eq!(f.yield_claims(), 0);
        drop((a, again, waiter));
        assert_eq!(f.yield_claims(), 0);
        assert_eq!(f.used(), 0);
        assert_eq!(f.waiting(), 0);
    }

    #[test]
    fn the_line_stays_sorted_and_is_searched_by_id() {
        let f = quiet(1);
        let g = f.try_acquire(Units::All);
        let places: Vec<Place> = (0..9).map(|_| f.enqueue(Units::ONE)).collect();
        let mut kept = Vec::new();
        for (i, p) in places.into_iter().enumerate() {
            if i % 3 == 1 {
                drop(p);
            } else {
                kept.push(p);
            }
        }
        {
            let st = f.inner.lock();
            assert!(st
                .queue
                .iter()
                .zip(st.queue.iter().skip(1))
                .all(|(a, b)| a.id < b.id));
            for p in &kept {
                assert!(st.position(p.id).is_some());
            }
            assert_eq!(st.position(kept[0].id), Some(0));
            assert_eq!(st.position(u64::MAX), None);
        }
        assert_eq!(f.waiting(), 6);
        drop(kept);
        assert_eq!(f.waiting(), 0);
        drop(g);
    }

    #[test]
    fn deadline_saturates() {
        let now = Instant::now();
        assert!(deadline_after(now, Duration::MAX) > now);
    }
}
