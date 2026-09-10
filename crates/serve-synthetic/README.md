# PulsarMLX synthetic serving fixture

This standalone crate implements the synthetic-only API documented in
[`../../docs/serving/synthetic-api-contract.md`](../../docs/serving/synthetic-api-contract.md).
It provides a bounded loopback fixture for raw HTTP and official OpenAI Python
SDK integration tests. It performs no inference and has no model dependency.

Run the Rust checks from this directory:

```console
cargo test
cargo clippy --all-targets -- -D warnings
```

The SDK and mutation commands require the exact Python packages in
`tests/sdk-requirements.txt`. Supply newly created test-only token files; do not
use an existing OpenAI key or configuration.
