# F017 Event 06 V12-to-V11 Bridge — Whole-Domain Opus Arbitration, Cycle 02

Use `claude-opus-5` at high effort in a fresh detached read-only worktree.
Review committed bytes only. Do not edit files, resolve or inspect an original
checkpoint root, open a checkpoint shard, run numerical inference, create live
authority or state, consume an Event 06 identity, retry or resume Event 04, 05,
or 06, or execute P1 attempt 2.

## Authority under review

- repaired implementation head: `7fbc641339f65619f77cca78a86eabc4d19277b7`
- repaired implementation tree: `4ea92265360b7130948e52b8497f2802a7526702`
- repaired evidence and Gemini head: `83a463fd5bd526ad38f9731dea4c62be4864fb75`
- bridge digest: `b7f473d7066a3420170cb6fde73bdfd4955f1912d3d8977d9ca0b003c83c06cd`
- FULL_NATIVE run: `33141124246`, PASS, two required native jobs passed,
  required and unexpected native skips zero
- repaired evidence EVIDENCE_ONLY run: `33142278211`, PASS, native jobs zero
- Gemini-cycle-02 evidence EVIDENCE_ONLY run: `33143982465`, PASS, native jobs zero
- Gemini cycle-02 verdict: `ACCEPT_FOR_OPUS_WHOLE_DOMAIN_ARBITRATION`,
  11 supported, zero challenged, zero unresolved

The index-restoration artifact documents an external stale-index incident. The
request commit briefly deleted fourteen evidence paths while retaining their
bytes in the worktree; the following append-only corrective commit restored
the exact bytes. Verify the restored files byte-for-byte against
`8f943e67ffccd8b59c85f4bb05e00ed0fc18e943`, and do not treat the incident as
source drift.

## Mandatory reconstruction of cycle-01 rejection

Cycle 01 rejected `C-BRIDGE-PROV-001`, `C-BRIDGE-CALLPATH-001`,
`C-BRIDGE-LIFE-001`, and `C-BRIDGE-QUAL-001`. Reconstruct every finding and
prove or disprove the committed repair:

1. the production V12 `run_identity_stage` output crosses a real typed adapter
   into the sealed bridge authority;
2. the execution-plan digest is transitively bound through the event plan and
   installed V12 authority, and all source, measurement, numerical, result,
   identity-terminal, access-census, descriptor, and lease-owner provenance is
   validated;
3. package, primary, and secondary durable starts are coordinator-created
   sealed objects, with no caller-supplied start digest;
4. primary and secondary each execute once, and secondary binds the complete
   exact primary terminal;
5. comparison, release, accounting, V11 bundle closure, and package terminal
   form one implemented chain;
6. all success and modeled post-identity failure paths release the five leases
   exactly once without generic fallback;
7. qualification invokes the actual production coordinator and real consumer
   signatures with fail-closed spies, and rejects fourteen independently valid
   provenance substitutions.

## Required direct attacks

Repeat every cycle-01 direct attack, plus bridge-plan digest substitution,
identity-stage producer/report mismatch, package-owner substitution, sealed
start forgery, execution-result forgery, missing comparison/release/accounting
bindings, descriptor release failure, terminal closure mismatch, evidence
restoration mismatch, and CI/evidence-head mismatch.

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
