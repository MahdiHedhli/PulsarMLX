# Canonical runner CLI contract v1

## Executable

`f017-glm52-runner` is the only canonical Feature 017 GLM-5.2 runner. It MUST
not invoke Python, the Linux/CUDA `pulsar-cli`, or Feature 018 kernels.

## Common options

- `--out <fresh-json>`: required and created atomically; existing files fail.
- `--validation-mode golden-strict`: required for P1; unsupported modes fail.
- `--stream-mode default-gpu|owned-device`: explicit and recorded.
- `--memory-floor-bytes <u64>`: nonzero absolute admission floor.
- `--environment-manifest <path>`: exact reviewed environment identity.
- `--numerical-mode exact-qualification-scaffold|production-mlx-tier-b`:
  required for fixture and model execution and recorded in evidence. The exact
  scaffold is qualification-only; the production mode cannot silently recover
  through it.

## Execution options

- `--checkpoint-manifest <path>`: required by identity and model modes.
- `--tokens <comma-separated-u32>`: exact IDs; no tokenization is performed.
- `--n-new <u32>`: bounded requested continuation length.
- `--expected-token <u32>`: required for golden-strict one-token validation.

## Mutually exclusive modes

- `--dry-run`: CLI, source, environment, and schema only; no checkpoint access.
- `--adapter-preflight-only`: production adapter lifecycle only; no checkpoint.
- `--checkpoint-identity-only`: shard hashes and catalog only; no tensor read.
- `--fixture-mode <manifest>`: public-safe tiny end-to-end fixture only.

With no mode flag the runner requests real execution. Real execution remains
fail-closed until every required capability and tensor-map gate is present.
P1 requires explicit `production-mlx-tier-b`; the exact scaffold is never a
production fallback.

## Exit codes

| Code | Class |
| ---: | --- |
| 0 | success |
| 10 | admission/environment failure |
| 11 | checkpoint identity failure |
| 12 | lifecycle/ownership failure |
| 13 | numerical/behavioral failure |
| 14 | infrastructure/evidence failure |
| 15 | cancellation |

Unknown, duplicate, missing, or incompatible options are infrastructure errors.
Unsupported runtime capabilities fail before tensor execution. No mode may
silently downgrade to another backend or execution engine.
