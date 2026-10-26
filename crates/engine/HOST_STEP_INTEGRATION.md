# Bounded host-step package integration

`tests/host_step_package.rs` imports the real `stream::Read`, positional source,
owned slab and stable allocator exports. Its synthetic bytes pass through the
existing backend contracts into the same coordinator type exposed by
`engine::host_step`. It also exercises the public row-cap and capacity refusals.
The fixture contains no native API calls. This target supplements the isolated
storage harness; it does not replace native backend qualification.

The compile/link boundary on macOS matters even for a CPU fixture. `stream`'s
existing build script compiles Objective-C++ bridges and links Foundation/Metal.
When the default local MLX headers/libraries exist, it also selects
`pulsar_native_mlx` and links MLX. Do not execute those linked artifacts under
the bounded host-only qualification, including test listing or filtered tests.

For the inspected `aarch64-apple-darwin` configuration, use a separate target
directory and at most two Cargo jobs. Package defaults are unchanged; no cfg,
prefix or feature override is needed:

```sh
cargo check --locked --offline -p backend -p stream -p engine --all-targets
cargo test --locked --offline -p backend -p stream -p engine --all-targets --no-run
cargo check --locked --offline -p backend -p stream -p engine --all-targets --release
cargo test --locked --offline -p backend -p stream -p engine --all-targets --no-run --release
```

`check` proves types, while `test --no-run` additionally compiles and links the
actual libraries, binaries, tests and examples selected by Cargo. Inspect the
current build scripts, transitive hooks and installed inputs before using this
boundary on another host. Missing cached or native inputs must be reported,
without installing replacements, forcing cfg or using fake libraries.

`scripts/check-rust-host.sh` remains eligible for serial CPU regression checks:
its standalone harness includes the production storage source modules with an
equivalent local `Read` definition. It has no native dependencies, but does not
establish real `stream` exports or linkage. Backend tests and the existing
`host_lifecycle` example likewise have no native dependencies. Use one test
process/thread at a time. Reuse unchanged source-bound receipts where possible.

The storage docs distinguish initialization from confidentiality: retaining
policies can expose earlier initialized lease bytes, and clearing a logical
surface is not secure erasure. Telemetry records request attempts before later
refusals; only overflow of the request counters leaves both attempts unchanged.
Existing counter tests now assert this ordering explicitly.

The added public `SourceError` and `SlabAllocatorError` variants are additive API
changes that can break downstream exhaustive matches. Actual macOS consumers
must compile against them; source inspection or an equivalent harness type is
insufficient. No blanket catch-all or `non_exhaustive` conversion is needed for
the selected consumers. Linux/CUDA consumers and other targets/configurations
require their own checks. Compile/link acceptance does not establish native
execution, numerical behavior, backend attachment or production readiness.

The Rust003 checkpoint checked rustc/cargo 1.95.0, Apple clang 21.0.0, macOS SDK
27.0, installed mlx-c 0.6.0_2 and mlx 0.31.2, using package defaults and naturally
selected `pulsar_native_mlx`. All 24 selected package targets passed type-check
and compile/link in debug and release (29 linked executables per profile).
Static Mach-O inspection confirmed native linkage; none of those native-linked
artifacts ran. The isolated storage checks passed 27 tests per profile, including
the strengthened attempt-counter assertions. Unchanged backend test/example and
lint receipts were reused. No consumer compatibility fix or dependency change
was needed. Linux/CUDA and unselected workspace consumers remain unchecked.
