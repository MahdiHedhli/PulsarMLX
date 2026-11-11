# Copied resident expert MLP

The experiment attaches a synchronous, copied gate/up/activation/down consumer to the two-slot host cache and the public step coordinator. It consumes only the nine named tensors of each fixed D=128, H=64, E=3, M=1 synthetic recipe. A step returns ordered concatenated F32 vectors and the deterministic fixture token zero. Copying remains the default. Physical numerical and ownership qualification is pending.

The base is `94af723930f6502e72b4c32c65375735b1be3900`. The [historical MLP source](https://github.com/MahdiHedhli/PulsarMLX/tree/79e5de15271b2b27439fcc3b2404c5026ac2584a/crates/mlx-expert-mlp) supplies the unchanged activation, numerical experiment and original fixtures. The import manifest records all 93 donor objects and 28 shared numerical dependencies. Host evidence records the actual commands, linkage, results and capacity observations.

## Source and execution

`Population::load` verifies the compiled view manifest. `Population::open` binds the fixed three experts' nine independent component hashes, the original shard/config/manifest, the derived index and the separate framed metadata digest. The original six activation files happen to be byte-identical. Fixture preparation verifies all six. Each new step reads the matching recipe's 512-byte original activation. Replay uses the retained result. Source preparation and the independent CPU reference can inspect these tiny synthetic files. Execution reads selected weight ranges through the sealed reader.

`CopiedResidency::admitted_class` borrows the actual layer and immutable expert request. `Geometry::from_cache` validates the role order, D/H/E, groups and recipe before staging. Default uses 4/4/4 bits and mixed uses 8/4/8. `stage_parts` checks the nine exact lengths and hashes before it takes a single owned copy per component. Packed data stays U32 and scales/biases stay BF16. The allocating arm opens a second bounded reader and checks its full plan, metadata, ranges and loaded hashes against the same authority. Its cache remains empty.

`resident::setup` constructs the real `StepCoordinator<ResidentExecutor<D>>`. The fixed requests at positions zero and one require 3,072 and 1,536 output bytes. The first demand is 0,1,0,2,1,0. Failed delivery occurs after the first commit. Matching replay returns the same retained allocation. The second demand is 0,1,0. Actual native operation counters in snapshots count completed stages. The successful sequence requires two dispatches, nine consumptions and two activation reads.

The native driver owns one thread-affine context per occurrence. It checks real GPU facts and both gate/up descriptors before importing, runs the unchanged copied bridge with two BF16-to-F32 conversions at each projection, then checks both intermediates. The donor activation runs in mode zero with its own stream, upper gate and two-sided up clamps, explicit SiLU materialization, hidden and two clamp readbacks. The down guard uses that actual hidden buffer. Each projection returns its evaluated, synchronized F32 copy. Retirement checks synchronization, context drop, handler/cleanup status, double frees and result-handle census. Success requires positive, balanced ownership observations.

Cancellation is checked at tuple entry and between stages. Once a native call starts, the owner waits for retirement. A fully retired domain refusal can retain immutable CPU payloads. Unknown completion, unwind, failed synchronization or cleanup returns a callback error, stops the wave and quarantines the executor before returning to the coordinator. A finish failure prevents commit. Primary and secondary errors and partial records survive. The driver checks cache-limit initialization, clear status and allocator observations. Supervisor termination leaves unobserved retirement uncertain.

## Working memory and copies

Both arms reserve one constant `W_cache + 1,048,576 + 33,554,432` bytes for the life of the executor. The cache owns two complete slots, metadata and its existing control and workspace charges. Default and mixed stage 13,824 and 22,016 component bytes respectively. The allocating arm additionally owns the second source's metadata and one simultaneous full tuple. The host ledger charges a 512-byte activation copy, bounded projection/activation intermediates and shape/name bookkeeping, nine saved rows of at most 32 KiB, and 192 KiB of record/serialization workspace. The coordinator charges input, output, retained prior output and growing token history. Its second-step peak adds 5,128 bytes to the standing charge.

Each occurrence stages nine component copies, performs 12 projection data imports including the down input, six metadata widenings and three projection readbacks. The activation imports two intermediates and two scalars and reads back hidden plus both clamps. The final concatenation is coordinator output. The native logical bound takes the largest simultaneous projection or activation live set plus 4 MiB temporary headroom. Per-projection active/peak values belong to the inherited reset interval. Activation has a separate reset interval. Cache observations are reported alongside those intervals. Host RSS in host evidence concerns the measured process. These measurements establish no physical allocation cap or throughput.

## Host verification

Use two Cargo jobs, an external target directory per profile and a single test thread. Remove native prefixes and loader overrides. Compile with `cargo test --offline --locked -p mlx-expert-mlp --no-run --message-format=json`, adding `--release` for the release pass. Inspect each test's libraries before execution. The donor activation test builds and runs a separately inspected C++ host stub. A diagnostic built without native capability exits 69. The isolated native Rust type check is `cargo check --offline --locked -p mlx-expert-mlp --features resident-native --bin qualify-resident-mlp`.

```sh
python3 -B scripts/research/f020_resident_mlp_fixtures.py
python3 -B scripts/research/tests/f020_resident_mlp_checks.py
```

The independent checker starts at the six original input/checkpoint pairs. It verifies gate, up, hidden, actual-hidden local down and original-input end-to-end output, using the unchanged rational reference, gamma selection, clamp bits and E_act=1/128. The historical beta_B=5201/4194304 remains proof provenance. After every row passes, the checker compares corresponding allocating and cached stage bytes. Synthetic structured records and the test driver exercise these gates locally.

## Readiness repair

The retained runtime is admitted through the actual child's fixed library directory. Static inspection uses bounded `otool -L` and `-l` observations, distinguishes imports from own IDs and records the lexical entry, symlink chain, canonical target, file stamps and content digest. An MLX image must actually import the retained runtime. Its expected SHA-256 is `36d3439033afa76443943a1a6967623cde063e435283ccf3b4e6a4e93a8755ca`. Alternate search routes, competing system overrides and drift fail admission. The native child retains its fixed library path. Its isolated Python verifier starts with the system path and the existing home directory for the ordinary authenticated client. The build binds the six project Python modules embedded in the child. A source or installation change after an exclusive claim leaves that claim spent.

For the locked little-endian Darwin arm64 layout, exact source metadata is the fixed term plus the UTF-8 byte count of the canonical **fixture directory**. Default has a fixed term of 5,681 bytes and mixed has 6,195. The proof charges the bounded source, identity, shard/header/catalog/index, held files, overrides and retained JSON from the original fixture. Every root has its own identity, including paths of equal byte length. `W_cache = 2*S + M + 1 MiB + 64 KiB`. Both arms reserve `W_cache + 1 MiB + 32 MiB`, and the allocating arm charges the second source's actual metadata. The second-step admission adds 5,128 bytes. The checked host controls compare both arms and recipes at short, long and non-ASCII roots against the actual Rust executor.

The accounting proof binds the measured layout, checker bytes, fixture authority and native build witness for Rust 1.95.0 (59807616e 2026-04-14). A different build/layout requires its own verified correspondence. The C and C++ syntax check used the pinned MLX-C headers with the four previously accepted patches in a separate inspection root. All 29 included MLX-C headers matched the patched closure. The [host evidence](readiness-evidence.json) records the term table, header provenance, observed relocated charges, commands, tests and limits.

## Future physical interface

A separately authorized physical build must supply its actual child, Cargo artifact message, linkage and SHA-256. Those physical identities are pending. The supervisor and checker use the ordinary CPU Python runtime. The native child alone receives the explicit retained prefixes and its separate feature.

```sh
CARGO_BUILD_JOBS=2 MLX_PREFIX="$RETAINED_PREFIX" MLX_C_PREFIX="$RETAINED_PREFIX" \
  cargo build --offline --locked --release --features resident-native \
  -p mlx-expert-mlp --bin qualify-resident-mlp --target-dir "$EXTERNAL_TARGET" \
  --message-format=json > "$BUILD_CAPTURE"
```

Save the complete single matching release `compiler-artifact` JSON message as a separate original file. The build receipt is a JSON object with `commit`, `tree`, `prefix`, `binary_sha256`, `artifact`, `artifact_sha256` and `linkage`, plus the two witness fields below. The linkage value is the ordered array of actual `otool -L` dependency lines after the first line, retaining indentation. The binary must be the emitted release executable at the exact location in the artifact. Keep receipts and reports outside the source tree.

During the separately authorized preparation, include `verifier_modules` (module names mapped to SHA-256 of the exact build source) and `accounting_abi_stamp` in the original build receipt. The stamp uses the actual build compiler, target and layout. From the clean source tree, with the build toolchain selected, these commands print the prospective receipt additions. The physical child must contain the matching compiled witness and independently checks its embedded module set before its first native call.

```sh
python3 -B - <<'PYTHON'
import json, subprocess, sys
from pathlib import Path
sys.path.append(str(Path("scripts/research").resolve()))
import f020_resident_mlp_supervise as supervisor
compiler = subprocess.check_output(["rustc", "-V"], text=True).strip()
stamp = "pulsarmlx.resident-layout/1|aarch64-apple-darwin|" + compiler + "|end"
print(json.dumps(dict(accounting_abi_stamp=stamp, verifier_modules=supervisor.verifier_modules()), sort_keys=True))
PYTHON
```

Preparation ends with the original physical build receipt and read-only `describe` output. A later committed grant binds those observed identities before `run`. Physical child/build hashes remain pending.

A private configuration names canonical absolute paths in `repo`, `binary`, `build`, `prefix`, `installation` (original install receipt), `freeze`, `diagnostic_receipt` and `output` (a fresh location). The original historical receipts bind the prefix and stable installation location. The later work order supplies `operator` with its exact `commit`, `path` and `sha256`. The configuration digest excludes only that operator object so the physical build can be bound without a self-reference. The supervisor reads the immutable prompt and sidecar through the existing authenticated GitHub client. A later Studio prompt must include exactly one fenced `resident-mlp-grant` block containing the one-line JSON produced by the read-only description command.

```sh
python3 -B scripts/research/f020_resident_mlp_supervise.py describe "$CONFIG"
python3 -B scripts/research/f020_resident_mlp_supervise.py run "$CONFIG"
python3 -B scripts/research/f020_resident_mlp_supervise.py inspect "$CONFIG"
```

`describe` identifies the current source tree and complete file/mode inventory, build, retained installation, host, fixture, checker and supervisor. `run` requires the grant, creates the stable exclusive claim beside the original installation receipt, and records intent, actual PID, exit and reap for each serial child. The ordered pairs are default allocating, default cached, mixed allocating and mixed cached. Each child receives at most 300 seconds within a 900-second campaign. Failure stops the sequence and retains the original files. Changing output roots cannot create a second claim. The single grading intent covers all 36 occurrences. `inspect` verifies the saved result and its component hashes without another grade.

Each arm saves a summary and nine bounded `occ-NN.json` records. The summary binds the intent, identity, provenance, fixture, allocation policy, ledger and coordinator snapshots. Rows bind ordinal, step, recipe, expert, slot/generation, complete component hashes, copy counts, gate/up/activation/down bits and hashes, actual down input, allocator intervals and observed cleanup census. Partial or crossed evidence fails admission. Static runtime identity is separate from observations of loaded libraries and the metallib read from its admitted installation path.

Source publication and ordinary CI do not start this physical campaign.
