//! A bounded, backend-neutral greedy generation seam.
//!
//! This module intentionally accepts only token IDs and a [`LogitsRuntime`]. It
//! has no model, filesystem, device, or adapter identity surface. Callers that
//! want real inference must provide and separately authorize a runtime adapter.

use crate::{
    CancellationToken, ContractError, ErrorCategory, GenerationState, LogitsOutput, LogitsRuntime,
};
use std::collections::BTreeSet;

/// Maximum prompt length admitted by the model-free generation contract.
pub const MAX_PROMPT_TOKENS: usize = 4_096;
/// Maximum number of tokens one generation request may append.
pub const MAX_NEW_TOKENS: u32 = 128;
/// Maximum number of candidate logits a runtime may return for one step.
pub const MAX_TOPK: usize = 4_096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GenerationRequest {
    prompt_token_ids: Vec<u32>,
    max_new_tokens: u32,
    eos_token_id: Option<u32>,
}

impl GenerationRequest {
    /// Construct a request after applying all public bounds.
    pub fn try_new(
        prompt_token_ids: Vec<u32>,
        max_new_tokens: u32,
        eos_token_id: Option<u32>,
    ) -> Result<Self, ContractError> {
        if prompt_token_ids.is_empty() || prompt_token_ids.len() > MAX_PROMPT_TOKENS {
            return Err(contract_error(
                ErrorCategory::ResourceLimit,
                "invalid_prompt_length",
                "prompt token count must be non-zero and within the bounded limit",
            ));
        }
        if max_new_tokens == 0 || max_new_tokens > MAX_NEW_TOKENS {
            return Err(contract_error(
                ErrorCategory::ResourceLimit,
                "invalid_max_new_tokens",
                "max_new_tokens must be non-zero and within the bounded limit",
            ));
        }
        if u64::try_from(prompt_token_ids.len())
            .ok()
            .and_then(|prompt| prompt.checked_add(u64::from(max_new_tokens)))
            .is_none()
        {
            return Err(contract_error(
                ErrorCategory::ArithmeticOverflow,
                "generation_length_overflow",
                "prompt and generation length overflow",
            ));
        }
        Ok(Self {
            prompt_token_ids,
            max_new_tokens,
            eos_token_id,
        })
    }

    pub fn prompt_token_ids(&self) -> &[u32] {
        &self.prompt_token_ids
    }

    pub const fn max_new_tokens(&self) -> u32 {
        self.max_new_tokens
    }

    pub const fn eos_token_id(&self) -> Option<u32> {
        self.eos_token_id
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GenerationStep {
    /// One-based step number within this request.
    step: u32,
    /// Position after the selected token was committed.
    position: u64,
    token_id: u32,
}

impl GenerationStep {
    pub const fn step(&self) -> u32 {
        self.step
    }

    pub const fn position(&self) -> u64 {
        self.position
    }

    pub const fn token_id(&self) -> u32 {
        self.token_id
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TerminationReason {
    EosToken,
    MaxNewTokens,
}

impl TerminationReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::EosToken => "eos_token",
            Self::MaxNewTokens => "max_new_tokens",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GenerationResult {
    prompt_token_ids: Vec<u32>,
    generated_token_ids: Vec<u32>,
    full_token_ids: Vec<u32>,
    steps: Vec<GenerationStep>,
    termination_reason: TerminationReason,
}

impl GenerationResult {
    pub fn prompt_token_ids(&self) -> &[u32] {
        &self.prompt_token_ids
    }

    pub fn generated_token_ids(&self) -> &[u32] {
        &self.generated_token_ids
    }

    pub fn full_token_ids(&self) -> &[u32] {
        &self.full_token_ids
    }

    pub fn steps(&self) -> &[GenerationStep] {
        &self.steps
    }

    pub const fn step_count(&self) -> usize {
        self.steps.len()
    }

    pub const fn termination_reason(&self) -> TerminationReason {
        self.termination_reason
    }
}

/// Run deterministic greedy decoding against a backend-neutral logits runtime.
///
/// The runtime is checked before every step and after every logits call. A
/// runtime may cancel the shared token during its call, which makes cancellation
/// observable before a token is committed.
pub fn generate_greedy<R: LogitsRuntime>(
    runtime: &mut R,
    request: &GenerationRequest,
    cancellation: &CancellationToken,
) -> Result<GenerationResult, ContractError> {
    cancellation.check()?;

    let mut state = GenerationState::default();
    for &token_id in request.prompt_token_ids() {
        state.push_token(token_id)?;
    }

    let mut generated_token_ids = Vec::with_capacity(request.max_new_tokens as usize);
    let mut steps = Vec::with_capacity(request.max_new_tokens as usize);
    for step in 1..=request.max_new_tokens() {
        cancellation.check()?;
        let logits = runtime.logits(cancellation)?;
        cancellation.check()?;
        let token_id = select_greedy_token(&logits)?;
        state.push_token(token_id)?;
        generated_token_ids.push(token_id);
        steps.push(GenerationStep {
            step,
            position: state.position(),
            token_id,
        });

        if request.eos_token_id() == Some(token_id) {
            return Ok(result(
                request,
                generated_token_ids,
                state,
                steps,
                TerminationReason::EosToken,
            ));
        }
    }

    Ok(result(
        request,
        generated_token_ids,
        state,
        steps,
        TerminationReason::MaxNewTokens,
    ))
}

fn result(
    request: &GenerationRequest,
    generated_token_ids: Vec<u32>,
    state: GenerationState,
    steps: Vec<GenerationStep>,
    termination_reason: TerminationReason,
) -> GenerationResult {
    GenerationResult {
        prompt_token_ids: request.prompt_token_ids.clone(),
        generated_token_ids,
        full_token_ids: state.tokens().to_vec(),
        steps,
        termination_reason,
    }
}

fn select_greedy_token(logits: &LogitsOutput) -> Result<u32, ContractError> {
    if logits.topk.is_empty() || logits.topk.len() > MAX_TOPK {
        return Err(contract_error(
            ErrorCategory::InvalidTensor,
            "invalid_logits_candidates",
            "logits candidate list is empty or exceeds the bounded limit",
        ));
    }

    let mut seen = BTreeSet::new();
    let mut selected: Option<(u32, f32)> = None;
    for &(token_id, score) in &logits.topk {
        if !score.is_finite() {
            return Err(contract_error(
                ErrorCategory::InvalidTensor,
                "non_finite_logits",
                "logits candidates must contain finite scores",
            ));
        }
        if !seen.insert(token_id) {
            return Err(contract_error(
                ErrorCategory::InvalidTensor,
                "duplicate_logits_token",
                "logits candidates must contain unique token IDs",
            ));
        }
        if selected.is_none_or(|(best_token, best_score)| {
            score > best_score || (score == best_score && token_id < best_token)
        }) {
            selected = Some((token_id, score));
        }
    }

    let (selected_token, _) = selected.expect("non-empty logits candidate list was checked");
    if logits.argmax != selected_token {
        return Err(contract_error(
            ErrorCategory::InvalidTensor,
            "inconsistent_logits_argmax",
            "runtime argmax does not follow the deterministic greedy tie rule",
        ));
    }
    Ok(selected_token)
}

fn contract_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CancellationToken, LogitsOutput};

    struct TestRuntime {
        outputs: Vec<LogitsOutput>,
        next: usize,
        cancel_after_call: Option<usize>,
    }

    impl LogitsRuntime for TestRuntime {
        fn logits(
            &mut self,
            cancellation: &CancellationToken,
        ) -> Result<LogitsOutput, ContractError> {
            let output = self.outputs.get(self.next).cloned().ok_or_else(|| {
                ContractError::new(
                    ErrorCategory::InvalidStateTransition,
                    "missing_logits_step",
                    "test logits runtime ran out of bounded steps",
                )
            })?;
            self.next += 1;
            if self.cancel_after_call == Some(self.next) {
                cancellation.cancel();
            }
            Ok(output)
        }
    }

    fn output(argmax: u32, topk: &[(u32, f32)]) -> LogitsOutput {
        LogitsOutput {
            topk: topk.to_vec(),
            argmax,
        }
    }

    #[test]
    fn normal_greedy_steps_have_monotonic_positions_and_full_ids() {
        let mut runtime = TestRuntime {
            outputs: vec![output(9, &[(9, 2.0), (8, 1.0)]), output(10, &[(10, 4.0)])],
            next: 0,
            cancel_after_call: None,
        };
        let request = GenerationRequest::try_new(vec![1, 2], 2, None).unwrap();
        let result = generate_greedy(&mut runtime, &request, &CancellationToken::new()).unwrap();
        assert_eq!(result.prompt_token_ids(), [1, 2]);
        assert_eq!(result.generated_token_ids(), [9, 10]);
        assert_eq!(result.full_token_ids(), [1, 2, 9, 10]);
        assert_eq!(result.step_count(), 2);
        assert_eq!(result.steps()[0].position(), 3);
        assert_eq!(result.steps()[1].position(), 4);
        assert_eq!(result.termination_reason(), TerminationReason::MaxNewTokens);
    }

    #[test]
    fn eos_stops_after_committing_the_eos_token() {
        let mut runtime = TestRuntime {
            outputs: vec![output(0, &[(0, 3.0), (8, 2.0)]), output(8, &[(8, 4.0)])],
            next: 0,
            cancel_after_call: None,
        };
        let request = GenerationRequest::try_new(vec![11], 2, Some(0)).unwrap();
        let result = generate_greedy(&mut runtime, &request, &CancellationToken::new()).unwrap();
        assert_eq!(result.generated_token_ids(), [0]);
        assert_eq!(result.step_count(), 1);
        assert_eq!(result.termination_reason(), TerminationReason::EosToken);
        assert_eq!(runtime.next, 1);
    }

    #[test]
    fn ties_choose_the_lowest_token_id_independent_of_candidate_order() {
        let mut runtime = TestRuntime {
            outputs: vec![output(7, &[(8, 1.0), (7, 1.0), (12, 0.5)])],
            next: 0,
            cancel_after_call: None,
        };
        let request = GenerationRequest::try_new(vec![3], 1, None).unwrap();
        let result = generate_greedy(&mut runtime, &request, &CancellationToken::new()).unwrap();
        assert_eq!(result.generated_token_ids(), [7]);
    }

    #[test]
    fn zero_and_over_limit_requests_fail_closed() {
        assert_eq!(
            GenerationRequest::try_new(vec![1], 0, None)
                .unwrap_err()
                .code(),
            "invalid_max_new_tokens"
        );
        assert_eq!(
            GenerationRequest::try_new(vec![1], MAX_NEW_TOKENS + 1, None)
                .unwrap_err()
                .code(),
            "invalid_max_new_tokens"
        );
        assert_eq!(
            GenerationRequest::try_new(Vec::new(), 1, None)
                .unwrap_err()
                .code(),
            "invalid_prompt_length"
        );
        assert_eq!(
            GenerationRequest::try_new(vec![1; MAX_PROMPT_TOKENS + 1], 1, None)
                .unwrap_err()
                .code(),
            "invalid_prompt_length"
        );
    }

    #[test]
    fn malformed_logits_fail_closed_before_token_commit() {
        for (runtime_output, expected_code) in [
            (output(1, &[]), "invalid_logits_candidates"),
            (output(1, &[(1, f32::NAN)]), "non_finite_logits"),
            (output(1, &[(1, 1.0), (1, 0.5)]), "duplicate_logits_token"),
            (output(2, &[(1, 1.0)]), "inconsistent_logits_argmax"),
        ] {
            let mut runtime = TestRuntime {
                outputs: vec![runtime_output],
                next: 0,
                cancel_after_call: None,
            };
            let request = GenerationRequest::try_new(vec![1], 1, None).unwrap();
            let error =
                generate_greedy(&mut runtime, &request, &CancellationToken::new()).unwrap_err();
            assert_eq!(error.code(), expected_code);
        }
    }

    #[test]
    fn cancellation_is_checked_before_and_during_generation() {
        let before = CancellationToken::new();
        before.cancel();
        let mut runtime = TestRuntime {
            outputs: vec![output(1, &[(1, 1.0)])],
            next: 0,
            cancel_after_call: None,
        };
        let request = GenerationRequest::try_new(vec![1], 1, None).unwrap();
        assert_eq!(
            generate_greedy(&mut runtime, &request, &before)
                .unwrap_err()
                .code(),
            "cancelled"
        );
        assert_eq!(runtime.next, 0);

        let cancellation = CancellationToken::new();
        let mut runtime = TestRuntime {
            outputs: vec![output(1, &[(1, 1.0)]), output(2, &[(2, 1.0)])],
            next: 0,
            cancel_after_call: Some(1),
        };
        assert_eq!(
            generate_greedy(&mut runtime, &request, &cancellation)
                .unwrap_err()
                .code(),
            "cancelled"
        );
        assert_eq!(runtime.next, 1);
    }
}
