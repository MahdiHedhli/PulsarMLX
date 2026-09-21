# F017 Event 06 V12-to-V11 Bridge — Whole-Domain Opus Arbitration, Cycle 03

Use `claude-opus-5` at high effort in a fresh detached read-only worktree.
Review committed bytes only. Do not edit files, resolve or inspect an original
checkpoint root, open a checkpoint shard, run numerical inference, create live
authority or state, consume an Event 06 identity, retry or resume Event 04, 05,
or 06, or execute P1 attempt 2.

## Authority under review

- repaired implementation head: `7fbc641339f65619f77cca78a86eabc4d19277b7`
- repaired implementation tree: `4ea92265360b7130948e52b8497f2802a7526702`
- CI-evidence repair head: `a30c26c3843ad43fc4b1b01bd76b9ac33e535ed6`
- CI-evidence repair tree: `bb54f8cc87f470ea275b20a7c8935fce1d61ff02`
- bridge digest: `b7f473d7066a3420170cb6fde73bdfd4955f1912d3d8977d9ca0b003c83c06cd`
- exact-head FULL_NATIVE run: `33141124246`, PASS, both required native
  jobs passed, required and unexpected native skips zero
- exact CI-evidence-repair EVIDENCE_ONLY run: `33144909934`, PASS, evidence
  integrity PASS, native jobs zero
- committed CI history:
  `docs/architecture/reviews/evidence/f017-event06-v12-to-v11-bridge-evidence-only-ci-history-v1.json`,
  SHA-256 `8cd387163e4854ea8d0f57d61d29ccac42ea6c0920fb16c98c73c92b436bde69`
- committed authority manifest:
  `docs/architecture/reviews/evidence/f017-event06-v12-to-v11-bridge-authority-manifest-v3.json`,
  SHA-256 `d2d40e2088cedcf8f3f596f4c8383ac8191808d1a150a02ae889c1d69cc1b650`

## Mandatory reconstruction of cycle-02 disposition

Cycle 02 accepted ten of eleven readiness-critical claims and left only
`C-BRIDGE-CI-001` unresolved. Its exact finding was that the reviewed committed
packet did not include a durable EVIDENCE_ONLY CI result artifact and the
authority manifest did not bind that artifact. Reconstruct that finding from:

- `f017-event06-v12-to-v11-bridge-opus-whole-domain-cycle-02-response.md`
- `f017-event06-v12-to-v11-bridge-opus-whole-domain-cycle-02-normalized-result.json`

Then verify the append-only repair:

1. the CI-history artifact records the authoritative PASS runs and the
   non-authoritative transient index-incident failure truthfully;
2. the authority-manifest successor binds that CI-history artifact by exact
   path and SHA;
3. run `33144909934` is for the exact CI-evidence repair head, passed evidence
   integrity, and launched zero native jobs;
4. no execution byte changed after implementation head `7fbc6413...`;
5. the restoration artifact and exact restored bytes preserve append-only
   evidence continuity.

## Required direct attacks

Reverify all cycle-02 attacks, with emphasis on forged CI run IDs, wrong heads,
native jobs hidden behind evidence-only classification, omission of the failed
index-incident run, manifest substitution, source drift after FULL_NATIVE,
restoration mismatch, original checkpoint access, live Event 06 authority,
Event 06 execution, and hidden P1 attempt-2 authority.

You may run only bounded synthetic or static validation that cannot resolve
checkpoint roots, access checkpoint bytes, execute numerical cores, install
authority, create durable live state, or consume identities.

## Claim decisions

Issue exactly one `ACCEPT`, `REJECT`, or `UNRESOLVED`, with committed evidence,
for every claim:

- `C-BRIDGE-GEN-001`
- `C-BRIDGE-PROV-001`
- `C-BRIDGE-DIGEST-001`
- `C-BRIDGE-LEGACY-001`
- `C-BRIDGE-CALLPATH-001`
- `C-BRIDGE-LIFE-001`
- `C-BRIDGE-CAP-001`
- `C-BRIDGE-DRIFT-001`
- `C-BRIDGE-QUAL-001`
- `C-BRIDGE-CI-001`
- `C-BRIDGE-SAFETY-001`

Report blocking, required, and unresolved counts. No conditional acceptance.

If and only if all eleven claims are `ACCEPT`, all three finding counts are
zero, and a fresh Event 06 production-shaped no-access GO boundary is
defensible, end exactly with:

`ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_AND_READINESS`

Otherwise end exactly with `REJECT` and identify the smallest rejected or
unresolved claim.
