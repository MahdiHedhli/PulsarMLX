# F017 corrected-oracle numerical-authority supersession — Opus cycle 2 response

Reviewed exact bytes at `7fff686ab2a576230dcf23c8e43ca8e4d74c35fa` in a clean detached worktree.

Opus independently verified cycle-1 findings `F1`, `F2`, `F3`, `F7`, and `F8` closed. It exercised eight target-method injection vectors, 22 exact path/SHA mutation vectors, eleven provenance-audit mutations, a complete byte-identical 24-case requalification, and live target geometry/row-bound probes. All ten tombstones remained fail-closed, historical Git-byte reconstruction remained exact, and numerical formulas, thresholds, outputs, and independence were unchanged.

One `NON_BLOCKING_REQUIRED` finding remained:

`F5-R1`: the widened pure-core import denylist was still fail-open for alternative network, native, file, archive, serialization, and dynamic-import modules. Opus recommended an exact import allowlist matching the seven observed module families.

Two `DEFENSE_IN_DEPTH` observations remained: original-checkpoint-zero is structurally contained rather than measured, and the target graph guard matched names rather than an exact function/method census.

No finding required a formula change, threshold change, original-checkpoint access, or loss of primary/secondary independence.

Safety confirmed: Event 04 authorization absent; Event 04 unexecuted; original checkpoint access zero; primary/secondary real executions zero; P1 attempt 2 absent; historical master ledger 175.

`REJECT`
