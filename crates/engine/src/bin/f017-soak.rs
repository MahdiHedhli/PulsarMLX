use engine::f017_soak::run_soak_bounded;
use std::time::Duration;

fn main() {
    let mut iterations = 1_u32;
    let mut duration = None;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--iterations" => {
                iterations = args
                    .next()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or_else(|| fail("--iterations requires a bounded integer"));
            }
            "--duration-seconds" => {
                let seconds: u64 = args
                    .next()
                    .and_then(|value| value.parse().ok())
                    .unwrap_or_else(|| fail("--duration-seconds requires a bounded integer"));
                duration = Some(Duration::from_secs(seconds));
            }
            "--help" | "-h" => {
                println!("usage: f017-soak [--iterations N] [--duration-seconds N]");
                return;
            }
            _ => fail("unknown argument"),
        }
    }
    match run_soak_bounded(iterations, duration) {
        Ok(report) => {
            println!(
                "f017-soak passed: iterations={}/{} elapsed_ms={} boundary={} fingerprint={} rss_baseline={:?} rss_min={:?} rss_max={:?} rss_growth={:?} rss_passed={} logical_allocations={} residency_peak={} registrations={} generations={} teardowns={} cancellations={} failure_injections={}",
                report.completed_iterations,
                report.requested_iterations,
                report.elapsed_millis,
                report.highest_boundary,
                report.deterministic_fingerprint,
                report.rss_baseline_bytes,
                report.rss_min_bytes,
                report.rss_max_bytes,
                report.rss_growth_bytes,
                report.rss_passed,
                report.logical_allocation_events,
                report.residency_peak_entries,
                report.registration_count,
                report.generation_count,
                report.teardown_count,
                report.cancellation_count,
                report.failure_injection_count,
            );
        }
        Err(error) => fail(&error.to_string()),
    }
}

fn fail(message: &str) -> ! {
    eprintln!("f017-soak failed: {message}");
    std::process::exit(2);
}
