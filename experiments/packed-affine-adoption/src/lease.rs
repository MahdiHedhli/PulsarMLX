//! Serial whole-buffer lease transitions. Native completion is supplied only by
//! the private owner after actual eval/sync and consumer release.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum State {
    Free,
    Filling,
    Ready,
    Leased,
    Quarantined,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Generation {
    slot: usize,
    number: u64,
}
impl Generation {
    pub fn slot(self) -> usize {
        self.slot
    }
    pub fn number(self) -> u64 {
        self.number
    }
}
pub struct Leases {
    slots: [(State, u64); 2],
    quarantined: bool,
}
impl Default for Leases {
    fn default() -> Self {
        Self {
            slots: [(State::Free, 0); 2],
            quarantined: false,
        }
    }
}
impl Leases {
    pub fn begin_fill(&mut self, slot: usize) -> Result<Generation, &'static str> {
        if self.quarantined
            || slot >= 2
            || self
                .slots
                .iter()
                .any(|(s, _)| matches!(s, State::Filling | State::Leased | State::Quarantined))
        {
            return Err("not-quiescent");
        }
        let generation = self.slots[slot]
            .1
            .checked_add(1)
            .ok_or("generation-exhausted")?;
        self.slots[slot] = (State::Filling, generation);
        Ok(Generation {
            slot,
            number: generation,
        })
    }
    fn transition(&mut self, g: Generation, from: State, to: State) -> Result<(), &'static str> {
        if self.quarantined || self.slots.get(g.slot) != Some(&(from, g.number)) {
            return Err("stale-generation-or-state");
        }
        self.slots[g.slot].0 = to;
        Ok(())
    }
    pub fn publish(&mut self, g: Generation) -> Result<(), &'static str> {
        self.transition(g, State::Filling, State::Ready)
    }
    pub fn lease(&mut self, g: Generation) -> Result<(), &'static str> {
        if self
            .slots
            .iter()
            .any(|(s, _)| matches!(s, State::Filling | State::Leased))
        {
            return Err("whole-buffer-busy");
        }
        self.transition(g, State::Ready, State::Leased)
    }
    pub fn release(&mut self, g: Generation) -> Result<(), &'static str> {
        self.transition(g, State::Leased, State::Ready)
    }
    pub fn failed_fill(&mut self, g: Generation) -> Result<(), &'static str> {
        self.transition(g, State::Filling, State::Free)
    }
    pub fn quarantine(&mut self) {
        self.quarantined = true;
        for slot in &mut self.slots {
            slot.0 = State::Quarantined;
        }
    }
    pub fn quiescent(&self) -> bool {
        !self.quarantined
            && self
                .slots
                .iter()
                .all(|(s, _)| matches!(s, State::Free | State::Ready))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_stale_publish_or_refill_with_live_consumers() {
        let mut p = Leases::default();
        let a = p.begin_fill(0).unwrap();
        assert!(p.begin_fill(1).is_err());
        p.publish(a).unwrap();
        p.lease(a).unwrap();
        assert!(p.begin_fill(0).is_err());
        assert!(p.begin_fill(1).is_err());
        p.release(a).unwrap();
        let other = p.begin_fill(1).unwrap();
        p.publish(other).unwrap();
        p.lease(a).unwrap();
        assert!(p.lease(other).is_err());
        p.release(a).unwrap();
        let b = p.begin_fill(0).unwrap();
        assert!(p.publish(a).is_err());
        p.failed_fill(b).unwrap();
        assert!(p.lease(b).is_err());
    }
    #[test]
    fn quarantine_is_terminal() {
        let mut p = Leases::default();
        let a = p.begin_fill(0).unwrap();
        p.quarantine();
        assert!(!p.quiescent());
        assert!(p.publish(a).is_err());
        assert!(p.begin_fill(1).is_err());
    }
    #[test]
    fn generation_exhaustion_precedes_mutation() {
        let mut p = Leases::default();
        p.slots[0] = (State::Ready, u64::MAX);
        assert!(p.begin_fill(0).is_err());
        assert_eq!(p.slots[0], (State::Ready, u64::MAX));
    }
}
