//! CARGO_BUILD_JOBS=2 cargo run --locked --offline -p backend --example routed_host_lifecycle
//! Generated resident CPU fixtures only. This does not exercise expert paging.
use backend::host_generation::{HostGeneration, HostStop};
use backend::routed_cpu::{
    advance_fixture, fixture_identity, RoutedTrace, TinyFixture, TinyMoeCpuBackend, FIXTURE_WEIGHTS,
};
use backend::{CancellationToken, ContractError, ErrorCategory, MemoryBudget};
#[path = "../tests/support/routed_goldens.rs"]
mod reference;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    for (case, seed, eos, expected_stop) in [
        ("max", 0, None, HostStop::MaxTokens),
        ("eos", 5, Some(7), HostStop::Eos),
    ] {
        let fixture = TinyFixture::new(FIXTURE_WEIGHTS)?;
        let mut driver = HostGeneration::new(
            fixture_identity(),
            MemoryBudget::try_new(200_000, 10_000, 100_000)?,
            TinyMoeCpuBackend::default(),
            seed,
            8,
            8,
            eos,
        )?;
        let mut delivery_fault = case == "max";
        while driver.stop()?.is_none() {
            let outcome =
                advance_fixture(&mut driver, &fixture, &CancellationToken::new(), |_| {
                    if delivery_fault {
                        delivery_fault = false;
                        Err(ContractError::new(
                            ErrorCategory::InvalidStateTransition,
                            "delivery_offline",
                            "simulated transport failure",
                        ))
                    } else {
                        Ok(())
                    }
                })?;
            reference::compare(case, &outcome.committed)?;
            let trace = RoutedTrace::decode(&outcome.committed.bytes)?;
            println!("reference=PASS case={case} input={} routes={:?}/{:?} token={} position={} COMMITTED",trace.input_token,trace.layers[0].selected,trace.layers[1].selected,outcome.committed.token,outcome.committed.position);
            if outcome.delivery_error.is_some() {
                let stats = driver.coordinator().backend().stats();
                let reads = fixture.reads();
                let cancel = CancellationToken::new();
                cancel.cancel();
                let retry = advance_fixture(&mut driver, &fixture, &cancel, |_| Ok(()))?;
                assert!(retry.replayed);
                assert!(std::sync::Arc::ptr_eq(&retry.committed, &outcome.committed));
                assert_eq!(fixture.reads(), reads);
                assert_eq!(driver.coordinator().backend().stats(), stats);
                println!("delivery_retry=PASS cancelled=true extra_reads=0 extra_routes=0 extra_experts=0 extra_commits=0");
            }
            assert_eq!(driver.coordinator().active_reservations(), 0);
            assert!(!driver.coordinator().backend().has_staged_resources());
        }
        assert_eq!(driver.stop()?, Some(expected_stop));
        println!(
            "case={case} stop={expected_stop:?} tokens={:?} reads={} stats={:?}",
            driver.generated_tokens(),
            fixture.reads(),
            driver.coordinator().backend().stats()
        );
    }
    Ok(())
}
