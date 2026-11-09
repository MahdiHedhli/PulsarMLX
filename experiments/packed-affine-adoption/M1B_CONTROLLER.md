# M1b: one prospective physical-Studio run

This is the host controller for the optional warm-buffered copy-removal screen.
The Rust014 build and its host tests do not authorize a run, qualify another
native candidate, or measure performance. The previously qualified child is
the retained C2 executable. Copying remains the shipping default, including
after a benefit pass. Copied M2 residency has a separate decision.

## Build and bind the two executables

Use the returned S commit/tree, not a moving branch, for the controller.
Keep separate, clean C2/Q/R2/S checkouts with the canonical source origin.
`m1b-source-profile-v1.json` pins the first three, all permitted additions,
frozen policy, original Studio acceptance, planner decision, contract,
retained Python and child. S is external to this profile. Reconcile all four
registered roots, their ownership and the six externally frozen file digests.

A **later, independently pinned and explicitly launched physical-Studio work
order** must provide the authority. Its committed name must be a later Studio
Rust-engine prompt; its exact bytes must explicitly say
`STUDIO_M1B_SCREEN_ONCE` and `phase=m1b`. The adjacent checksum for each
sealed document is the lowercase SHA-256 and its exact basename. Verify the
future prompt's commit, path and bytes through the authenticated repository
before preparing the external authority. Neither Rust014 nor the previous
physical acceptance is a timing grant.

Only on that later launch, select a fresh external private build-record
directory and a distinct empty external Cargo target. With all loader,
Git, model, native-prefix and native-require variables absent, use:

```sh
umask 077
env -i HOME="$HOME" PATH="$TOOL_PATH" CARGO_TARGET_DIR="$NEW_TARGET" \
  CARGO_BUILD_JOBS=2 RUST_TEST_THREADS=1 "$CARGO" build --offline --locked \
  --release --manifest-path "$S_SOURCE/experiments/packed-affine-adoption/Cargo.toml" \
  --no-default-features --bin m1b-controller --message-format=json \
  >"$BUILD_CAPTURE/cargo.jsonl" 2>"$BUILD_CAPTURE/cargo.stderr"
```

Use only a successful Cargo exit and its single non-test `compiler-artifact`
for the release `m1b-controller`, with `features=[]`. Save that exact JSON
line (including LF) alone as `artifact.json`. Resolve its actual executable;
record its hash, then inspect it with `/usr/bin/otool -L`. Neither the
controller nor selected Python may link MLX or Metal. Do not build, copy
or substitute an adoption probe from S. Physical controller and build hashes
are pending until the actual future build.

Write one external build receipt, with exactly these fields:

```json
{"schema":"pulsarmlx.m1b-controller-build/1","commit":"<S_COMMIT>","tree":"<S_TREE>","binary":"<ACTUAL_CONTROLLER>","sha256":"<ACTUAL_CONTROLLER_SHA256>","linkage":["<each actual otool -L line after the header, untrimmed>"],"features":[],"artifact_message":"<ABS_ARTIFACT_JSON>","artifact_message_sha256":"<ACTUAL_MESSAGE_SHA256>"}
```

The native identity is separate: original Studio004 build receipt
`a03d98087a6e8e6798bd3bd9b3b14398a0ea8927e7aa3ecc821580360bd67cdc`,
retained child `012b6f301662dbbf429ac277ec930e71c566c99ab666bd478047e4bca828cd1b`.
The operator must also bind and retain the original installation receipt,
two spent M1a claims, original Studio004 operator authority, ready, freeze,
bound, parent completion, build, untransformed acceptance, all native
reports/outputs and scientific gate files, the 19 historical originals and
46 inputs. The original acceptance supplies the locations; the historical
freeze and diagnostic receipt independently name the original installation.
The Studio004 handoff is a hash index, never a substitute for original bytes.
Rust011's four actual publication files are resolved at the original authority's
CI paths. Inspect saved decisions only.

## Authority and launch

Supply one original JSON file and adjacent `.sha256`, in a private operator
control directory separate from timing. Its closed schema is:

```
schema              "pulsarmlx.studio-m1b-authority/1"
purpose             "STUDIO_M1B_SCREEN_ONCE"
phase               "m1b"
host_role           "m1-ultra-studio"
launch_authorized   true
shipping_default    "copied"
allowances          {"campaign":1,"raw":0,"numerical":0}
prompt              {commit, filename, sha256} of the later Studio work order
sources             {S,C,Q,R}; each value is {root,commit,tree}; C=C2, R=R2
added_files         all six profile-relative paths -> externally frozen S SHA-256
paths               closed canonical absolute path roles listed below
identities          contract, decision, controller, controller_build, python,
                    child, native_install, acceptance, handoff, profile -> SHA-256
```

| Path role | Required location |
|---|---|
| prompt, decision, contract | Exact local originals and adjacent sidecars; the last two are the pinned planner JSON and controller contract |
| handoff | Exact Studio004 publication handoff JSON, never a generated index |
| acceptance | Original Studio004 output-root acceptance, 3,557,122 bytes |
| python, child | Actual retained executables at the original Studio004 build locations |
| controller, controller_build | Actual S executable selected above and its immutable build receipt |
| native_install | Installation receipt at the original custody location |
| claim | That receipt's sibling `f020-studio-m1b-screen.claim.json`, initially absent |
| timing | One new absent directory, with existing canonical parent |

Keep timing disjoint from all source roots, native prefix, inputs, build/receipt,
control/state/campaign/output roots. Control/build/failure capture must be
independently owned and external. Retain the original claim directory without
renames or relocation. No overwrite, path alias, resume or retry.

The prospective command is exactly one foreground controller invocation;
`CAPTURE` denotes a new exclusive operator-owned process capture directory.
The launcher must preserve intent, physical prompt identity, stdout/stderr,
actual wait and exit there even if the timing root cannot be created:

```sh
env -i PATH=/usr/bin:/bin PULSAR_ADOPTION_PHASE=m1b \
  "$CONTROLLER" "$ABS_AUTHORITY" "$AUTHORITY_SHA256" \
  >"$CAPTURE/controller.stdout" 2>"$CAPTURE/controller.stderr"
```

Inspector invocation is internal: pinned Python with `-I -S -B -X
pycache_prefix=/dev/null`, exact S helper, authority path/hash, stage
(`pre` or `live`), and actual controller executable. It reads the actual
C2/Q/R2 origins, compares original custody, source proofs, CI prerequisite,
build/linkage, host and static runtime on Darwin arm64 Mac13,2, Apple M1
Ultra, 128 GiB, 16 KiB pages, macOS 26.0 build 25A354. No
`DYLD_*`, `LD_LIBRARY_PATH`, `LD_PRELOAD`, `PYTHONPATH`, `PYTHONHOME`,
`GIT_*` or model path in the controller/inspector context. Child context
alone comes from the existing harness's cleared `child_env` with its fixed
prefix/lib loader setting, isolated arm directory and TF32 disabled.

## Timing, outputs and failure

After full original and live admission, the controller exclusively creates
the stable claim. The 1,800-second monotonic budget starts immediately on
acquisition, before setup. Setup creates the new root and one external
`freeze.json`. Each arm repeats admission, writes an exclusive config and
intent, and starts only the hash-matching C2 child. Native argv is **config
path and absent output directory only**. The config inherits the verified
original case's binary, source, tree, dependency/generator, fixture, host,
native libraries and metadata identities. Only mode, arm, sequence and
operation count are set by the fixed state machine. Modes are fill/resident;
methods are copied/adopted. No user-specified count, case or binary override.

The controller records each serial process outcome, raw events, timings and
hashes. It applies the smaller of 120 seconds and the remaining budget,
terminates only its owned process group on failure, and records actual reap
or unknown cleanup. An execution, output, resource or cleanup failure ends
the campaign. A stall, occupied state, failed child or changed output must
not be reinterpreted as a noisy baseline or another invocation.

There are four warmups per fresh process; fill reads on every operation and
resident fills just two slots. Use three copied/copied pairs per mode.
Initial counts are 128/4096; only policy-declared unsuitable calibration may
use one 512/16384 recalibration per mode. Preserve both attempts. Freeze
noise and counts before candidate timing. Primary A-gate fill uses three
alternating pairs. Only the policy's mixed result permits three reversed
follow-up pairs, combined over all six. Held-out B-up fill runs only after
primary passes, then the A-gate resident guard. No more than 48 timing
children. All decisions reuse `packed_affine_adoption::policy`.

Timing reports have `outputs=[]`. Every warmup and measured output digest
must agree with its original Studio004 projection. Ordered samples, operational
reads, resident fill counts, copy bytes, setup geometry, balanced lifetime
and the observed 32 MiB working/native/cache and 96 MiB combined logical
reservation are checked. Every sample stays in the record, including short
candidate blocks. No diagnostic whole-slab or pointer-view checks are claimed.

After a terminal schedule the controller re-admits the original evidence,
checks claim, freeze and each sealed arm/config/outcome/report/event digest.
`result.json` uses `pulsarmlx.m1b-result/1` with decision or failure,
admitted identities, calibration/decision steps, chronological arms, complete
reports, samples, process durations, claim/allowance use and final readmission.
Outcomes are `PASS_EXPERIMENTAL_ONLY`, `NO_PROMOTION`, `INCONCLUSIVE`,
or a distinct failure. A preclaim refusal has no new claim. A postclaim setup,
process/cleanup, resource/correctness, deadline or final drift failure leaves
the claim spent. Pre-root or result-write failures go to the external capture;
never write a failure into someone else's directory. Preserve partial arms
and raw outcomes after interruption. Absence of a result is not a pass.

The child's setup/first-operation sum is internal to its run function. Whole
child launch-to-reap and controller admission are distinct observations.
Process-launch/admission-to-first-projection latency remains unobserved; do
not sum overlapping intervals. Physical IO, deduplicated memory, wiring and
layout materialization are unknown. Static libjaccl identity does not prove
a loaded image. This one warm synthetic screen cannot establish whole-model
performance, paging, a physical-memory cap or a shipping change.
