//! Deterministic, backend-neutral routing and scalar aggregation contracts.

use std::cmp::Ordering;
use std::collections::BTreeSet;

use crate::error::{ContractError, ErrorCategory};

/// A validated routed-MoE plan in token-major, selected-slot-major order.
///
/// Router scores are not retained. The selected expert IDs and normalized
/// weights use the same flattened `[token][selected_slot]` layout. Unique
/// expert IDs are sorted in ascending order so callers can issue one stable,
/// deduplicated storage request per expert.
#[derive(Debug, Clone, PartialEq)]
pub struct RoutingPlan {
    token_count: u64,
    expert_count: u64,
    top_k: u64,
    selected_expert_ids: Vec<u64>,
    normalized_weights: Vec<f64>,
    unique_expert_ids: Vec<u64>,
}

impl RoutingPlan {
    /// Builds a deterministic top-k plan and applies softmax over only the
    /// selected scores.
    ///
    /// Scores are interpreted as a flattened `[token][expert]` matrix. Higher
    /// scores sort first and exact score ties resolve to the lower expert ID.
    pub fn try_softmax(
        router_scores: &[f64],
        token_count: u64,
        expert_count: u64,
        top_k: u64,
    ) -> Result<Self, ContractError> {
        validate_routing_bounds(token_count, expert_count, top_k)?;

        let score_count = token_count.checked_mul(expert_count).ok_or_else(|| {
            routing_overflow(
                "routing_score_count_overflow",
                "router score shape product exceeds u64",
            )
        })?;
        let actual_score_count = u64::try_from(router_scores.len()).map_err(|_| {
            routing_overflow(
                "routing_score_count_overflow",
                "router score cardinality cannot be represented as u64",
            )
        })?;
        if actual_score_count != score_count {
            return Err(routing_error(
                "routing_score_cardinality_mismatch",
                "router score cardinality does not match token and expert dimensions",
            ));
        }
        if router_scores.iter().any(|score| !score.is_finite()) {
            return Err(routing_error(
                "non_finite_router_score",
                "router scores must all be finite",
            ));
        }

        let token_count = usize::try_from(token_count).map_err(|_| {
            routing_overflow(
                "routing_dimension_overflow",
                "token count cannot be represented on this platform",
            )
        })?;
        let expert_count = usize::try_from(expert_count).map_err(|_| {
            routing_overflow(
                "routing_dimension_overflow",
                "expert count cannot be represented on this platform",
            )
        })?;
        let top_k = usize::try_from(top_k).map_err(|_| {
            routing_overflow(
                "routing_dimension_overflow",
                "top-k cannot be represented on this platform",
            )
        })?;
        let selected_count = token_count.checked_mul(top_k).ok_or_else(|| {
            routing_overflow(
                "routing_selection_count_overflow",
                "selected route shape product exceeds platform bounds",
            )
        })?;

        let mut selected_expert_ids = Vec::with_capacity(selected_count);
        let mut normalized_weights = Vec::with_capacity(selected_count);
        let mut unique_expert_ids = BTreeSet::new();

        for scores in router_scores.chunks_exact(expert_count) {
            let mut expert_ids: Vec<usize> = (0..expert_count).collect();
            expert_ids
                .sort_unstable_by(|&left, &right| descending_score_then_id(scores, left, right));
            expert_ids.truncate(top_k);

            let max_selected_score = scores[expert_ids[0]];
            let mut token_weights = Vec::with_capacity(top_k);
            let mut weight_sum = 0.0_f64;
            for &expert_id in &expert_ids {
                let weight = (scores[expert_id] - max_selected_score).exp();
                weight_sum += weight;
                token_weights.push(weight);
            }
            if !weight_sum.is_finite() || weight_sum <= 0.0 {
                return Err(routing_error(
                    "softmax_normalization_failed",
                    "selected router weights could not be normalized",
                ));
            }

            for (&expert_id, weight) in expert_ids.iter().zip(token_weights) {
                let expert_id = u64::try_from(expert_id).map_err(|_| {
                    routing_overflow(
                        "routing_expert_id_overflow",
                        "selected expert ID cannot be represented as u64",
                    )
                })?;
                selected_expert_ids.push(expert_id);
                normalized_weights.push(weight / weight_sum);
                unique_expert_ids.insert(expert_id);
            }
        }

        Ok(Self {
            token_count: u64::try_from(token_count).expect("validated u64 token count"),
            expert_count: u64::try_from(expert_count).expect("validated u64 expert count"),
            top_k: u64::try_from(top_k).expect("validated u64 top-k"),
            selected_expert_ids,
            normalized_weights,
            unique_expert_ids: unique_expert_ids.into_iter().collect(),
        })
    }

    pub fn token_count(&self) -> u64 {
        self.token_count
    }

    pub fn expert_count(&self) -> u64 {
        self.expert_count
    }

    pub fn top_k(&self) -> u64 {
        self.top_k
    }

    pub fn selected_expert_ids(&self) -> &[u64] {
        &self.selected_expert_ids
    }

    pub fn normalized_weights(&self) -> &[f64] {
        &self.normalized_weights
    }

    /// Returns the ascending, deduplicated expert fetch plan.
    pub fn unique_expert_ids(&self) -> &[u64] {
        &self.unique_expert_ids
    }

    /// Applies the route weights to selected expert outputs using a scalar
    /// token-major accumulation.
    ///
    /// `selected_outputs` uses flattened `[token][selected_slot][output]`
    /// layout. The result uses flattened `[token][output]` layout.
    pub fn aggregate_selected_outputs(
        &self,
        selected_outputs: &[f64],
        output_width: u64,
    ) -> Result<Vec<f64>, ContractError> {
        if output_width == 0 {
            return Err(routing_error(
                "invalid_routed_output_width",
                "routed output width must be greater than zero",
            ));
        }

        let selected_output_count = self
            .token_count
            .checked_mul(self.top_k)
            .and_then(|count| count.checked_mul(output_width))
            .ok_or_else(|| {
                routing_overflow(
                    "routed_output_count_overflow",
                    "selected expert output shape product exceeds u64",
                )
            })?;
        let actual_output_count = u64::try_from(selected_outputs.len()).map_err(|_| {
            routing_overflow(
                "routed_output_count_overflow",
                "selected expert output cardinality cannot be represented as u64",
            )
        })?;
        if actual_output_count != selected_output_count {
            return Err(routing_error(
                "routed_output_cardinality_mismatch",
                "selected expert output cardinality does not match routing dimensions",
            ));
        }
        if selected_outputs.iter().any(|value| !value.is_finite()) {
            return Err(routing_error(
                "non_finite_expert_output",
                "selected expert outputs must all be finite",
            ));
        }

        let output_width = usize::try_from(output_width).map_err(|_| {
            routing_overflow(
                "routed_output_dimension_overflow",
                "routed output width cannot be represented on this platform",
            )
        })?;
        let output_count = usize::try_from(
            self.token_count
                .checked_mul(output_width as u64)
                .ok_or_else(|| {
                    routing_overflow(
                        "routed_output_count_overflow",
                        "aggregated output shape product exceeds u64",
                    )
                })?,
        )
        .map_err(|_| {
            routing_overflow(
                "routed_output_count_overflow",
                "aggregated output cardinality exceeds platform bounds",
            )
        })?;
        let top_k = usize::try_from(self.top_k).expect("validated platform top-k");
        let mut aggregated = vec![0.0_f64; output_count];

        for (token_index, token_output) in aggregated.chunks_exact_mut(output_width).enumerate() {
            let token_weight_offset = token_index * top_k;
            let token_input_offset = token_weight_offset * output_width;
            for selected_slot in 0..top_k {
                let weight = self.normalized_weights[token_weight_offset + selected_slot];
                let selected_offset = token_input_offset + selected_slot * output_width;
                let selected = &selected_outputs[selected_offset..selected_offset + output_width];
                for (destination, &value) in token_output.iter_mut().zip(selected) {
                    *destination += weight * value;
                    if !destination.is_finite() {
                        return Err(routing_error(
                            "non_finite_aggregated_output",
                            "weighted expert accumulation produced a non-finite value",
                        ));
                    }
                }
            }
        }

        Ok(aggregated)
    }
}

fn validate_routing_bounds(
    token_count: u64,
    expert_count: u64,
    top_k: u64,
) -> Result<(), ContractError> {
    if token_count == 0 {
        return Err(routing_error(
            "invalid_token_count",
            "routing token count must be greater than zero",
        ));
    }
    if expert_count == 0 {
        return Err(routing_error(
            "invalid_expert_count",
            "routing expert count must be greater than zero",
        ));
    }
    if top_k == 0 || top_k > expert_count {
        return Err(routing_error(
            "invalid_top_k",
            "routing top-k must be greater than zero and no larger than expert count",
        ));
    }
    Ok(())
}

fn descending_score_then_id(scores: &[f64], left: usize, right: usize) -> Ordering {
    match scores[right]
        .partial_cmp(&scores[left])
        .expect("router scores were validated as finite")
    {
        Ordering::Equal => left.cmp(&right),
        ordering => ordering,
    }
}

fn routing_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, code, message)
}

fn routing_overflow(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::ArithmeticOverflow, code, message)
}
