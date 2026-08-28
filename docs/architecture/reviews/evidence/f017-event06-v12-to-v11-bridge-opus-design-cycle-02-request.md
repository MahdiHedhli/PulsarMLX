# F017 Event 06 V12-to-V11 bridge — Opus design arbitration cycle 2

Act as ARBITER using claude-opus-5 at high effort in a fresh detached read-only checkout. Review repair head `eb920e17debd37738db2539e910a34b5950cbf71`. Do not edit files and do not access checkpoint data.

Re-evaluate FINDING-A through FINDING-E and the manifest advisory against bridge contract V2, lifecycle V3, design V2, support ledger V2, claim ledger V3, and authority manifest V2. Execute safe in-memory counterexamples where useful.

In particular verify: exact nine-field descriptors pass the unchanged descriptor validator; the six-shard source projection satisfies the unchanged source constructor; adapters can call unchanged source plus `execute_and_bank` without candidate fabrication; event/execution plan digests close both event IDs; closed consumer view censuses are enforceable; V12 transition-binding journals provide transitive bridge closure without mutating any V11 artifact; the V12 package terminal is acyclic; durable-package-start failures have exact outcomes; and every acquired descriptor is released on every terminal path.

Return `ACCEPT`, `REJECT`, or `UNRESOLVED` with evidence and invalidation disposition for all eight bridge claims. End with exactly one global verdict: `ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_DESIGN_FOR_IMPLEMENTATION` or `REJECT`. No conditional acceptance.
