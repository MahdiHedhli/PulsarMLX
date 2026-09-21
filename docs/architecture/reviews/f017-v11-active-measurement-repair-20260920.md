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
