# F017 numerical output interface — Gemini numerical CHALLENGE cycle 01

Review role: CHALLENGE, read-only. Review committed bytes at exact head
`7d1f014a97887f427d4664abe996a259d6817141` on branch
`feat/017-rust-native-inference-runtime`.

The implementation authority is measured at
`858f2013829993a23508b673a4bbc1d6b8d6e243`, tree
`0919de5f7142b5320e275edd57daa8948185db08`. Exact-head FULL_NATIVE run
`32971168057` passed with required native skips 0. The evidence-only descendant
does not change execution bytes.

Independently attack these readiness-critical numerical claims:

- V2-to-V3 primary and secondary formula and operation-order equivalence;
- exact legacy API equivalence;
- immutable f64le/f32le payload bit identity and SHA binding;
- exactly one graph execution for final hidden, final normalized, and logits;
- absence of hidden final-normalization or output-projection recomputation;
- source-read census equivalence;
- absence of callbacks, reflection, filesystem, checkpoint, subprocess,
  authorization, lifecycle, or dynamic-import capability;
- control-plane JSON rejection of payload buffers;
- independence of primary and secondary numerical implementations;
- adequacy and reproducibility of the V4 requalification corpus;
- exact-head CI coverage and zero original-checkpoint access.

Inspect and run repository tests as needed. Do not access original checkpoint
shards. Do not modify the repository. Git and committed evidence control.

Return strict JSON with:

```json
{
  "reviewed_head": "...",
  "blocking": [{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "non_blocking_required": [{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "defense_in_depth": [{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "claim_challenges": [{"claim_id":"...","status":"SUPPORTED|CHALLENGED","reason":"...","evidence":["..."]}],
  "unresolved_material_disagreement": true,
  "verdict": "CHALLENGES_ISSUED|NO_MATERIAL_CHALLENGES"
}
```

Do not issue the final acceptance verdict; Opus is the arbiter.
