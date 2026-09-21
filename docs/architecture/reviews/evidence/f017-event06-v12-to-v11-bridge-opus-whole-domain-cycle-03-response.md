All verification complete. The workflow change is purely additive — it
strengthens the FULL_NATIVE gate rather than weakening it.

I did not write a plan file: the task under review forbids editing files, and
this is a read-only arbitration whose deliverable is the verdict itself.

# F017 Event 06 V12→V11 Bridge — Opus Whole-Domain Arbitration, Cycle 03

## Authority verification

| Item | Result |
|---|---|
| impl head `7fbc6413` → tree `4ea92265` | exact |
| CI-repair head `a30c26c3` → tree `bb54f8cc` | exact |
| ancestry impl → repair → HEAD | linear, no rewrite |
| bridge digest `b7f473d7…c06cd` | **independently reproduced by fresh execution**, 42 fields |
| ci-history SHA `8cd38716…` / manifest-v3 SHA `d2d40e20…` | both exact |
| manifest v3 bindings | **11/11 byte-exact** |
| measured impl paths | **28/28** exact at impl head *and* HEAD |

## Cycle-02 reconstruction

Reproduced exactly: 10 ACCEPT, `C-BRIDGE-CI-001` **UNRESOLVED**, blocking 0 /
required 1 / unresolved 1, verdict REJECT. Request and response digests are
self-consistent. The finding was that the EVIDENCE_ONLY half of CI-001 had
**no committed artifact at all** and no manifest binding — runs named only as
prose in the document under review.

## The five repair checks

1. **CI-history truthful.** The 5 recorded runs map one-to-one, in order, onto
   exactly the 5 commits in `7fbc6413..02b8668c` — no room for insertion or
   omission. I re-ran the committed validator
   (`scripts.ci.validate_evidence_change`) on every head and reproduced each
   recorded outcome, including the incident run at `7aca5e2b` failing with the
   exact recorded taxonomy (`immutable evidence must be append-only, got D:`).
   It is preserved with `authority: false`.
2. **Manifest binds by exact path and SHA.** `manifest-v3` binds
   `…evidence-only-ci-history-v1.json` → `8cd38716…`, verified byte-exact. Chain
   v1→v2→v3 intact; v2 carried **no** `evidence_only_run` field, confirming the
   repair is precisely scoped to the finding.
3. **Run `33144909934`.** Head is the exact CI-repair head ✓. Evidence integrity
   **PASS — independently reproduced** ✓. Zero native jobs ✓ (structurally:
   `a30c26c3` classifies EVIDENCE_ONLY). The run *ID* appears only as prose — see
   adjudication below.
4. **Zero execution-byte drift after `7fbc6413`:** 28 additions, all under
   `docs/`; 0 modifications, 0 deletions.
5. **Restoration exact:** 14/14 paths byte-identical across `8f943e67` ≡
   `02ed1c53` ≡ HEAD; no force-push, no rewrite.

## Direct attacks — all fail closed

**Native jobs hidden behind evidence-only classification** is defeated
structurally: `classify_ci_change.py` routes evidence-mixed-with-docs →
FULL_NATIVE, unknown → UNKNOWN_DEFAULT_FULL, and raises on any manual `evidence`
override of a non-evidence diff; native jobs are gated on FULL_NATIVE/UNKNOWN
only. I reproduced the mode for all 8 heads — every evidence head EVIDENCE_ONLY,
`7fbc6413` FULL_NATIVE. The CI tooling itself was **never touched** by the bridge
work, and the sole workflow change is a purely *additive* assertion gate.
Manifest substitution fails on 11/11 SHAs — and the repair banks cycle-02's own
REJECT against itself. Checkpoint access, live authority, Event 06 execution,
and P1 attempt-2 all measure zero across five freshly executed qualifiers
(`p1_attempt_2_executed: false`; no attempt-02 artifact exists). Banked vs.
fresh qualification: **31 shared fields, 0 disagreements**. Live: 20 fresh
processes → 1 digest, 395 mutations and 14 provenance substitutions rejected,
0 unexpected passes, **12/12 tests pass**, 0 capability violations, 38/38
unique failure outcomes, historical V4/V11/V12 drift 0 from the starting head.

## Adjudication of `C-BRIDGE-CI-001` — ACCEPT

The residual — an opaque run-ID integer — has **identical epistemic status to
`33141124246`**, which cycle 02 accepted; holding the EVIDENCE_ONLY half to a
stricter standard would be inconsistent. Further, `33144909934` is not in the
claim's satisfaction set: the claim requires a *final manifest-bound* pass, and
the manifest binds `33144107149` at `02b8668c` — the maximum bankable head,
since no commit can bank its own CI result. That one-commit lag is the domain's
established convention (`…v12-evidence-only-ci-history-v1…v7`, where v7 banks
`0b0c774a` the same way). Any stricter reading makes the claim unsatisfiable by
infinite regress. Cycle 02 held the claim unadjudicable because nothing durable
asserted it; every substantive assertion is now durable, manifest-bound, and
reproducible from committed bytes by the committed CI tooling itself.

## Claim decisions

`C-BRIDGE-GEN-001` **ACCEPT** · `C-BRIDGE-PROV-001` **ACCEPT** ·
`C-BRIDGE-DIGEST-001` **ACCEPT** · `C-BRIDGE-LEGACY-001` **ACCEPT** ·
`C-BRIDGE-CALLPATH-001` **ACCEPT** · `C-BRIDGE-LIFE-001` **ACCEPT** ·
`C-BRIDGE-CAP-001` **ACCEPT** · `C-BRIDGE-DRIFT-001` **ACCEPT** ·
`C-BRIDGE-QUAL-001` **ACCEPT** · `C-BRIDGE-CI-001` **ACCEPT** ·
`C-BRIDGE-SAFETY-001` **ACCEPT**

**Blocking: 0. Required: 0. Unresolved: 0.**

Cycle-02's non-blocking observation 3 (qualification schema field-naming
variance) is confirmed as presentation-layer only — every shared field agrees
exactly, and the fields the banked record omits are corroborated elsewhere. Not
counted.

The GO boundary is defensible: a fresh production-shaped no-access rehearsal
passes with every checkpoint, numerical, state, authority, and
identity-consumption counter at zero.

ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_AND_READINESS
