# Active-source CI input provenance repair

This change repairs the current-source pin for
`scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py` in
`scripts/ci/f017_primary_ci_inputs_v1.json`.

The prior digest, `97e640e1e0fa4da36e7aed407c612ea991681422316f527a585e7c70eb6c8c55`,
is the exact wrapper body at commit `5b39a21aa8369ea2e53ea8e406002cc74250cec3`.
Commit `e7759c3e7be0edf8098e3c9e29c37db88e694e7f` then integrated the reviewed
secondary descriptor-observation prefix and changed the wrapper to digest
`77b3b473f3744c88f37ab18175df6ace4f6e44d6b15aeefa1832aa3913834586`.
The current-input manifest did not move with that active source change.

The consuming runner reads every `inputs` row from the active checkout and
raises `CURRENT_ACTIVE_SOURCE_DRIFT` when the current bytes differ. It handles
the frozen measurement separately: measurement-v8 stays bound to commit
`f35d341110c67377200ad353ab56a3cf38615a73` and its 36 historical Git objects.
Updating this current wrapper row therefore preserves the historical record;
substituting the historical wrapper digest is rejected by the focused mutation
tests.

The manifest contains 38 unique repository and view paths. Before this repair,
a read-only inventory found two current-byte mismatches. This patch changes only
the first:

| Active input | Manifest before | Current bytes | Disposition |
| --- | --- | --- | --- |
| `f017_corrected_oracle_secondary_wrapper_v11.py` | `97e640e…` | `77b3b473…` | Updated here; exact known CI failure. |
| `validate_f017_v11_execution_authority_v1.py` | `5a123ec8…` | `dec34ba2…` | Preserved for separate provenance review; outside this repair. |

The focused source-only tests use the real consumer's hash and failure helpers.
They reproduce the old wrapper failure, accept the corrected current binding,
and reject a wrong digest, wrong path, wrong role, historical substitution,
changed source bytes, a missing entry, and a duplicate entry. They do not open
checkpoint data, change runtime or numerical code, alter historical authority,
or claim full-forward or native qualification. Hosted exact-head CI remains the
authority for whether the formerly failing step advances and for any subsequent
independent mismatch.
