use packed_affine_adoption::*;
#[test]
fn registration_uses_runtime_pages_and_complete_two_slot_capacity() {
    assert_eq!(registration(4194304, 16384, 1 << 30).unwrap(), 8388608);
    assert_eq!(registration(4096, 16384, 1 << 30).unwrap(), 16384);
    assert!(registration(usize::MAX - 3, 16384, usize::MAX).is_err());
    assert!(registration(4, 3, usize::MAX).is_err());
    assert!(registration(4194304, 16384, 8388607).is_err());
}
#[test]
fn independent_adoption_detectors_trip_exact_gate() {
    assert_eq!(adopted(false, false, true), Err("copied-fallback"));
    assert_eq!(adopted(true, true, true), Err("early-callback"));
    assert_eq!(adopted(true, false, false), Err("native-error"));
    assert!(adopted(true, false, true).is_ok());
}
#[test]
fn retirement_requires_actual_ack_and_balanced_handles() {
    assert!(require_retired(1, 0, 0, 0, false).is_err());
    assert!(require_retired(1, 2, 0, 0, false).is_err());
    assert!(require_retired(1, 1, 1, 0, false).is_err());
    assert!(require_retired(1, 1, 0, 1, false).is_err());
    assert!(require_retired(1, 1, 0, 0, true).is_err());
    assert!(require_retired(1, 1, 0, 0, false).is_ok());
}
