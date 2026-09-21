//! Bounded, checkpoint-free Feature 017 semantic-path soak execution.

use crate::f017_parity::{
    run_complete_layer_fixture, run_expert_fixture, run_final_output_fixture,
    run_mla_dense_fixture, run_projection_fixture, run_router_fixture, run_top8_shared_fixture,
    CompleteLayerFixture, ExpertFixture, FinalOutputFixture, MlaDenseFixture, ProjectionDispatch,
    ProjectionFixture, RouterFixture, Top8SharedFixture,
};
use sha2::{Digest, Sha256};
use std::fmt;
use std::time::{Duration, Instant};
use stream::{
    AppleBridgeEvent, AppleBridgeGeneration, AppleBridgeLifecycle, ExpertAdmissionError,
    ExpertAdmissionPolicy, ExpertAdmissionRequest, ExpertKey, ExpertKind, ExpertLifecycle,
    ExpertResidencyTable, ExpertResidencyTier, SlotId,
};

const MAX_SOAK_ITERATIONS: u32 = 100_000;
const MAX_SOAK_SECONDS: u64 = 3_600;
const RSS_GROWTH_LIMIT_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SoakReport {
    pub requested_iterations: u32,
    pub completed_iterations: u32,
    pub elapsed_millis: u128,
    pub highest_boundary: &'static str,
    pub deterministic_fingerprint: String,
    pub rss_baseline_bytes: Option<u64>,
    pub rss_min_bytes: Option<u64>,
    pub rss_max_bytes: Option<u64>,
    pub rss_growth_bytes: Option<u64>,
    pub rss_passed: bool,
    pub logical_allocation_events: u64,
    pub residency_peak_entries: u32,
    pub registration_count: u64,
    pub generation_count: u64,
    pub teardown_count: u64,
    pub cancellation_count: u64,
    pub failure_injection_count: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SoakError {
    InvalidBound(String),
    BoundaryFailure {
        iteration: u32,
        boundary: &'static str,
        error: String,
    },
    Nondeterministic {
        iteration: u32,
        boundary: &'static str,
        expected: String,
        actual: String,
    },
    MemoryGrowth {
        iteration: u32,
        baseline: u64,
        current: u64,
    },
    Lifecycle(String),
    Residency(String),
}

impl fmt::Display for SoakError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidBound(error) => write!(formatter, "invalid soak bound: {error}"),
            Self::BoundaryFailure {
                iteration,
                boundary,
                error,
            } => write!(formatter, "iteration {iteration} failed at {boundary}: {error}"),
            Self::Nondeterministic {
                iteration,
                boundary,
                expected,
                actual,
            } => write!(
                formatter,
                "iteration {iteration} nondeterministic at {boundary}: expected {expected}, actual {actual}"
            ),
            Self::MemoryGrowth {
                iteration,
                baseline,
                current,
            } => write!(
                formatter,
                "iteration {iteration} exceeded RSS growth limit: baseline {baseline}, current {current}"
            ),
            Self::Lifecycle(error) => write!(formatter, "lifecycle failure injection failed: {error}"),
            Self::Residency(error) => write!(formatter, "residency churn failed: {error}"),
        }
    }
}

impl std::error::Error for SoakError {}

pub fn run_soak(iterations: u32) -> Result<SoakReport, SoakError> {
    run_soak_bounded(iterations, None)
}

pub fn run_soak_bounded(
    iterations: u32,
    duration: Option<Duration>,
) -> Result<SoakReport, SoakError> {
    if iterations == 0 || iterations > MAX_SOAK_ITERATIONS {
        return Err(SoakError::InvalidBound(format!(
            "iterations must be in 1..={MAX_SOAK_ITERATIONS}"
        )));
    }
    if duration.is_some_and(|value| value.is_zero() || value.as_secs() > MAX_SOAK_SECONDS) {
        return Err(SoakError::InvalidBound(format!(
            "duration must be non-zero and <= {MAX_SOAK_SECONDS} seconds"
        )));
    }
    let started = Instant::now();
    let deadline = duration.map(|value| started + value);
    let baseline_rss = current_rss_bytes();
    let mut min_rss = baseline_rss;
    let mut max_rss = baseline_rss;
    let mut expected_fingerprint: Option<String> = None;
    let mut completed_iterations = 0_u32;
    let mut logical_allocation_events = 0_u64;
    let mut residency_peak_entries = 0_u32;
    let mut registration_count = 0_u64;
    let mut generation_count = 0_u64;
    let mut teardown_count = 0_u64;
    let mut cancellation_count = 0_u64;
    let mut failure_injection_count = 0_u64;

    for iteration in 0..iterations {
        if completed_iterations > 0 && deadline.is_some_and(|value| Instant::now() >= value) {
            break;
        }
        let fingerprint = run_semantic_iteration(iteration)?;
        if let Some(expected) = expected_fingerprint.as_ref() {
            if expected != &fingerprint {
                return Err(SoakError::Nondeterministic {
                    iteration,
                    boundary: "semantic-path",
                    expected: expected.clone(),
                    actual: fingerprint,
                });
            }
        } else {
            expected_fingerprint = Some(fingerprint);
        }
        let churn = exercise_residency_and_lifecycle(iteration)?;
        residency_peak_entries = residency_peak_entries.max(churn.residency_entries);
        registration_count += churn.registrations;
        generation_count += churn.generations;
        teardown_count += churn.teardowns;
        cancellation_count += churn.cancellations;
        failure_injection_count += churn.failure_injections;
        logical_allocation_events += 7;
        completed_iterations += 1;

        if let Some(rss) = current_rss_bytes() {
            min_rss = Some(min_rss.map_or(rss, |value| value.min(rss)));
            max_rss = Some(max_rss.map_or(rss, |value| value.max(rss)));
            if let Some(baseline) = baseline_rss {
                if rss.saturating_sub(baseline) > RSS_GROWTH_LIMIT_BYTES {
                    return Err(SoakError::MemoryGrowth {
                        iteration,
                        baseline,
                        current: rss,
                    });
                }
            }
        }
    }

    let rss_growth = match (baseline_rss, max_rss) {
        (Some(baseline), Some(maximum)) => Some(maximum.saturating_sub(baseline)),
        _ => None,
    };
    Ok(SoakReport {
        requested_iterations: iterations,
        completed_iterations,
        elapsed_millis: started.elapsed().as_millis(),
        highest_boundary: "final-norm-logits-top-k",
        deterministic_fingerprint: expected_fingerprint.unwrap_or_default(),
        rss_baseline_bytes: baseline_rss,
        rss_min_bytes: min_rss,
        rss_max_bytes: max_rss,
        rss_growth_bytes: rss_growth,
        rss_passed: rss_growth.is_none_or(|value| value <= RSS_GROWTH_LIMIT_BYTES),
        logical_allocation_events,
        residency_peak_entries,
        registration_count,
        generation_count,
        teardown_count,
        cancellation_count,
        failure_injection_count,
    })
}

fn run_semantic_iteration(iteration: u32) -> Result<String, SoakError> {
    let dispatch = ProjectionDispatch::ExplicitReference;
    let projection = run_projection_fixture(&ProjectionFixture::synthetic_q8_0(), dispatch)
        .map_err(|error| boundary_error(iteration, "projection", error))?;
    let router = run_router_fixture(&RouterFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "router", error))?;
    let expert = run_expert_fixture(&ExpertFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "complete-expert", error))?;
    let top8 = run_top8_shared_fixture(&Top8SharedFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "top8-shared", error))?;
    let mla = run_mla_dense_fixture(&MlaDenseFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "mla-dense", error))?;
    let layer = run_complete_layer_fixture(&CompleteLayerFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "complete-layer", error))?;
    let final_output = run_final_output_fixture(&FinalOutputFixture::synthetic(), dispatch)
        .map_err(|error| boundary_error(iteration, "final-norm-logits-top-k", error))?;
    let material = format!(
        "{:?}|{:?}|{:?}|{:?}|{:?}|{:?}|{:?}",
        (
            projection.classification,
            projection.reference_output_sha256,
            projection.dispatch
        ),
        (
            router.classification,
            router.selected_ids_sha256,
            router.weights_sha256,
            router.output_sha256,
            router.dispatch
        ),
        (expert.classification, expert.output_sha256, expert.dispatch),
        (top8.classification, top8.output_sha256, top8.dispatch),
        (mla.classification, mla.output_sha256, mla.dispatch),
        (layer.classification, layer.output_sha256, layer.dispatch),
        (
            final_output.classification,
            final_output.norm_sha256,
            final_output.logits_sha256,
            final_output.topk_sha256,
            final_output.argmax,
            final_output.dispatch
        )
    );
    Ok(format!("{:x}", Sha256::digest(material.as_bytes())))
}

fn boundary_error<T: fmt::Display>(iteration: u32, boundary: &'static str, error: T) -> SoakError {
    SoakError::BoundaryFailure {
        iteration,
        boundary,
        error: error.to_string(),
    }
}

struct ChurnReport {
    residency_entries: u32,
    registrations: u64,
    generations: u64,
    teardowns: u64,
    cancellations: u64,
    failure_injections: u64,
}

fn exercise_residency_and_lifecycle(iteration: u32) -> Result<ChurnReport, SoakError> {
    let policy = ExpertAdmissionPolicy::new(4096, 8, true, true)
        .ok_or_else(|| SoakError::Residency("invalid policy".to_owned()))?;
    let mut table = ExpertResidencyTable::new(policy);
    let base = u64::from(iteration)
        .checked_mul(10)
        .ok_or_else(|| SoakError::Residency("slot generation overflow".to_owned()))?;
    let routed = ExpertKey {
        layer: 0,
        expert: 1,
        kind: ExpertKind::Routed,
    };
    let hot = ExpertKey {
        layer: 0,
        expert: 2,
        kind: ExpertKind::Routed,
    };
    let shared = ExpertKey {
        layer: 0,
        expert: 0,
        kind: ExpertKind::Shared,
    };
    let transient = ExpertKey {
        layer: 0,
        expert: 3,
        kind: ExpertKind::Routed,
    };
    table
        .admit(request(
            routed,
            ExpertResidencyTier::CompressedResident,
            base + 1,
            false,
        ))
        .map_err(|error| SoakError::Residency(format!("compressed: {error:?}")))?;
    table
        .admit(request(
            hot,
            ExpertResidencyTier::DecodedHot,
            base + 2,
            false,
        ))
        .map_err(|error| SoakError::Residency(format!("decoded: {error:?}")))?;
    table
        .admit(request(
            shared,
            ExpertResidencyTier::NativeReadyHot,
            base + 3,
            true,
        ))
        .map_err(|error| SoakError::Residency(format!("shared: {error:?}")))?;
    table
        .admit(request(
            transient,
            ExpertResidencyTier::Transient,
            base + 4,
            false,
        ))
        .map_err(|error| SoakError::Residency(format!("transient: {error:?}")))?;
    table
        .transition(transient, ExpertLifecycle::Leased)
        .and_then(|_| table.transition(transient, ExpertLifecycle::Available))
        .map_err(|error| SoakError::Residency(format!("transient lifecycle: {error:?}")))?;
    table
        .evict(transient)
        .map_err(|error| SoakError::Residency(format!("transient eviction: {error:?}")))?;
    if table.evict(shared) != Err(ExpertAdmissionError::Protected) {
        return Err(SoakError::Residency(
            "protected shared expert became evictable".to_owned(),
        ));
    }
    let mut normal = AppleBridgeLifecycle::new(AppleBridgeGeneration { value: base + 1 });
    apply_lifecycle(&mut normal, AppleBridgeEvent::Register, base + 1)?;
    apply_lifecycle(&mut normal, AppleBridgeEvent::Submit, base + 1)?;
    apply_lifecycle(&mut normal, AppleBridgeEvent::Complete, base + 1)?;
    apply_lifecycle(&mut normal, AppleBridgeEvent::Release, base + 1)?;
    apply_lifecycle(&mut normal, AppleBridgeEvent::Destroy, base + 1)?;
    let mut cancelled = AppleBridgeLifecycle::new(AppleBridgeGeneration { value: base + 2 });
    apply_lifecycle(&mut cancelled, AppleBridgeEvent::Register, base + 2)?;
    apply_lifecycle(
        &mut cancelled,
        AppleBridgeEvent::CancelBeforeSubmit,
        base + 2,
    )?;
    apply_lifecycle(&mut cancelled, AppleBridgeEvent::Release, base + 2)?;
    apply_lifecycle(&mut cancelled, AppleBridgeEvent::Destroy, base + 2)?;
    if normal.state() != stream::AppleBridgeState::Destroyed
        || cancelled.state() != stream::AppleBridgeState::Destroyed
    {
        return Err(SoakError::Lifecycle(
            "lifecycle did not reach destroyed".to_owned(),
        ));
    }
    if cancelled
        .apply(
            AppleBridgeEvent::Register,
            AppleBridgeGeneration { value: base + 1 },
        )
        .is_ok()
    {
        return Err(SoakError::Lifecycle(
            "stale generation was accepted".to_owned(),
        ));
    }
    Ok(ChurnReport {
        residency_entries: table.len() as u32,
        registrations: 2,
        generations: 2,
        teardowns: 2,
        cancellations: 1,
        failure_injections: 2,
    })
}

fn request(
    key: ExpertKey,
    tier: ExpertResidencyTier,
    slot_id: u64,
    protected: bool,
) -> ExpertAdmissionRequest {
    ExpertAdmissionRequest {
        key,
        tier,
        bytes: 64,
        slot_id: SlotId(slot_id),
        protected,
    }
}

fn apply_lifecycle(
    lifecycle: &mut AppleBridgeLifecycle,
    event: AppleBridgeEvent,
    generation: u64,
) -> Result<(), SoakError> {
    lifecycle
        .apply(event, AppleBridgeGeneration { value: generation })
        .map(|_| ())
        .map_err(|error| SoakError::Lifecycle(format!("{error:?}")))
}

#[cfg(target_os = "macos")]
fn current_rss_bytes() -> Option<u64> {
    let mut info = unsafe { std::mem::zeroed::<libc::mach_task_basic_info>() };
    let mut count = (std::mem::size_of::<libc::mach_task_basic_info>()
        / std::mem::size_of::<libc::natural_t>())
        as libc::mach_msg_type_number_t;
    let result = unsafe {
        libc::task_info(
            libc::mach_task_self_,
            libc::MACH_TASK_BASIC_INFO,
            (&mut info as *mut libc::mach_task_basic_info).cast::<libc::integer_t>(),
            &mut count,
        )
    };
    (result == libc::KERN_SUCCESS).then_some(info.resident_size as u64)
}

#[cfg(not(target_os = "macos"))]
fn current_rss_bytes() -> Option<u64> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_soak_is_deterministic_and_reaches_final_boundary() {
        let report = run_soak(2).expect("short soak");
        assert_eq!(report.completed_iterations, 2);
        assert_eq!(report.highest_boundary, "final-norm-logits-top-k");
        assert_eq!(report.residency_peak_entries, 3);
        assert_eq!(report.registration_count, 4);
        assert_eq!(report.generation_count, 4);
        assert_eq!(report.teardown_count, 4);
        assert_eq!(report.cancellation_count, 2);
        assert!(report.rss_passed);
    }

    #[test]
    fn soak_bounds_are_fail_closed() {
        assert!(matches!(run_soak(0), Err(SoakError::InvalidBound(_))));
        assert!(matches!(
            run_soak_bounded(1, Some(Duration::ZERO)),
            Err(SoakError::InvalidBound(_))
        ));
    }
}
