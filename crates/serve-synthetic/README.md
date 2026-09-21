# PulsarMLX synthetic serving fixture

This standalone crate implements the synthetic-only API documented in
[`../../docs/serving/synthetic-api-contract.md`](../../docs/serving/synthetic-api-contract.md).
It provides a bounded loopback fixture for raw HTTP and official OpenAI Python
SDK integration tests. It performs no inference and has no model dependency.

## Running the checks

Rust checks, from this directory:

```console
cargo fmt --check
cargo test
cargo clippy --all-targets -- -D warnings
```

The SDK and mutation commands require the exact Python packages in
`tests/sdk-requirements.txt` in a dedicated environment:

```console
python3 -m venv .sdkvenv
.sdkvenv/bin/pip install -r tests/sdk-requirements.txt
PYTHON=.sdkvenv/bin/python ./tests/sdk_smoke.sh
.sdkvenv/bin/python tests/mutation_guards.py --scratch /tmp/mutants --target /tmp/mutant-target
```

`sdk_smoke.sh` generates a disposable bearer token per run, writes it `0600`,
never prints it, starts the server on an ephemeral IPv4 loopback port, runs the
SDK client against it, asserts the server did not log the token, and stops the
server on exit. Supply newly created test-only token files; do not use an
existing OpenAI key or configuration.

Run the mutation guards in the SDK environment. Run them under a bare
interpreter and the two Python guard mutants cannot execute at all, which the
harness now reports as a setup error rather than counting as a kill.

## CI coverage

This crate declares its own `[workspace]`, so it is **not** a member of the root
workspace and `cargo check --workspace` / `cargo test --workspace` in the
`macOS baseline` workflow never build it. A green run of that workflow is not
evidence about this crate.

The `Serving synthetic qualification` workflow
([`../../.github/workflows/serving-synthetic.yml`](../../.github/workflows/serving-synthetic.yml))
qualifies it explicitly on `macos-15`: formatting, Clippy with `-D warnings`,
`cargo test`, the SDK loopback smoke, and the mutation guards. It asserts
`PULSARMLX_MODEL_GGUF` is empty and is independent of model assets and of the
F017 native qualification path.

Client setup and the qualified client behaviours are documented in
[`../../docs/serving/client-integration.md`](../../docs/serving/client-integration.md).
An opt-in LM Studio adapter is planned but not implemented; see
[`../../docs/serving/lm-studio-integration-plan.md`](../../docs/serving/lm-studio-integration-plan.md).

## Security notes

- The server binds IPv4 loopback only and additionally checks the peer address.
- Exactly one `Host` header value is required; a duplicate is rejected rather
  than resolved in the peer's favour.
- The bearer token is compared in constant time.
- **Token memory (open):** the token is held as a plain `Arc<[u8]>` and is not
  zeroized on drop, so it can persist in freed heap memory or a core dump for
  the process lifetime. For a loopback fixture holding a disposable,
  per-run token this is accepted rather than fixed; introducing a zeroizing
  wrapper is a dependency and lifetime change that has not been made here. Any
  deployment holding a durable credential should revisit this.
