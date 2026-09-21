# F017 numerical output interface — Gemini numerical CHALLENGE cycle 02

Cycle 01 was invalid because the reviewer searched unrelated repositories and
claimed the mounted target commit was absent. This cycle is bound to the
current detached worktree supplied by the caller.

Before analysis, run exactly:

```text
pwd
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --short
```

The required values are:

- HEAD: `7d1f014a97887f427d4664abe996a259d6817141`
- the implementation measurement inside the committed evidence binds head
  `858f2013829993a23508b673a4bbc1d6b8d6e243`, tree
  `0919de5f7142b5320e275edd57daa8948185db08`.

Do not search another checkout, sibling repository, remote, project cache, or
branch. Treat the current worktree as the complete committed review target.
If `git rev-parse HEAD` does not equal the required head, return only
`REVIEW_PROTOCOL_INVALID` with the observed cwd/head.

Review role: CHALLENGE, read-only. Independently attack:

- C-FORM-001/C-FORM-002 formula and operation-order equivalence;
- C-LEGACY-001/C-LEGACY-002 exact legacy API equivalence;
- C-BITS-001/C-BITS-002 immutable payload bit identity and SHA binding;
- C-OUT-001/C-OUT-002 and C-ONEEXEC-001: one graph execution yields all
  three outputs, without hidden normalization/projection recomputation;
- source-read census equivalence;
- C-PURITY-001 absence of callbacks, reflection, filesystem, checkpoint,
  subprocess, authorization, lifecycle, or dynamic-import capability;
- control-plane JSON rejection of payload buffers;
- C-INDEP-001 primary/secondary independence;
- C-QUAL-001 corpus adequacy and reproducibility;
- C-CI-001 exact-head FULL_NATIVE coverage and zero original-checkpoint access.

Inspect and run committed tests as needed. Never access original checkpoint
shards. Do not modify the worktree. Return strict JSON:

```json
{
  "reviewed_head":"...",
  "reviewed_tree":"...",
  "protocol":"VALID|INVALID",
  "blocking":[{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "non_blocking_required":[{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "defense_in_depth":[{"id":"...","claim_id":"...","attack":"...","evidence":"..."}],
  "claim_challenges":[{"claim_id":"...","status":"SUPPORTED|CHALLENGED","reason":"...","evidence":["..."]}],
  "unresolved_material_disagreement":false,
  "verdict":"CHALLENGES_ISSUED|NO_MATERIAL_CHALLENGES|REVIEW_PROTOCOL_INVALID"
}
```

Gemini is not the final arbiter.
