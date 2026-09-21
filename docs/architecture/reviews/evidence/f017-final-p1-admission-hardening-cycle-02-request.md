# PulsarMLX F017 final P1 admission hardening — independent cycle 2 review

Review committed bytes only at exact pushed commit
`33e394cd1f1b0022c538b817a87baa3cf22c1b42` on branch
`feat/017-rust-native-inference-runtime`, using this detached worktree read-only.
Do not edit. Do not execute P1, full-model inference, or read checkpoint payload.

Controlling exact-head GitHub Actions run: `32531735838`, conclusion success;
dedicated native job `96924935741`, workspace job `96924935985`. Inspect it.

Cycle 1 at `9760c156...` returned REJECT with:

- BLOCKING `F017-IR1-P1-001`: no committed exact contract instance and no
  committed identity-bound P1 executor capable of mechanically emitting the
  required execution receipt.
- NON_BLOCKING_REQUIRED `F017-IR1-P1-002`: a fresh attempt ID could execute a
  second P1 under the same reviewed contract.
- NON_BLOCKING_REQUIRED `F017-IR1-HIST-002`: stale final-CI record.
- DEFENSE_IN_DEPTH `F017-IR1-B1-002`, `F017-IR1-B1-003`,
  `F017-IR1-EDGE-002`, `F017-IR1-ORACLE-002`.

Cycle-2 changes:

- `claim_attempt` now creates a durable contract-wide `p1-once.claim.json`
  before the attempt directory; a new authorization and new attempt ID are
  rejected. The fixed state root is enforced and caller-selected alternate
  roots are rejected.
- checkpoint root must resolve exactly to the bound environment root; caller
  alternate roots fail.
- a permanent fresh-authorization/attempt mutation test was added.
- the CI handoff distinguishes historical implementation CI and exact repair
  implementation CI run `32530443531`; exact cycle-2 CI is run `32531735838`.

Independently rerun the critical review attacks:

1. remove actual native free while logical accounting remains;
2. exact B2 source-first/no-eval/no-sync callback timing;
3. free-memory observation bypass/staleness/caller claim;
4. same-authorization replay, fresh-authorization second P1, concurrent claim,
   alternate state root, mandatory-stop removal;
5. checkpoint/runtime/Git identity mutation and alternate checkpoint root;
6. missing accounting counter / unavailable stream ownership;
7. residual cancellation/signed zero and oracle independence;
8. exact-head pinned-native CI with zero qualification skips;
9. most importantly, re-evaluate `F017-IR1-P1-001`: determine whether this
   committed tree contains an exact validated contract instance and an
   identity-bound real bounded-P1 executor which mechanically snapshots all
   required counters and emits the receipt accepted by
   `scripts/research/f017_p1_admission.py`. Do not accept a placeholder or a
   gate that can only fail.

Severity: BLOCKING, NON_BLOCKING_REQUIRED, DEFENSE_IN_DEPTH. Both first two
prevent acceptance. For each finding give stable ID, exact path/symbol,
evidence, failure mode, repair, CI requirement, and oracle impact.

Return exactly one final verdict:

- `ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`
- `REJECT`

Do not authorize P1.
