# F017 numerical output interface — Gemini numerical CHALLENGE cycle 03

Cycles 01 and 02 were repository-mount protocol failures. This final numerical
cycle is run in a self-contained clone whose `.git` object database is inside
the supplied review directory.

First run `pwd`, `git rev-parse HEAD`, `git rev-parse HEAD^{tree}`, and
`git status --short`. Required review head:
`7d1f014a97887f427d4664abe996a259d6817141`. Do not inspect another checkout.
If identity fails, return `REVIEW_PROTOCOL_INVALID` only.

Review committed bytes read-only. The measured execution implementation is
head `858f2013829993a23508b673a4bbc1d6b8d6e243`, tree
`0919de5f7142b5320e275edd57daa8948185db08`, bound by the evidence descendant.
FULL_NATIVE run `32971168057` passed with zero required native skips.

Attack, claim by claim:

- C-FORM-001, C-FORM-002: numerical expressions and order versus V2;
- C-LEGACY-001, C-LEGACY-002: exact compatibility output;
- C-BITS-001, C-BITS-002: f64le/f32le bytes, immutability, hashes;
- C-OUT-001, C-OUT-002, C-ONEEXEC-001: exactly one graph run supplies hidden,
  normalized, and logits, with no hidden recomputation;
- C-PURITY-001: no callbacks, reflection, I/O, checkpoint, subprocess,
  lifecycle, authorization, or dynamic-import capability;
- C-INDEP-001: independent primary and secondary arithmetic;
- C-QUAL-001: corpus, source-read equivalence, reproducibility, zero checkpoint
  access;
- C-CI-001: exact-head CI actually executes these gates.

Also attack control-JSON leakage. Run safe committed tests if useful. Never open
original checkpoint shards. Do not edit.

Return strict JSON with reviewed_head, reviewed_tree, protocol, arrays
`blocking`, `non_blocking_required`, `defense_in_depth`, a `claim_challenges`
row for every claim above, boolean `unresolved_material_disagreement`, and
verdict `CHALLENGES_ISSUED`, `NO_MATERIAL_CHALLENGES`, or
`REVIEW_PROTOCOL_INVALID`. Each finding needs id, claim_id, attack, evidence.
Gemini is CHALLENGE only, not final arbiter.
