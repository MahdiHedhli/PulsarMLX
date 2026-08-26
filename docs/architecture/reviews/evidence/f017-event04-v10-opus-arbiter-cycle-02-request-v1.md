# F017 Event-04 V10 Opus ARBITER — Cycle 02

Review exact committed HEAD `f659a31d6820bbd646395f475fd3b83564042031` in a detached read-only worktree. Do not modify files, access original checkpoint shards, rerun Event 04, run either oracle, or mint/execute P1 attempt 2.

The one-shot package is terminal and non-replayable. It returned `ORACLE_EXECUTION_FAILURE`: primary completed 79 layers and wrote a 3,104,598-byte raw result; bounded decoding then rejected it because it exceeds both the 1,048,576-byte artifact limit and the 16,384-element array limit. No primary receipt/terminal was banked, secondary never started, comparison did not run, accounting is package 1 / primary 1 / secondary 0, all five leases were released, and historical ledger remains 175.

Cycle 1 reported 21 accepts and 7 rejects but emitted only 27 explicit verdict rows, omitting `E-RELEASE-001`. The builder did not silently accept it. Review the cycle-1 result, corrected claim census, phase-qualified lease statement, current graph bindings, terminal-result source/banked distinction, and EVIDENCE_ONLY run 32918434857.

Return one explicit verdict for each of the exact 28 claim IDs in claim-ledger-v7, including `E-RELEASE-001`; verify the seven unmet success claims remain rejected; verify no retry, no secondary execution, no comparison, no P1 authority, and historical ledger 175. Acceptance is of truthful failure evidence only and cannot imply successful completion or P1 readiness.

Required global verdict: `ACCEPT_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EVIDENCE` or `REJECT`. No conditional acceptance.
