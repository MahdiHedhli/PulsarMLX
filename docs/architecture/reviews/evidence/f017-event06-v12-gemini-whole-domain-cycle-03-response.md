# F017 Event 06 V12 checkpoint-identity authority whole-domain CHALLENGE cycle 3

Reviewed exact committed bytes only in a detached read-only clone.

Initial repository state:

- `pwd`: `/private/tmp/f017-gemini3.6G8RDI/repo`
- `git rev-parse HEAD`: `e9f6b1323a21a5981e50e549c537a882f10cf9df`
- `git rev-parse HEAD^{tree}`: `2658a1b66b3a963409523334d0f8cb2ac8433e8e`
- `git status --short`: clean

The repair implemented at `45647e1aadbe646e8d274ed2af8bc08ee2c2ed8b` successfully closes the three rejected findings from Opus cycle 1:

- `C-SCOPE-002` and `C-VALIDATE-002`: the installed authority is generated and validated against an `installed_expected` dictionary that maps all non-schema fields of the candidate authority, closing splice freedom.
- `C-FAIL-003`: capability and producer-measurement drift validations explicitly raise `F017_V12_IDENTITY_CAPABILITY_DRIFT` and `F017_V12_IDENTITY_PRODUCER_MEASUREMENT_DRIFT`, providing live raise sites without generic fallback.

The lifecycle outcomes contract models and maps these failure transitions. The remaining challenge is evidence indexing: append-only run `33115885569` and failed runs `33112357172` and `33112777151` were not represented by committed CI-history artifacts.

| Claim ID | Disposition | Attack and exact committed evidence |
| --- | --- | --- |
| `C-SCOPE-001` | `SUPPORTED` | Verified typed scope model and event-number exclusion in `f017_checkpoint_identity_authority_v12.py` and `f017_checkpoint_identity_capability_v12.py`. |
| `C-SCOPE-002` | `SUPPORTED` | Verified exact installed projection through `installed_expected`. |
| `C-INTERFACE-001` | `SUPPORTED` | Verified `f017-v12-checkpoint-identity-implementation-measurement-v3.json`. |
| `C-VALIDATE-001` | `SUPPORTED` | Verified candidate triple validation in instantiability v4. |
| `C-VALIDATE-002` | `SUPPORTED` | Verified installed field-for-field candidate comparison. |
| `C-VALIDATE-003` | `SUPPORTED` | Verified package-start gate ordering. |
| `C-RUNTIME-001` | `SUPPORTED` | Verified stale report and binding mutations in synthetic qualification v4. |
| `C-RUNTIME-002` | `SUPPORTED` | Verified six-shard synthetic terminal closure. |
| `C-FAIL-001` | `SUPPORTED` | Verified modeled lifecycle outcomes and generic-fallback prohibition. |
| `C-FAIL-002` | `SUPPORTED` | Verified exact transitions, deltas, prefixes, release duties, and terminals. |
| `C-FAIL-003` | `SUPPORTED` | Verified both drift live raise sites. |
| `C-HIST-001` | `CHALLENGED` | Failed CI runs were not committed as an evidence-history census. |
| `C-SYN-001` | `SUPPORTED` | Verified synthetic and failure qualification v4. |
| `C-NOACCESS-001` | `SUPPORTED` | Verified rehearsal v5. |
| `C-CI-001` | `CHALLENGED` | FULL_NATIVE v2 present; clean evidence-only run lacked a committed artifact. |
| `C-GO-001` | `UNRESOLVED` | Dependent on `C-HIST-001` and `C-CI-001`. |

Counts:

- supported claims: 13
- challenged claims: 2
- unresolved claims: 1
- material challenges: 2
- blocking findings: 2
- non-blocking-required findings: 0
- unresolved findings: 1

Global disposition: `MATERIAL_CHALLENGE`.
