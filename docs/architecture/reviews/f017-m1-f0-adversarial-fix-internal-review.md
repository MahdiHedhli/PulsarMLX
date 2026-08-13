# F017 M1-F0 Adversarial-Fix Internal Review

## Review boundary

This review is limited to the two required adversarial fixes and their
downstream hardening. It does not authorize or execute M1-F0 or M1-F.

- reviewed starting head: `1c80f6419112f3410cdb26e3294a8610c31a9c22`
- runtime semantic boundary: `7e4c3f37049444443164964aea2fc630752d17ce`
- exact tooling/config content commit: `7d7b972ce541ca1f62fad5269283249510ff67e8`
- rebuilt execution-config SHA-256: `444ab5d0c0c763ee6af52d8b3a8859e1edcfa17dd8609e03551a554f6cfd8a3f`
- accepted M1-E evidence: `0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9`

## Findings

1. **Config self-consistency:** closed. The validator resolves the declared
   tooling commit, requires it to be an ancestor, verifies its tree object,
   and compares every execution-controlling artifact with the bytes at that
   exact commit. Parent, descendant, unrelated, and stale fixture/config
   identities fail closed.
2. **Pinned input regeneration:** closed. A fresh CPython 3.13.13 / NumPy
   2.4.5 / PCG64 / seed 17017006 run reproduced the committed fixture and
   package byte-for-byte. No metadata was hand-edited.
3. **Real-byte Q5_K truth:** closed. The one authorized
   `blk.3.attn_output.weight` payload was decoded by the existing scalar
   oracle and an independent vector transcription of the pinned upstream
   Q5_K layout. All 100,663,296 little-endian f32 elements were bit-identical.
4. **Mandatory Q5_K admission:** closed. M1-F0 config, decoder contract, and
   validator directly bind the real-byte qualification evidence, the decoder
   sources, and `m1f0-q5-k-exact-v1`.
5. **Route-to-layer binding:** closed. The strengthened route schema binds the
   original input package, attention normalized input, attention output,
   attention residual, router normalized input, router scores, IDs, and
   weights. M1-F must carry the exact M1-F0 residual and must qualify any
   recomputed residual while retaining the frozen route IDs.
6. **Future quantization:** closed. A first-real-use policy requires exact
   real-byte independent cross-qualification before a new quantization family
   can freeze downstream F017 numerical evidence.
7. **Scope:** preserved. The remediation read one Q5_K tensor payload once.
   It performed no attention, router, route discovery, expert, or MLX
   candidate computation. M1-F0 remains unconsumed and unauthorized.

## Validation reviewed

- exact pinned input regeneration and byte comparison: PASS
- real-byte Q5_K two-decoder identity: PASS
- Q5_K block-pattern regressions: PASS
- M1-F0 config/preflight and stale-head negatives: PASS
- 10-repeat synthetic M1-F0 and six stress families: PASS
- route schema and historical-route rejection: PASS
- expert/tensor access rejection: PASS
- full Python research suite: 463 PASS
- `cargo check --workspace --all-targets`: PASS
- `cargo test --workspace --no-fail-fast`: PASS
- package duplicate-key/privacy/generated-artifact validation: PASS
- M1-E, M1-D, identity, and loader regressions: PASS

No threshold or frozen numerical contract changed.

## Verdict

GO FOR M1-F0 ADVERSARIAL DELTA REVIEW

