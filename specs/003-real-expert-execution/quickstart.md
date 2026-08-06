# Validation Quickstart: Real Expert Execution

**Status**: Feature 003 scaffolding. Follow after Feature 002 package remains
green.

## 1. Baseline

```sh
git status --short --branch
git rev-parse HEAD origin/main
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
python3 -B scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
```

## 2. Model-free expert fixtures (CI-safe)

```sh
# After fixtures exist:
cargo test -p mlx-backend --test expert_contract
PULSARMLX_MODEL_GGUF='' python3 -B -m unittest discover \
  -s scripts/research/tests -v
```

## 3. Notify and admit

```sh
curl -fsS \
  -H 'Title: PulsarMLX Feature 003 model work starting' \
  -H 'Priority: high' \
  -d 'Please pause local inference. Single-expert MLP validation starting.' \
  https://ntfy.sh/Mahdi-Dev

export PULSARMLX_MODEL_GGUF='<external>/Qwen3-30B-A3B-Q8_0.gguf'
# verify size/hash against Feature 001/002 identity
```

## 4. Oracle freeze then Apple validate-expert

Exact command names and flags are finalized during implementation and recorded
in `contracts/commands-v1.md`. Expected flow:

1. Freeze CPU expert oracle for expert 114 + row-0 input.  
2. Capture public-safe environment (admission).  
3. Run MLX full expert MLP + weighted output.  
4. Sanitize external candidate.  
5. Publish under `docs/research/raw/003-expert-mlp/`.  
6. Clean-checkout reproduction.  
7. Package verify + claims.

## 5. Unsupported

Any multi-expert aggregation, MoE block, layer, logits, tokens, generation,
serving, or tokens/sec interpretation is out of scope.
