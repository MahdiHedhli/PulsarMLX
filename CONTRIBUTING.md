# Contributing to PulsarMLX

PulsarMLX is an experimental derivative of Pulsar focused on Apple Silicon
and MLX compatibility. Contributions are welcome when they are narrow,
testable, and preserve the inherited Linux and CUDA paths.

## Engineering principles

- Put correctness before optimization. Establish a reference result before
  tuning kernels, storage, routing, or memory behavior.
- Preserve upstream Linux and CUDA behavior. Platform-specific additions
  should be additive and explicitly gated where appropriate.
- Treat the committed GitHub Spec Kit constitution, feature specification,
  implementation plan, task list, and supporting artifacts as the source of
  truth for requirements and scope. Update them when a design or requirement
  changes.
- Make only verified claims. Record the command, machine context, inputs, and
  actual result for compatibility and performance statements.
- Keep benchmarks reproducible. Document the hardware, OS, toolchain, model,
  quantization, prompt/workload, run settings, warm-up behavior, and command.
- Make explicit which model architectures and quantization formats a change
  supports. A successful synthetic test is not proof of real-model support.
- Prefer focused, incremental commits backed by tests and documentation.
- Never commit credentials, environment secrets, private keys, model weights,
  GGUF or safetensors files, local caches, or large generated binaries.

## Contribution flow

1. Start from a clean working tree and review the current feature's Spec Kit
   artifacts before editing code.
2. Keep the change within a bounded task. If implementation reveals a new
   requirement, update the specification or plan before expanding scope.
3. Add or update tests that exercise the affected behavior, including
   platform guards when the implementation is platform-specific.
4. Update documentation alongside code. Clearly distinguish observed facts,
   inherited capabilities, planned work, and unsupported behavior.
5. Run the relevant validation commands and retain their exact output for any
   result cited in a pull request.
6. Review the complete diff for accidental generated files, weights, secrets,
   unrelated formatting, and changes to upstream behavior.
7. Submit focused commits with messages that explain one coherent change each.

## Baseline validation

From the repository root, run:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

Inspect formatting and Clippy as well:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

The repository may retain documented upstream formatting or Clippy debt. Do
not perform repository-wide formatting or unrelated warning cleanup in a
feature contribution. Fix failures introduced by your change, and document
pre-existing failures accurately.

Before committing, also run:

```sh
git diff --check
git status
```

Run any validation command supplied by the installed Spec Kit version and any
targeted tests required by the active feature. Apple-specific claims must be
validated on Apple hardware; Linux/CUDA preservation claims require suitable
Linux/CUDA validation or must be identified as unverified.

## Pull requests

Describe the problem, the relevant Spec Kit task, the implementation boundary,
and the exact validation performed. Include observed limitations and call out
anything that could not be tested. Performance changes should include a
reproducible comparison against the correct baseline, not an isolated number.

Keep upstream attribution and the MIT license intact. Do not imply endorsement
by the upstream Pulsar project.
