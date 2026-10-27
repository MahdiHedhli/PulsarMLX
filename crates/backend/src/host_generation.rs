//! Bounded serial generation over the real host coordinator, without another
//! generated-token state or commit path. Pending delivery must be resolved first.
use crate::step::{
    CommittedStep, HostLayerExecutor, HostTensorStore, StepCoordinator, StepFailure, StepOutcome,
    StepRequest,
};
use crate::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, GenerationState,
    MemoryBudget, TensorCatalog,
};

pub const MAX_HOST_GENERATED_TOKENS: u32 = 8;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HostStop {
    Eos,
    MaxTokens,
}

pub struct HostGeneration<B> {
    coordinator: StepCoordinator<B>,
    maximum: u32,
    eos: Option<u32>,
    pending_delivery: bool,
}

impl<B: HostLayerExecutor> HostGeneration<B> {
    pub fn new(
        checkpoint: CheckpointIdentity,
        memory: MemoryBudget,
        backend: B,
        seed: u32,
        vocabulary: u32,
        maximum: u32,
        eos: Option<u32>,
    ) -> Result<Self, ContractError> {
        if vocabulary == 0
            || seed >= vocabulary
            || eos.is_some_and(|t| t >= vocabulary)
            || maximum == 0
            || maximum > MAX_HOST_GENERATED_TOKENS
        {
            return Err(driver_error("invalid_host_generation"));
        }
        let mut state = GenerationState::default();
        // The only push outside StepCoordinator: seed history before ownership.
        state.push_token(seed)?;
        Ok(Self {
            coordinator: StepCoordinator::new(checkpoint, memory, state, backend)?,
            maximum,
            eos,
            pending_delivery: false,
        })
    }

    pub fn coordinator(&self) -> &StepCoordinator<B> {
        &self.coordinator
    }
    pub fn generated_tokens(&self) -> &[u32] {
        &self.coordinator.state().tokens()[1..]
    }
    pub fn pending_request(&self) -> Option<&StepRequest> {
        if self.pending_delivery {
            self.coordinator.retained_request()
        } else {
            None
        }
    }
    pub fn stop(&self) -> Option<HostStop> {
        if self.pending_delivery {
            return None;
        }
        let tokens = self.generated_tokens();
        if tokens.last().is_some_and(|token| Some(*token) == self.eos) {
            Some(HostStop::Eos)
        } else if tokens.len() >= self.maximum as usize {
            Some(HostStop::MaxTokens)
        } else {
            None
        }
    }
    pub fn next_input_token(&self) -> Result<u32, ContractError> {
        if self.pending_delivery {
            return Err(driver_error("host_delivery_pending"));
        }
        if self.stop().is_some() {
            return Err(driver_error("host_generation_stopped"));
        }
        self.coordinator
            .state()
            .tokens()
            .last()
            .copied()
            .ok_or_else(|| driver_error("missing_host_seed"))
    }
    /// The backend must itself enforce its vocabulary/output contract before
    /// returning a proposal. Errors here never roll back a committed prefix.
    pub fn advance<
        C: TensorCatalog,
        S: HostTensorStore,
        D: FnMut(&CommittedStep) -> Result<(), ContractError>,
    >(
        &mut self,
        request: &StepRequest,
        catalog: &C,
        store: &S,
        cancellation: &CancellationToken,
        deliver: D,
    ) -> Result<StepOutcome, StepFailure> {
        if self.pending_delivery {
            if self.coordinator.retained_request() != Some(request) {
                return Err(driver_error("host_delivery_pending").into());
            }
        } else if self.stop().is_some() {
            return Err(driver_error("host_generation_stopped").into());
        }
        let result = self
            .coordinator
            .execute(request, catalog, store, cancellation, deliver)?;
        // No fallible work or second push after the coordinator's commit.
        self.pending_delivery = result.delivery_error.is_some();
        Ok(result)
    }
}

fn driver_error(code: &'static str) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidStateTransition,
        code,
        "host generation refused",
    )
}
