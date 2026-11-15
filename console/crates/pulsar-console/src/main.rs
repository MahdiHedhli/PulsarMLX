//! `pulsar-console`: the minimal M1 entry point (lead decision LD31). It hands the command
//! line and the scripted engine's factory to [`pulsar_console::run`]; API-17 (M4) replaces
//! it with the full command line and keeps the synthetic-only refusal at process start.
//!
//! This is the only engine the binary can name: no flag, environment variable or
//! configuration key selects another. Built alone (`cargo build --locked -p
//! pulsar-console`), the package does not enable the `test-support` feature of
//! `console-engine`, so the test doubles, among them the engine built to be refused, are
//! not even compiled into it.

fn main() {
    let code = pulsar_console::run(std::env::args_os(), pulsar_console::scripted_factory);
    std::process::exit(code);
}
