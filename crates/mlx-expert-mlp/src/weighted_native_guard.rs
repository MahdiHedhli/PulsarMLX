//! Synchronous delegation and CPU arithmetic observations around the existing copied Driver.
use mlx_expert_mlp::resident_pipeline::*;
use mlx_native_affine::{fixture::HostTensor, refusal::DeviceFacts};
use std::{
    cell::RefCell,
    rc::Rc,
    thread::{self, ThreadId},
};

pub struct Guard<P> {
    owner: ThreadId,
    initial: u64,
    probe: P,
    pub words: Vec<(&'static str, u64)>,
}
impl<P: FnMut() -> StageResult<u64>> Guard<P> {
    pub fn new(mut probe: P) -> StageResult<Self> {
        let initial = probe()?;
        let mut words = Vec::with_capacity(23);
        words.push(("initial", initial));
        Ok(Self {
            owner: thread::current().id(),
            initial,
            probe,
            words,
        })
    }
    pub fn owner(&self) -> StageResult<()> {
        if self.owner != thread::current().id() {
            return Err(Fault::uncertain("native owner thread"));
        }
        Ok(())
    }
    pub fn check(&mut self, phase: &'static str) -> StageResult<()> {
        self.owner()?;
        if self.words.len() >= 23 {
            return Err(Fault::uncertain("guard record capacity"));
        }
        let value = (self.probe)()?;
        self.words.push((phase, value));
        if value != self.initial {
            return Err(Fault::uncertain("CPU arithmetic state changed"));
        }
        Ok(())
    }
}
pub struct Guarded<D, P> {
    pub copied: D,
    pub state: Rc<RefCell<Guard<P>>>,
}
impl<D: Driver, P: FnMut() -> StageResult<u64>> Driver for Guarded<D, P> {
    fn begin(&mut self) -> StageResult<DeviceFacts> {
        self.state.borrow().owner()?;
        self.copied.begin()
    }
    fn projection(
        &mut self,
        role: usize,
        input: &HostTensor,
        parts: &[HostTensor; 3],
        bits: u32,
    ) -> StageResult<Projection> {
        self.state.borrow().owner()?;
        self.copied.projection(role, input, parts, bits)
    }
    fn activation(&mut self, g: &HostTensor, u: &HostTensor) -> StageResult<Activation> {
        self.state.borrow().owner()?;
        self.copied.activation(g, u)
    }
    fn retire(&mut self) -> StageResult<Retirement> {
        self.state.borrow().owner()?;
        let retired = self.copied.retire()?;
        self.state.borrow_mut().check("retired")?;
        Ok(retired)
    }
    fn finish(&mut self) -> StageResult<()> {
        self.state.borrow().owner()?;
        self.copied.finish()?;
        self.state.borrow_mut().check("finish")
    }
}
