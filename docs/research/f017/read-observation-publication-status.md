# Read-observation source publication

This feature-branch checkpoint publishes the **primary Python descriptor observer
and fixed synthetic qualification helpers only**. It is source publication, not
new scientific acceptance, an execution GO, a default-branch merge or a rerun.
The [model-target page](../../roadmap/MODEL_TARGETS.md) distinguishes the older
full-oracle reference from this narrower instrumentation work.

## Provenance and exact bytes

The source was reconstructed as data against public base
`c23e58ec87c7e73a23cf37ac64aa4dee6c45896f`, tree
`92cd4a53d36cae96a5aeb3485b00f157ae13e89e`.
The reconstructed primary tree is exactly
`25fa77eb4d4acabd443186b8d584ac9b7ad873e7`, matching measured source commit
`520f925c7acff5bec2b7b69dea7f624fc2d51235`.
The clean publication snapshot is
`1f49d767de96a6cc716fa074580dc2ac73733e3d` with that same tree. CI and documentation
commits through `443c7884eea3d6140f509466c29cf69e8c3fa9f6` preserve those bytes.
The table below is that historical publication checkpoint, not the relocated
successor described next.

Private source-recovery manifest SHA-256:
`c9bb69173cfcd9c6f8f49c9a59170ff66e028c58004280fd37c0ca5202949721`.
Private operational evidence and reviewer bodies are not published here.
The separately reconstructed historical evidence tree
`cfbd024d9cf30eb97f642fa186b9f05a2a4e30ab` was checked for custody but omitted from
the public snapshot. No historical helper or scientific executor was run to
reconstruct these trees.

| Repository-relative source path | SHA-256 |
| --- | --- |
| `scripts/research/f017_corrected_oracle_primary_target_source_v10.py` | `752fd55ba1ad641e3ab26b545e983a6bf798032d75a916e83e6c8fc2f701d28b` |
| `scripts/research/f017_corrected_oracle_primary_target_source_v11.py` | `2dec696bf2892928664780ba2438167c73ff579b47ad05ada48780355673b57e` |
| `scripts/research/f017_corrected_oracle_primary_wrapper_v11.py` | `515b23b0ac4fd382b9f4a75d01b4bbabe079020e17834347d6c1cfa2d7529133` |
| `scripts/research/f017_primary_read_observation_v1.py` | `f12b3908db48a51cd23ed564cd5da954cd08f8168a3a178a311cc3fd140e4e02` |
| `scripts/research/tests/f017_sequence54/README.md` | `9a34fc86e52b10abf89bf9db235f9d964c160779d41757e49d4e54ee8b757f7c` |
| `scripts/research/tests/f017_sequence54/observation_oracle54.py` | `31d1faa5d66e6c8e7d0f9f3b73342f25894f81b43750eaf288f103726582208c` |
| `scripts/research/tests/f017_sequence54/primary_cases54.py` | `b310fc410070730540a70a097bbe7c04569e9dc1518edf1ff8b3e3cb000a99f3` |
| `scripts/research/tests/f017_sequence54/primary_faults54.py` | `6e57f4cb858948d830bee3beda77186c937ef59967fc82807c14182c7005f7a7` |
| `scripts/research/tests/f017_sequence54/primary_suite54.py` | `cdadf472d197aff23d55e9cb678fff65180201e59ebd3476c72896344db967a3` |

## Historical/active placement repair

Hosted run [34307202519](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/34307202519)
at `443c7884eea3d6140f509466c29cf69e8c3fa9f6` exposed a historical-authority
placement defect: the instrumented implementation occupied the frozen V10
filename. This successor restores that filename to the exact historical base
bytes, moves the instrumented implementation byte-for-byte into an active
module, and makes the V11 factory import that module directly.

| Successor role | Repository-relative path | SHA-256 |
| --- | --- | --- |
| Historical V10, restored | `scripts/research/f017_corrected_oracle_primary_target_source_v10.py` | `ceab082d593a22fc30f76e67947b1819809edf0be488476f7affa326f5e744f4` |
| Active observed implementation, exact relocated bytes | `scripts/research/f017_primary_observed_descriptor_source_v1.py` | `752fd55ba1ad641e3ab26b545e983a6bf798032d75a916e83e6c8fc2f701d28b` |
| Active V11 factory | `scripts/research/f017_corrected_oracle_primary_target_source_v11.py` | `33e6473aff9ba468b0614d5f06261c8995bf4ac609f9b61e59c6238b9cd99f74` |
| Observer with successor filename census | `scripts/research/f017_primary_read_observation_v1.py` | `16165f7dfb1060d72d79545e9986d439229b80691f4cc34ccebf66661724d5ec` |
| Independent oracle with successor filename census | `scripts/research/tests/f017_sequence54/observation_oracle54.py` | `f3190ada6ab51a735bf4d97c5a7a0a1feb75ccedfaa46c086ba473dafdcb40ba` |
| Relocated fault-hook wiring | `scripts/research/tests/f017_sequence54/primary_faults54.py` | `6d16ce257ae60a7b2207774ad7c10ebb4def74384b93da01bd8a885db326a72c` |
| Confined integration checks | `scripts/research/tests/f017_primary_integration_cases.py` | `03ef0fcbe9a0687f1a9b5fd9407ab1ff5ef082e3128c5e3312488ecc7ff64711` |
| Unchanged historical/active validator | `scripts/research/validate_f017_v11_execution_authority_v1.py` | `5a123ec88b805df77d00be1f42a6e6f13dcb7c6c69b06f09deb102761872628c` |

The two independently owned measurement censuses each substitute exactly one
filename after completed review of the uncovered-active-file defect. Counter
formulas, oracle expectations, numerical formulas, wrapper behavior and
historical validator pins are unchanged. The new measurement digest is
`0cab94fd423f67d8e660e08a277d3ebeb54052c8abf8bcaacb5256913690cc8d`;
this is successor evidence, not a relabeling of the earlier measurement.

Current confined synthetic qualification passes the original 51 primary cases:
339 actual descriptor read calls, 4,372 requested bytes and 4,332 returned
bytes, including one error, two short returns (one zero-length). Baseline and
successor agree exactly on numerical output bits, routing captures, requests,
order, outcomes, counted prefixes and original stops. Fresh identity-bearing
hashes are validated independently, not asserted equal across roots.

Seventeen counter/durable-record mutations are rejected. Additional controls
exercise the unchanged historical validator against changed historical bytes,
detect changed active measurement bytes, reject an uninstrumented active
factory, and reject a missing active return observation. A separate fresh-root
process confirms the tiny wrapper and those active separation checks. Thirty-two
selected source call sites are mapped to passed cases; this is a scoped
source-to-test map, not a claim of complete runtime branch coverage.

Independent transcript comparison remains essential: a deliberately unbound,
uninstrumented substitute can otherwise produce a complete zero-read record.
The active-byte census and tested factory wiring are required separation
guards; this repair does not extend the observer to detect arbitrary substitute
callers. Counter mutations tested in memory are rejected by the independent
oracle; separate on-disk mutations exercise the producer's durable reader.

The fixed integration helper is
`scripts/research/tests/f017_primary_integration_cases.py`. Like the original
helpers, it requires the admitted confined loader; it is not a standalone or
unconfined discovery runner. The full-result banking refusal remains intact:
tiny numerical cases stop at `ResultEnvelopeError: numerical output payload
binding`. Full-result success, full geometry, secondary, native and physical
per-shard disk measurement are not qualified by this placement repair.

These local results do not claim hosted CI acceptance. The successor source
push must run the existing workflow normally; its exact commit/run outcome is
reported separately. No workflow, classifier, numerical contract or dependency
lockfile is changed by this placement repair.

## Qualification and omissions

The published observer records API intent, entry, return/error and a durable
prefix. It cannot turn an unavailable owner/suffix into zero observations.
Sequence 54's primary-prefix result is preserved; its full-geometry refusal is
not bypassed. The fixed helpers are **not standalone test runners**: their
[README](../../../scripts/research/tests/f017_sequence54/README.md) requires
confinement before production imports. Source publication does not authorize
running them unconfined.

| Scope | Disposition |
| --- | --- |
| Primary measured source and fixed helpers | Exact nine-file source checkpoint published |
| Secondary repository integration | **PENDING — not included** |
| Native / full-result / full-forward instrumentation qualification | **NOT_QUALIFIED** |
| Missing Sequence 43 numerical read/mapping/fault counts | **UNKNOWN_NO_BACKFILL** |
| Physical per-shard disk bytes and faults | **NOT_MEASURABLE_BY_CURRENT_METHOD** |
| Sequence 62 observer diagnostics | Private diagnostics, not production executor instrumentation |

The finite secondary recovery preserved 85 baseline/successor views. Of the 43
final successor views, 30 match this primary tree, four map to changed/new
secondary source files, and nine qualification helpers lack an explicitly bound
original repository integration. The final five-file measurement digest is
`8b0337366baac3c5035e7bcc0d1a655d24d34882217a8f56b754b7e234727756`;
it does **not** establish a complete shipping commit or tree. That integration
binding remains unknown. No secondary bytes were silently promoted or fabricated.

## CI routing

The accompanying bounded CI repair sends docs-only, evidence-only and mixed
docs/evidence changes to cheap applicable integrity checks. Evidence remains
append-only, regular-file, strictly decoded and semantically bound. Documentation
renames are checked as deletion plus addition; evidence renames remain prohibited.
Noncanonical paths fail closed. Source, contracts, fixtures, dependencies,
workflows and unknown paths retain native classification across the complete
base-to-head diff. The closed historical branch still rejects source changes.

The integrity summary schema is `pulsarmlx.ci.evidence-change-validation/2.0.0`:
`append_only` describes the whole changed-path set; `evidence_append_only`
describes the evidence subset. Head-side content is counted once for each added
or modified path, with no content bytes counted for deletion.

This genuine source/CI publication should launch the existing hosted synthetic
native workflow normally. It does not use skip-CI markers. Local CI-policy tests
are distinct from hosted native results; running, failed and unavailable CI are
not PASS. The repair is on this feature branch only, not a repository-wide or
default-branch deployment.

No checkpoint or retained Event 06 data was accessed for publication. No replay,
GO, P1 authority, native local build or historical-ledger change was performed.
Historical ledger: **175**.
