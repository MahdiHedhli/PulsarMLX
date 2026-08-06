# Commands Contract v1: Real Expert Execution

## inspect-expert

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- inspect-expert \
  --model "$PULSARMLX_MODEL_GGUF" \
  --expert 114 \
  --evidence "$PULSARMLX_EXPERT_INSPECTION"
```

Read-only admission of gate/up/down tensor ranges for one expert index.

## freeze-expert-oracle (script)

```sh
python3 scripts/research/expert_oracle.py \
  --model "$PULSARMLX_MODEL_GGUF" \
  --expert 114 \
  --input-row "$PULSARMLX_F002_INPUT_ROW" \
  --routing-weight "$PULSARMLX_F002_WEIGHT" \
  --output "$PULSARMLX_EXPERT_ORACLE"
```

CPU-only; must not import MLX worker.

## validate-expert

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-expert \
  --model "$PULSARMLX_MODEL_GGUF" \
  --expert 114 \
  --oracle "$PULSARMLX_EXPERT_ORACLE" \
  --evidence-dir "$PULSARMLX_EXPERT_EVIDENCE"
```

Runs full MLP + weighted output on MLX GPU; retains external candidate.

## Exclusions

No generation, multi-expert aggregation, serving, or automatic model download.
