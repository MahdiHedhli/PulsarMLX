# V11 implementation measurement: active-source repair and change review

Date: 2026-09-20. Scope: source-only. Checkpoint access: 0.

## The failure

`generate_f017_v11_measurement_v1.py --check` reads `implementation_head`
from the frozen v8 record (`f35d3411`, 2026-09-03) and then compares the Git
bytes **at that head** with the **current working tree**. The two are only
equal while the branch stays at the measurement head, so the check has failed
on every FULL_NATIVE run since `5b39a21a` ("feat: simplify Event 06 to minimum
gate path", 2026-09-03) — the accepted commit that changed seven of the 36
measured bodies. The observed message is
`working tree differs from measurement head:
scripts/research/f017_corrected_oracle_primary_wrapper_v11.py`.

This is a defect in the verification, not evidence about the implementation:
v8 is a correct, frozen measurement of `f35d3411` and remains one.

## What actually drifted

Seven of 36 measured paths, all in the single accepted commit `5b39a21a`:

| path | v8 sha256 | current sha256 |
|---|---|---|
| `f017_corrected_oracle_primary_wrapper_v11.py` | `6bec968b7f82…` | `1fda818af33e…` |
| `f017_corrected_oracle_secondary_wrapper_v11.py` | `2dad5b54bdc8…` | `97e640e1e0fa…` |
| `f017_result_envelope_v11.py` | `6f1f1f3f3876…` | `572f4f03e8e0…` |
| `f017_result_bundle_builder_v11.py` | `296fc64befb9…` | `8853623824f4…` |
| `qualify_f017_v11_full_geometry_v1.py` | `d6507262519d…` | `aeb6df8b6619…` |
| `qualify_f017_v11_failure_campaign_v1.py` | `e786fed7dba0…` | `2ab9b24041e1…` |
| `validate_f017_v11_execution_authority_v1.py` | `8277276239ed…` | `5a123ec88b80…` |

The remaining 29 measured bodies are byte-identical to v8 — including both
numerical cores, `f017_corrected_oracle_primary_numerics_v3.py` and
`f017_corrected_oracle_secondary_numerics_v3.py`. The scientific numerical
authority did not change.

## Review of each changed body

Read in full at `f35d3411..1b569190`:

1. **Both `..._wrapper_v11.py`** — the public `execute_and_bank` /
   `execute_target_and_bank` entrypoints are renamed to `_minimum_gate_*`,
   and the original names are retained as fail-closed stubs that `del` their
   arguments and raise `RuntimeError("superseded by F017 Sequence 39
   minimum-gate path")` *before* descriptor validation, any source read, any
   numerical execution and any banking. The numerical call
   (`primary_core.execute_outputs` / `secondary_core.execute_outputs`) and its
   arguments are unchanged; the secondary still gates on
   `require_primary_terminal` first. Net effect: the old call path can no
   longer execute; the new one is identical plus `_write_once=True`.
2. **`f017_result_envelope_v11.py` / `f017_result_bundle_builder_v11.py`** —
   add an opt-in `_write_once` payload policy: the artifact is opened
   `O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW`, `_set_user_immutable(fd, True)` is
   applied and the descriptor is rewound, instead of the close/fsync/reopen
   read-back used when the flag is false. `_write_once` is type-checked
   (`type(...) is not bool`) before use. The non-write-once path is
   byte-for-byte the previous behaviour, so the qualification harnesses keep
   their existing semantics through `_qualification_bank_output_bundle`.
3. **`qualify_f017_v11_full_geometry_v1.py` /
   `qualify_f017_v11_failure_campaign_v1.py`** — import
   `_qualification_bank_output_bundle as bank_output_bundle`; no other change.
   Their committed qualification outputs are still compared byte-for-byte by
   CI (`f017-v11-full-geometry-qualification-v2.json`,
   `f017-v11-result-failure-qualification-v2.json`), which both still pass.
4. **`validate_f017_v11_execution_authority_v1.py`** — extends the authority
   validation to the added minimum-gate modules.

Verdict: the change set narrows what can execute and hardens artifact
banking. It does not alter any numerical body, tolerance, geometry or result.
Nothing here re-opens an accepted scientific result, and this review does not
grant one: it records that the drift is accounted for, reviewed and
lineage-bound.

## The repair

`generate_f017_v11_measurement_v2.py` produces
`f017-v11-result-envelope-implementation-measurement-v9.json` and separates
the two questions:

* **Historical** — v8's own bytes (`c529221a…`), schema, head, tree, path
  count and path-set digest are asserted, and each measured path's blob id and
  SHA-256 **at `f35d3411`** must still equal what v8 recorded. v8 is never
  rewritten or regenerated.
* **Current** — every measured path's working-tree bytes must equal the Git
  object at the head being measured, and those bytes are inventoried into v9.

The measured path set is read from the predecessor, not restated, and its
digest is asserted against a constant (`6ddd0dcc…`), so the active measurement
cannot widen its own scope. Paths whose current bytes differ from v8 are
listed in `drift_from_predecessor` with both blob ids, both digests and the
accepted commits that produced them; drift with no commit lineage, and any
drift in a numerical core, are hard failures. The complete report is printed
before any exception is raised.

No `--skip`, no path removal, no swallowed exception, no evidence-only
reclassification. `original_checkpoint_access` stays 0.

Negative controls are exercised by
`scripts/research/tests/test_f017_v11_measurement_v2.py`: mutated working-tree
source, missing working-tree file, missing object at head, tampered
predecessor blob id, historical drift at the frozen head, wrong predecessor
schema/head/tree/bytes, widened source set, drift without lineage, and
numerical-core drift.

## Consumers

The FULL_NATIVE step in `.github/workflows/macos.yml` now runs
`generate_f017_v11_measurement_v2.py --check`. `generate_f017_v11_measurement_v1.py`
stays in the tree as the generator that produced v8 and is no longer a CI
gate. The Event 05 readiness/scientific-access authorities keep binding v8 —
they describe `f35d3411` and are unchanged by this repair.

## Addendum 2026-09-20 — consolidation of the qualify line

Scope: source-only. Checkpoint access: 0. Nothing above this heading is changed.

Consolidating `qualify/f017-qwen-admission-c2-20260913` onto the native line
(`work/glm52-weekend-20260920`) brings in commits that change measured V11
bodies the native line had never seen, so the committed v9 record no longer
reproduced at the consolidated head and
`generate_f017_v11_measurement_v2.py --check` reported
`ACTIVE_MEASUREMENT_DRIFT`. That is the designed behaviour of an *active*
measurement: the record inventories the bytes at the current head, and the
remedy the generator itself prescribes is to regenerate it in the same commit
as the source change. This addendum is the accompanying review; the v9 record
regenerated alongside it binds this file by sha256.

**Four measured bodies moved, not three.** The count is stated here because a
first reading of the drift named only the three oracle bodies; the fourth is
the validator that checks them.

| Measured path | predecessor sha256 | current sha256 | accepted qualify-line commits |
| --- | --- | --- | --- |
| `scripts/research/f017_corrected_oracle_primary_wrapper_v11.py` | `6bec968b7f82ad719fc3927f96df9bca07ec8d73c0f962df2a29f7b4446af4fb` | `515b23b0ac4fd382b9f4a75d01b4bbabe079020e17834347d6c1cfa2d7529133` | `1f49d767` |
| `scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py` | `2dad5b54bdc875d981dd5d5f7cf6eb8c78c83f751925a063e5423f04b11a0d22` | `77b3b473f3744c88f37ab18175df6ace4f6e44d6b15aeefa1832aa3913834586` | `e7759c3e` |
| `scripts/research/f017_corrected_oracle_primary_target_source_v11.py` | `3942be5766513eb5b96fa4dd342b96d98cb1b1923254ca7479daa8b368063f27` | `33e6473aff9ba468b0614d5f06261c8995bf4ac609f9b61e59c6238b9cd99f74` | `1f49d767`, `6f59d9db` |
| `scripts/research/validate_f017_v11_execution_authority_v1.py` | `8277276239ed6ec35bd9085b7fd29133468c95d82b6c70135b9f3d629fd55966` | `dec34ba2157f04dcea6e64347bb96dc4288bfc8d676fdb1b10801c5146602253` | `0ae4c6f1`, `f52cd006` |

All five accepted commits are contained in `qualify/f017-qwen-admission-c2-20260913`
and in none of the native line; `git cherry` had already shown that no commit on
this line has a patch equivalent on the native side. The remaining four drift
entries in the record (`f017_result_envelope_v11.py`,
`f017_result_bundle_builder_v11.py`, `qualify_f017_v11_full_geometry_v1.py`,
`qualify_f017_v11_failure_campaign_v1.py`) are unchanged from the previous v9:
they carry the already-reviewed `5b39a21a` lineage only.

### What each change does

**`f017_corrected_oracle_primary_wrapper_v11.py` (`1f49d767`).** Adds primary
read-observation instrumentation around the existing path. It imports the
observation helpers, starts an observation owner before the descriptor source is
built, marks the `CORE` / `CORE_COMPLETE` / `BANK` phases around the unchanged
`primary_core.execute_outputs(...)` call, wraps the execute-and-bank body in
`try/except BaseException` so a raising path still finishes its observation as
`RAISED` (attaching it to the exception) before re-raising, and adds one field,
`primary_read_observation`, to the returned bundle. The numerical call itself,
its arguments and the banked bundle are otherwise untouched.

**`f017_corrected_oracle_secondary_wrapper_v11.py` (`e7759c3e`).** The symmetric
change on the secondary side, plus a source swap: the descriptor prefix now comes
from `f017_secondary_read_observation_prefix_v1.open_secondary_descriptor_prefix`
instead of `f017_corrected_oracle_secondary_target_source_v11`. Phases
`PRIMARY_PREREQUISITE`, `CORE`, `CORE_COMPLETE` and `BANK` bracket the unchanged
`secondary_core.execute_outputs(...)` call and the unchanged
`require_primary_terminal(...)` prerequisite check.

**`f017_corrected_oracle_primary_target_source_v11.py` (`1f49d767`, `6f59d9db`).**
Re-bases `PrimaryDescriptorSourceV11` from
`f017_corrected_oracle_primary_target_source_v10` onto
`f017_primary_observed_descriptor_source_v1`, which is the same V10 semantics with
an observation owner threaded through, and adds the keyword-only
`_observation_owner` parameter to the class and to
`source_from_inherited_descriptors`. This is the commit that separates the *active*
primary observation from the *historical* authority so the two cannot be conflated.
Fourteen lines change; no numerical behaviour is touched.

**`validate_f017_v11_execution_authority_v1.py` (`0ae4c6f1`, `f52cd006`).** Purely
additive hardening of the validator that guards the three bodies above: +249 lines
against 3 removed. It gains AST-level checks — `_imports`, `_one_function`,
`_one_method`, `_require_import`, `_reject_rebinding`, `_reject_imports`,
`_direct_name_call`, `_bridge_get` and
`_validate_active_target_source_separation` — which require the exact observation
imports to be present and bound, reject rebinding or substituting them, and assert
that the active target source stays separated from the historical one. This makes
the gate stricter, not weaker: it is the enforcement that the instrumentation above
cannot be quietly bypassed.

### Numerical authority

Both scientific numerical cores are **byte-unchanged**. The regenerated record
reports `numerical_authority_unchanged` as
`scripts/research/f017_corrected_oracle_primary_numerics_v3.py` (sha256
`56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6`) and
`scripts/research/f017_corrected_oracle_secondary_numerics_v3.py` (sha256
`c1b6b95cf2a597453aeecc43bf1d5c6df5b8488a6ac522bd01771af7b4d0e7d3`), and neither
appears in `drift_from_predecessor`. The generator's own rule — "these bodies must
never drift under a measurement refresh; a v9 that reports them as changed is a
stop, not a re-baseline" — is therefore satisfied, and `verify()` raises nothing:
the run emits `"result": "PASS"` with 28 of 36 bodies unchanged since the
predecessor and 8 carrying reviewed lineage.

The frozen v8 predecessor is not regenerated and is not touched:
`predecessor_historical_verification` still reports 36 verified paths, 0 blob
mismatches, at head `f35d3411`, tree `08864e7d`. `original_checkpoint_access`
stays 0 and no authority is minted by this refresh.
