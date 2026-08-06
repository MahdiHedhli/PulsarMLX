# Feature 002 Reproducibility Guide

**Status**: Frozen methodology, fixture-only workflow, and bounded real CPU
oracle. The immutable external checkpoint was accessed for inspection,
capture, oracle construction, and two unadmitted Apple producer attempts; no
validated public Apple router result exists. A new real run remains unavailable
until T083 passes its quiet-window admission gate.

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
- For resumed real work only, the already authorized immutable checkpoint from
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
future ledger claim proposed for `verified`, use the measured `source_commit`
from its raw record and execute the record's sanitized exact command without
changing its operation, cases, tolerances, counts, or order. A raw v1 record
remains provisional because it cannot itself prove that evidence was committed,
indexed, and reproduced. Only the complete package can promote the ledger
claim. A fixture-only methodology review may instead use the exact committed
methodology revision being audited.

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
sidecars twice in temporary directories, and compares those two fresh runs
byte-for-byte. It does not write publication output into the checkout.

### Frozen fixture publication package

The accepted synthetic input set contains three records whose experiment
outcomes are `passed`, `failed`, and `aborted`. Their internal claim-boundary
states are fixture fields, not public claims-ledger rows. Six expected artifacts
are committed beneath `fixtures/research/router-v1/expected/`:
a Markdown table, CSV table, bounded SVG, and one provenance sidecar for each.
Artifact commit `ed9846ac9b120580b579eb669ff4370b918a5c91` froze those
bytes. All displayed measurements are constructed contract-test values, not
checkpoint, MLX, or Apple GPU observations.

After the fixture-only commands, the checkout must still have no non-ignored
changes:

```sh
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

At commit `d6f5820050cdc59944a7b2af26b7b0c2c15767c6`, a detached
clean worktree regenerated the six files outside the checkout. The focused
generator/package suite passed 28 of 28 tests, fixture verification accepted
three records and zero claims, recursive byte comparison was empty, an
independently sorted SHA-256 comparison was empty, and the checkout remained
clean. The following bounded pattern reproduces the committed baseline from a
clean checkout containing the expected files:

```zsh
set -eu
t057_output=$(mktemp -d "${TMPDIR:-/tmp}/pulsarmlx-fixture.XXXXXX")
case "$t057_output" in */pulsarmlx-fixture.*) ;; *) exit 1 ;; esac
trap 'rm -r -- "$t057_output"' EXIT
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_tables.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir "$t057_output/expected/tables"
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_figures.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir "$t057_output/expected/figures"
diff -ru fixtures/research/router-v1/expected "$t057_output/expected"
diff -u \
  <(cd fixtures/research/router-v1/expected && \
    find . -type f -print0 | sort -z | xargs -0 shasum -a 256) \
  <(cd "$t057_output/expected" && \
    find . -type f -print0 | sort -z | xargs -0 shasum -a 256)
test -z "$(git status --porcelain=v1 --untracked-files=all)"
rm -r -- "$t057_output"
trap - EXIT
```

Successful comparisons emit no `diff` output. Each sidecar records the exact
generator and hash, normalized generation command, all three fixture paths and
hashes, fixture-record source commit, and output hash. Fixture provenance must
not be described as a measured model commit.

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

After the external oracle bundle passes the complete read-only verifier, its
bounded public projection is installed from a clean commit with:

```sh
PULSARMLX_MODEL_GGUF='' python3 -B \
  scripts/research/oracle_publication.py \
  --oracle-candidate "$PULSARMLX_ORACLE_OUTPUT"
PULSARMLX_MODEL_GGUF='' python3 -B \
  scripts/research/oracle_publication.py --check
```

The publisher independently reconstructs the input and router hashes, full
softmax, ordered top-8 IDs, selected probabilities, and normalized weights. It
retains only public derived values and immutable source/model/tensor identity.
It writes byte-identical records to `fixtures/research/router-v1/real/` and the
dedicated `docs/research/raw/002-router-parity/oracle/` support subtree, then
installs the fixture manifest last. Existing conflicting bytes, symlinks,
partial completed state, private paths, model/tensor bytes, and unknown files
are rejected. The nested support record is not an Apple experiment and is not
input to the result table or figure generators.

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
PULSARMLX_PUBLIC_CANDIDATE=\
"$PULSARMLX_ROUTER_EVIDENCE/<experiment-id>.json"
python3 scripts/research/publish_evidence.py \
  --candidate "$PULSARMLX_PUBLIC_CANDIDATE" \
  --output-dir docs/research/raw/002-router-parity
```

Only a bounded, schema-valid, public-safe candidate may be installed with
`publish_evidence.py`. Installation is append-only, exclusive, atomic, and
refuses an existing experiment ID. The staged raw record is scanned and then
committed and pushed before tables or figures are generated from that exact raw
commit. The artifact manifest and reviewer index must name repository-relative
paths and hashes. Reproduction always creates a new attempt; it never
overwrites historical evidence.

Every attempt, rerun, correction, protocol amendment, and reproduction uses a
new experiment ID. Failed and aborted history is neither mutated nor deleted.
A duplicate ID under any filename, malformed existing history, unsafe path, or
partial install stops publication atomically. Raw evidence is committed and
pushed before tables or figures are generated. Generators write to fresh
destinations for review and byte comparison rather than overwriting history.

The ledger states are distinct from experiment outcomes. `provisional` means a
bounded claim lacks the full promotion chain; `verified` requires exact-scope
package validation and clean-checkout reproduction; `rejected` preserves a
claim contradicted by evidence; and `unsupported` marks an interpretation
outside the evidence boundary. A raw `failed` or `aborted` experiment remains
an immutable outcome and is not relabeled as a ledger state.

## Expected outcomes and failure handling

Fixture-only success proves only the schema, validator, statistical method,
deterministic generators, and publication boundary. It proves no checkpoint
routing or performance. A nonzero command result must be reported with its
bounded error; files are not deleted, tolerances are not widened, and claims
are not promoted. After any terminal real-work blocker, notify `Mahdi-Dev` that
local inference may resume.
