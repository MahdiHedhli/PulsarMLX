# F017 Prepared M1-A/B Staged Handoff

> **Superseded for the next action:** use the narrower
> [`f017-m1-a-adapter-preflight-handoff.md`](f017-m1-a-adapter-preflight-handoff.md).
> M1-B remains separately gated after M1-A evidence review.

## Status

Prepared, not authorized. The independent review closed T017-161. M1-A remains
blocked until T017-160 closes with internal GO on the final head and a new
explicit operator prompt authorizes that stage.

## M1-A — adapter preflight only

M1-A may run only under a fresh explicit prompt. It uses
`--adapter-preflight-only`, the reviewed production environment manifest,
owned-device stream mode, the 16 GiB absolute memory floor, and a fresh output
path. It must not receive or open a checkpoint manifest. It must stop after
evidence validation and review.

Acceptance requires measured-host admission, exact loaded MLX native/C
identity, native tests without skip, zero starting state, synchronized adapter
exercise, reconciled teardown, zero fallback/error/reference/scaffold
dispatch, and an exclusively acquired evidence path.

## M1-B — checkpoint identity only

M1-B is not implied by an M1-A authorization. It requires a separate prompt
after M1-A evidence is reviewed. It may hash and parse only the canonical six
shards, GGUF headers/catalog, tokenizer identity, and complete production
`Glm52TensorMap`. It must not decode a tensor, create inference state or an
`MlxContext`, or execute any projection/expert/layer. Stop after M1-B evidence
validation and review.

## Still blocked

T017-140/R13, M1-C and later tensor boundaries, T017-141/P1 command
publication, P1, Feature 018 integration, and output-head residency remain
blocked. No command containing machine-local checkpoint paths is published in
this public handoff.
