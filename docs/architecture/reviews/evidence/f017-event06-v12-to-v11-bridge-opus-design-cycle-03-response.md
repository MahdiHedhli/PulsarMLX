# F017 Event 06 V12→V11 Bridge — Opus Design Arbitration, Cycle 03

Contract V3 completely and unambiguously inherits the hash-bound V2 sections. FINDING-F is closed: the secondary view carries the complete primary terminal document, its three required prerequisite SHAs, and the bridge bundle binding; exact and negative calls through the unchanged primary-terminal gate pass and reject correctly. FINDING-G is closed: the comparison view carries the exact minimal `authorization_id` authority and substitutions reject.

All earlier findings were rechecked. Exact nine-field descriptors pass and the superseded census fails. Both source constructors accept the minimal three-key projection with six shard records and reject missing keys. The projection is not candidate-shaped. The ten-phase journal is acyclic, terminates at the zero genesis, and leaves V11 bytes untouched. Event/execution plan digests close both event IDs and the package. Lifecycle V3 covers durable package-start failures and descriptor release on every later terminal path. All seven views are closed and least-authority. Manifest V3 and all immutable runtime bindings reproduce with zero drift. Historical V11 and V12 admission remains closed. Fifty-two applicable historical tests pass.

## Claim verdicts

| Claim | Verdict | Invalidation disposition |
|---|---|---|
| `C-BRIDGE-GEN-001` | ACCEPT | Invalidate if V12 28/30 census changes or fake/union V11 candidate appears |
| `C-BRIDGE-PROV-001` | ACCEPT | Invalidate if a plan digest or equality edge is dropped |
| `C-BRIDGE-DIGEST-001` | ACCEPT | Invalidate on pre-primary self-reference or ambiguous journal provenance |
| `C-BRIDGE-LEGACY-001` | ACCEPT | Invalidate if a historical validator widens |
| `C-BRIDGE-CALLPATH-001` | ACCEPT | Invalidate on drift in unchanged sources, execute functions, or primary-terminal gate |
| `C-BRIDGE-LIFE-001` | ACCEPT | Invalidate on an unmodeled terminal path or unreleased descriptor |
| `C-BRIDGE-CAP-001` | ACCEPT | Invalidate if prohibited capability becomes reachable |
| `C-BRIDGE-DRIFT-001` | ACCEPT | Invalidate if any immutable runtime binding changes |

Eight accepted, zero rejected, zero unresolved; zero blocking, zero required, zero open findings.

`ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_DESIGN_FOR_IMPLEMENTATION`
