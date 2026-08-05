# Feature 002 Reproducibility Guide

**Status**: Frozen methodology and fixture-only workflow. No external
checkpoint has been accessed for Feature 002, no real router result exists, and
the model-backed commands remain unavailable until their implementation tasks
and admission gates pass.

This guide follows the [Feature 002 evidence
contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md)
and the [experiment protocol](EXPERIMENT_PROTOCOL.md). Model weights and local
candidate output always remain outside Git.

## Prerequisites

- A new clean checkout of the exact source commit being reviewed. Do not reuse
  a working tree that contains implementation or evidence changes.
- Native arm64 macOS for any later Apple execution. The fixture-only workflow
  uses Python 3 and does not need a model or MLX device.
- The checked-in schemas, fixtures, scripts, and Spec Kit package.
- For later real work only, the already authorized immutable checkpoint from
  Feature 001 at a caller-supplied absolute external path. Nothing in this
  repository downloads or searches for it.

## Create and verify a clean checkout

Set `PULSARMLX_SOURCE_COMMIT` to the full 40-character commit named by the
record being reviewed. Set `PULSARMLX_REPRO_ROOT` to a new, non-existent path
outside any existing PulsarMLX checkout. These are local shell values and are
not copied into public evidence.

```sh
test -n "$PULSARMLX_SOURCE_COMMIT"
test -n "$PULSARMLX_REPRO_ROOT"
test ! -e "$PULSARMLX_REPRO_ROOT"
git clone --no-checkout \
  https://github.com/MahdiHedhli/PulsarMLX.git \
  "$PULSARMLX_REPRO_ROOT"
git -C "$PULSARMLX_REPRO_ROOT" rev-parse --verify \
  "$PULSARMLX_SOURCE_COMMIT^{commit}"
git -C "$PULSARMLX_REPRO_ROOT" checkout --detach \
  "$PULSARMLX_SOURCE_COMMIT"
cd "$PULSARMLX_REPRO_ROOT"
test "$(git rev-parse HEAD)" = "$PULSARMLX_SOURCE_COMMIT"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
git status --short --branch
git rev-parse HEAD
cat .specify/feature.json
```

The checkout command must fail rather than substitute another revision. For a
future claim marked `verified`, use the measured `source_commit` from its raw
record and execute the record's sanitized exact command without changing its
operation, cases, tolerances, counts, or order. A fixture-only methodology
review may instead use the exact committed methodology revision being audited.

## Immutable inputs

Fixture-only validation uses only committed files under
`fixtures/research/router-v1/evidence/` and `schemas/research/v1/`. These files
are synthetic methodology evidence; they are not model measurements.

The later real experiment is constrained to the inherited Feature 001
checkpoint identity recorded in [MODEL_MANIFEST.json](MODEL_MANIFEST.json).
That inherited identity is not a Feature 002 access result. The router tensor's
occurrence, F32 type, dimensions, offset, length, encoded hash, bias absence,
and scale are deliberately unobserved until the notified read-only inspection.
A filename, upstream identity, or expected shape alone is not router admission.

## Fixture-only reproduction

From the repository root, with the model variable explicitly empty:

```sh
PULSARMLX_MODEL_GGUF='' scripts/research/setup.sh
PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -v
PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
```

The package verifier reads the committed full-schema fixture, validates its
semantic and privacy boundaries, regenerates Markdown, CSV, SVG, and source
sidecars twice in temporary directories, and compares every byte. It does not
write publication output into the checkout.

After the fixture-only commands, the checkout must still have no non-ignored
changes:

```sh
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

## Authorized local model reproduction

This section defines order, not current capability. Do not execute a model
command until tasks T022, T038, T049, T060, and T071 are pushed with green CI;
T072 passes its clean-tree, resource, load, pressure, thermal, disk, and
external-path checks; and T073 receives an acknowledged start notification on
NTFY topic `Mahdi-Dev`.

After those gates, the operator supplies explicit, pairwise-disjoint absolute
paths through the variables documented in the [Feature 002
quickstart](../../specs/002-qwen-router-parity/quickstart.md). The serialized
sequence is read-only model admission, two independent CPU captures, frozen
scalar/NumPy oracle, committed oracle evidence, Apple correctness, then timing.
Any identity, cancellation, tie, correctness, repeatability, fallback, or
resource failure stops the sequence and retains a new failed or aborted
attempt. Synthetic input is never substituted for a blocked real capture.

## Evidence validation and publication

External commands first write candidates outside the repository. Candidate
verification is read-only:

```sh
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input "$PULSARMLX_ROUTER_EVIDENCE"
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --candidate "$PULSARMLX_ROUTER_EVIDENCE"
```

Only a bounded, schema-valid, public-safe candidate may be installed with
`publish_evidence.py`. Installation is append-only, exclusive, atomic, and
refuses an existing experiment ID. The staged raw record is scanned and then
committed and pushed before tables or figures are generated from that exact raw
commit. The artifact manifest and reviewer index must name repository-relative
paths and hashes. Reproduction always creates a new attempt; it never
overwrites historical evidence.

## Expected outcomes and failure handling

Fixture-only success proves only the schema, validator, statistical method,
deterministic generators, and publication boundary. It proves no checkpoint
routing or performance. A nonzero command result must be reported with its
bounded error; files are not deleted, tolerances are not widened, and claims
are not promoted. After any terminal real-work blocker, notify `Mahdi-Dev` that
local inference may resume.
