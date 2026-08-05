use backend::{BackendCapabilityReport, BackendSelection, CapabilityProbe, DeviceState};

const BACKEND_ID: &str = "apple-mlx";
const DEVICE_ID: &str = "gpu";
const PROBE_CASE_ID: &str = "mlx-device-smoke-v1";

fn explicit_apple_selection() -> BackendSelection {
    BackendSelection::new(BACKEND_ID.to_owned(), Some(DEVICE_ID.to_owned()), false)
        .expect("an explicit Apple MLX GPU selection without fallback is valid")
}

fn available_unevaluated_report() -> BackendCapabilityReport {
    BackendCapabilityReport::available_unevaluated(
        explicit_apple_selection(),
        1,
        "0.32.0".to_owned(),
        "arm64".to_owned(),
        "26.0".to_owned(),
        DEVICE_ID.to_owned(),
        vec!["tensor_probe".to_owned()],
        vec!["float32".to_owned()],
        Vec::new(),
        vec![
            "full-model-inference".to_owned(),
            "custom-metal-kernels".to_owned(),
        ],
    )
    .expect("a discovered device starts available but unevaluated")
}

fn probe(
    backend_id: &str,
    device_id: &str,
    evaluated: bool,
    synchronized: bool,
    comparison_passed: bool,
) -> CapabilityProbe {
    CapabilityProbe::new(
        PROBE_CASE_ID.to_owned(),
        backend_id.to_owned(),
        device_id.to_owned(),
        evaluated,
        synchronized,
        comparison_passed,
    )
    .expect("the probe descriptor has bounded, nonempty identities")
}

#[test]
fn backend_selection_is_explicit_and_preserves_the_requested_device() {
    let selection = explicit_apple_selection();

    assert_eq!(selection.backend_id(), BACKEND_ID);
    assert_eq!(selection.requested_device(), Some(DEVICE_ID));
    assert!(!selection.allow_fallback());
    selection
        .validate_for_evidence()
        .expect("validation evidence forbids fallback");

    assert!(BackendSelection::new(String::new(), Some(DEVICE_ID.to_owned()), false).is_err());
    assert!(BackendSelection::new(BACKEND_ID.to_owned(), None, false).is_err());
    assert!(BackendSelection::new(BACKEND_ID.to_owned(), Some("  ".to_owned()), false,).is_err());
}

#[test]
fn evidence_validation_rejects_fallback_instead_of_silently_substituting_a_backend() {
    let selection = BackendSelection::new(BACKEND_ID.to_owned(), Some(DEVICE_ID.to_owned()), true)
        .expect("selection records the caller's fallback policy before evidence validation");

    assert!(selection.allow_fallback());
    assert!(selection.validate_for_evidence().is_err());

    assert!(BackendCapabilityReport::available_unevaluated(
        selection,
        1,
        "0.32.0".to_owned(),
        "arm64".to_owned(),
        "26.0".to_owned(),
        DEVICE_ID.to_owned(),
        vec!["tensor_probe".to_owned()],
        vec!["float32".to_owned()],
        Vec::new(),
        vec!["cpu-fallback".to_owned()],
    )
    .is_err());
}

#[test]
fn unavailable_report_is_explicit_and_cannot_skip_to_evaluated() {
    let report = BackendCapabilityReport::unavailable(
        explicit_apple_selection(),
        1,
        None,
        "arm64".to_owned(),
        "26.0".to_owned(),
        vec!["mlx-package-not-installed".to_owned()],
    )
    .expect("an unavailable report gives an explicit exclusion");

    assert_eq!(report.schema_version(), 1);
    assert_eq!(report.backend_id(), BACKEND_ID);
    assert_eq!(report.runtime_version(), None);
    assert_eq!(report.host_arch(), "arm64");
    assert_eq!(report.os_version(), "26.0");
    assert_eq!(report.device_id(), None);
    assert_eq!(report.device_state(), DeviceState::Unavailable);
    assert!(report.supported_ops().is_empty());
    assert!(report.supported_dtypes().is_empty());
    assert!(report.supported_quantizations().is_empty());
    assert_eq!(report.exclusions(), ["mlx-package-not-installed"]);
    assert_eq!(report.probe_case_id(), None);

    let passed_probe = probe(BACKEND_ID, DEVICE_ID, true, true, true);
    assert!(report
        .transition_to(DeviceState::Evaluated, Some(&passed_probe))
        .is_err());
    assert_eq!(report.device_state(), DeviceState::Unavailable);
}

#[test]
fn unavailable_report_requires_a_reason_and_all_exclusions_are_nonempty() {
    assert!(BackendCapabilityReport::unavailable(
        explicit_apple_selection(),
        1,
        None,
        "arm64".to_owned(),
        "26.0".to_owned(),
        Vec::new(),
    )
    .is_err());

    assert!(BackendCapabilityReport::unavailable(
        explicit_apple_selection(),
        1,
        None,
        "arm64".to_owned(),
        "26.0".to_owned(),
        vec!["  ".to_owned()],
    )
    .is_err());
}

#[test]
fn discovered_device_remains_available_unevaluated_before_a_probe() {
    let report = available_unevaluated_report();

    assert_eq!(report.backend_id(), BACKEND_ID);
    assert_eq!(report.runtime_version(), Some("0.32.0"));
    assert_eq!(report.device_id(), Some(DEVICE_ID));
    assert_eq!(report.device_state(), DeviceState::AvailableUnevaluated);
    assert_eq!(report.supported_ops(), ["tensor_probe"]);
    assert_eq!(report.supported_dtypes(), ["float32"]);
    assert!(report.supported_quantizations().is_empty());
    assert_eq!(
        report.exclusions(),
        ["full-model-inference", "custom-metal-kernels"]
    );
    assert_eq!(report.probe_case_id(), None);
}

#[test]
fn evaluated_claim_requires_a_present_fully_passed_probe() {
    let report = available_unevaluated_report();

    assert!(report.transition_to(DeviceState::Evaluated, None).is_err());

    for failed_probe in [
        probe(BACKEND_ID, DEVICE_ID, false, true, true),
        probe(BACKEND_ID, DEVICE_ID, true, false, true),
        probe(BACKEND_ID, DEVICE_ID, true, true, false),
    ] {
        assert!(!failed_probe.passed());
        assert!(report
            .transition_to(DeviceState::Evaluated, Some(&failed_probe))
            .is_err());
    }

    assert_eq!(report.device_state(), DeviceState::AvailableUnevaluated);
    assert_eq!(report.probe_case_id(), None);
}

#[test]
fn evaluated_claim_rejects_probe_identity_mismatches() {
    let report = available_unevaluated_report();

    let wrong_backend = probe("linux-cuda", DEVICE_ID, true, true, true);
    assert!(report
        .transition_to(DeviceState::Evaluated, Some(&wrong_backend))
        .is_err());

    let wrong_device = probe(BACKEND_ID, "cpu", true, true, true);
    assert!(report
        .transition_to(DeviceState::Evaluated, Some(&wrong_device))
        .is_err());

    assert_eq!(report.device_state(), DeviceState::AvailableUnevaluated);
}

#[test]
fn passed_probe_creates_a_new_evaluated_report_without_mutating_the_source() {
    let original = available_unevaluated_report();
    let passed_probe = probe(BACKEND_ID, DEVICE_ID, true, true, true);

    assert!(passed_probe.passed());
    assert_eq!(passed_probe.case_id(), PROBE_CASE_ID);

    let evaluated = original
        .transition_to(DeviceState::Evaluated, Some(&passed_probe))
        .expect("a matching evaluated, synchronized, numerically passing probe is sufficient");

    assert_eq!(original.device_state(), DeviceState::AvailableUnevaluated);
    assert_eq!(original.probe_case_id(), None);

    assert_eq!(evaluated.device_state(), DeviceState::Evaluated);
    assert_eq!(evaluated.probe_case_id(), Some(PROBE_CASE_ID));
    assert_eq!(evaluated.backend_id(), original.backend_id());
    assert_eq!(evaluated.device_id(), original.device_id());
    assert_eq!(evaluated.supported_ops(), original.supported_ops());
    assert_eq!(evaluated.supported_dtypes(), original.supported_dtypes());
    assert_eq!(evaluated.exclusions(), original.exclusions());
}

#[test]
fn capability_state_transitions_cannot_repeat_or_move_backwards() {
    let available = available_unevaluated_report();
    let passed_probe = probe(BACKEND_ID, DEVICE_ID, true, true, true);
    let evaluated = available
        .transition_to(DeviceState::Evaluated, Some(&passed_probe))
        .expect("first legal transition succeeds");

    assert!(available
        .transition_to(DeviceState::AvailableUnevaluated, None)
        .is_err());
    assert!(available
        .transition_to(DeviceState::Unavailable, None)
        .is_err());
    assert!(evaluated
        .transition_to(DeviceState::Evaluated, Some(&passed_probe))
        .is_err());
    assert!(evaluated
        .transition_to(DeviceState::AvailableUnevaluated, None)
        .is_err());
    assert!(evaluated
        .transition_to(DeviceState::Unavailable, None)
        .is_err());
}
