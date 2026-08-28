# F017 Event 06 V12→V11 Bridge — Opus Design Arbitration, Cycle 02

The exact nine-field descriptors pass the unchanged descriptor validator. The exact three-key source projection with six shard records constructs the unchanged primary descriptor source successfully, while passing it to the historical V11 candidate entry point still rejects as required. The ten-phase transition journal and V12 package terminal are acyclic and transitively bind one bridge digest without modifying V11 artifacts. Event identity closure, durable package-start outcomes, descriptor release, manifest V2, and all immutable runtime bindings pass.

## Residual findings

### FINDING-F — BLOCKING

Claims: `C-BRIDGE-CALLPATH-001`, `C-BRIDGE-DIGEST-001`.

The unchanged secondary `execute_and_bank` requires the complete primary terminal document, `primary_result_terminal_sha256`, `primary_receipt_sha256`, and `primary_manifest_sha256`. Those four values are absent from every consumer view. A terminal document digest cannot substitute for them.

### FINDING-G — REQUIRED

Claim: `C-BRIDGE-DIGEST-001`.

The unchanged independent comparison authority requires `authorization_id`, which is absent from `COMPARISON_V11`.

## Claim verdicts

| Claim | Verdict |
|---|---|
| `C-BRIDGE-GEN-001` | ACCEPT |
| `C-BRIDGE-PROV-001` | ACCEPT |
| `C-BRIDGE-DIGEST-001` | REJECT |
| `C-BRIDGE-LEGACY-001` | ACCEPT |
| `C-BRIDGE-CALLPATH-001` | REJECT |
| `C-BRIDGE-LIFE-001` | ACCEPT |
| `C-BRIDGE-CAP-001` | ACCEPT |
| `C-BRIDGE-DRIFT-001` | ACCEPT |

Six accepted, two rejected, zero unresolved; one blocking and one required finding.

`REJECT`
