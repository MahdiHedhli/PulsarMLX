# PulsarMLX Baseline Validation

Validation was performed on the inspected Apple Silicon macOS environment before beginning MLX backend implementation. The results below are the actual results from this session; expected outcomes are identified separately and are not presented as observed facts.

## Compatibility gate inspected

`crates/serve/src/main.rs` contains `handle_chat`, whose signature and implementation reference server-side types that are available only in the Linux build path, including `engine::Model`, `engine::State`, `engine::Result`, and `mcp::McpHub`.

At inspection, preserved commit `12c2406` had already guarded the function
immediately above its existing declaration:

```rust
#[cfg(target_os = "linux")]
fn handle_chat(
```

Only the target gate was required for this baseline. The function signature and body were not changed, and the attribute preserves the existing Linux behavior while preventing macOS from compiling this Linux-only path.

## Required workspace check

Command:

```console
cargo check --workspace --all-targets
```

Actual result: **passed** (exit status 0).

The check emitted an existing `unused_mut` warning from `crates/quant/src/iq.rs` and 13 dead-code warnings from the macOS build of `crates/serve`. No warning was represented as a failure, and no broad warning cleanup was performed.

## Required workspace tests

Command:

```console
cargo test --workspace --no-fail-fast
```

Actual result: **passed** (exit status 0). A total of 32 tests ran: 32 passed and 0 failed.

The anticipated Apple arm64 baseline was approximately 32 tests with a passing workspace run, subject to the upstream revision. The actual run matched that expectation. The count remains an observed property of this revision, not a permanent test-count guarantee.

### macOS coverage gaps

The test command is green, but target gating means it does not exercise every inherited runtime path. On this macOS run, the engine, kernels, and Linux-gated server test targets each executed zero tests. In particular, the successful result does not establish coverage of the Linux server path, CUDA execution, or the `handle_chat` implementation itself on macOS. These are observed baseline coverage limitations, not failures introduced by the compatibility gate.

## Formatting inspection

Command:

```console
cargo fmt --all -- --check
```

Actual result: **failed** (exit status 1). Rustfmt reported differences in 25 pre-existing upstream Rust files. This was a check-only invocation; it made no edits. Repository-wide formatting was not performed because the differences are broad upstream debt and do not directly block the Apple Silicon baseline.

## Clippy inspection

Command:

```console
cargo clippy --workspace --all-targets -- -D warnings
```

Actual result: **failed** (exit status 101). With warnings promoted to errors, the run stopped at `crates/kernels/build.rs:41` on `clippy::needless_borrows_for_generic_args`.

This strict Clippy failure is existing upstream build-script debt. It was inspected but not broadly fixed, and strict repository-wide Clippy should not yet be introduced as a baseline CI gate.

## Baseline conclusion

The required workspace build check and test suite both pass on the inspected Apple Silicon macOS machine. The Linux target gate around `handle_chat` establishes the narrow known macOS source-level compatibility fix without altering Linux behavior. Formatting and strict Clippy remain non-blocking upstream debt, and the zero-test macOS paths above must not be mistaken for validated engine, kernel, or server behavior. No MLX inference capability was exercised or established by these commands.
