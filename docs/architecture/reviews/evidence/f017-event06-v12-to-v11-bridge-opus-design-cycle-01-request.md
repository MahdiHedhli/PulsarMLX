# F017 Event 06 V12-to-V11 numerical authority bridge — Opus design arbitration

Act as the final design ARBITER using claude-opus-5 at high effort in a fresh detached read-only checkout. Do not edit files and do not access checkpoint data.

Independently reconstruct the terminal parent failure and review the complete proposed bridge design at design repair head `af7b3674a649bd4289f6f4654998e1b7cb5de0f0`, including bridge contract V1, lifecycle V2, capability V1, design data model, producer-consumer matrix, no-access plan, Gemini cycles 1–2, support ledger, and claim ledger V2.

For every claim `C-BRIDGE-GEN-001`, `C-BRIDGE-PROV-001`, `C-BRIDGE-DIGEST-001`, `C-BRIDGE-LEGACY-001`, `C-BRIDGE-CALLPATH-001`, `C-BRIDGE-LIFE-001`, `C-BRIDGE-CAP-001`, and `C-BRIDGE-DRIFT-001`, return exactly one verdict: `ACCEPT`, `REJECT`, or `UNRESOLVED`, with direct evidence and invalidation disposition.

Directly attack generation laundering; fake or partial V11 candidates; mutable or ambient authority; incomplete source/identity/lease provenance; digest self-reference or missing closure; consumer view widening; legacy validator admission; coordinator signature gaps; package-start bypass; event-number capability branching; duplicate primary/secondary calls; secondary-before-primary; every failure prefix and descriptor-release path; reconstruction/replay; validation-only capability leakage; and V4/V11 drift.

End with exactly one global verdict: `ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_DESIGN_FOR_IMPLEMENTATION` or `REJECT`. No conditional acceptance. Acceptance requires every claim accepted and zero blocking, required, or unresolved findings.
