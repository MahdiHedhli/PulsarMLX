# Quickstart: Feature 018 Validation

## Locate the active feature

```sh
cat .specify/feature.json
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

## Tier 1: checkpoint-free contracts

```sh
uv run --frozen python -m unittest \
  scripts.research.tests.test_f018_numerical_contract \
  scripts.research.tests.test_f018_evidence
cargo test -p stream --test iq2_xxs_metal --no-default-features
```

Expected: classification, malformed-input, evidence, and portable fallback
tests pass without a checkpoint or successful Metal dispatch requirement.

## Tier 2: native Apple Metal synthetic gate

```sh
cargo test -p stream --test apple_metal_bridge -- --ignored --nocapture
cargo test -p stream --test iq2_xxs_metal native_iq2_xxs -- --ignored --nocapture
```

Expected on arm64 macOS: no-copy registration, 100 deterministic packed GEMV
repeats, malformed request rejection, and teardown tests pass with zero fallback.

## Tier 3: admitted real matrix

```sh
PULSARMLX_GLM_GGUF='<checkpoint-directory>' \
uv run --frozen python scripts/research/benchmark_glm52_iq2_xxs_metal.py \
  --rung matrix \
  --out docs/research/glm52/raw/f018-iq2-xxs-matrix-0001.json
```

The command fails clearly when the external checkpoint, immutable identity, or
native helper is unavailable. It never silently skip-passes.

## Evidence regeneration

```sh
uv run --frozen python scripts/research/analyze_glm52_iq2_xxs_metal.py --check
uv run --frozen python -m unittest discover -s scripts/research/tests -v
scripts/research/check_staged.sh
git diff --check
```

## Full repository gates

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
specify check
specify integration status
```

P1, P2, and golden-eight are not part of the quickstart. P1 requires a separate
clean-source admission decision after the complete-layer rung.

## IQ3-down extension

Checkpoint-free native qualification:

```sh
cargo test -p stream --test iq3_xxs_metal -- --nocapture
```

The Tier-3 matrix entry point is added only after the independent
`iq3-down-numerical-qualification-contract.md` source is committed. It must use
a fresh output and the already admitted symbolic checkpoint directory. P2,
golden-eight, and a third kernel remain excluded.
