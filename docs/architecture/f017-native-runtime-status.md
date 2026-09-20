# F017 native GLM-5.2 runtime — current state

**This file is the current pointer for the native track.** Where an older
document or checklist in `docs/architecture/reviews/` describes a state before
the attempt-2 execution of 2026-09-20, that text is history: it is preserved
unchanged because those records are sha-bound, and this page supersedes it.

Machine-readable form: [`docs/glm52-native/native-runtime-summary.json`](../glm52-native/native-runtime-summary.json),
generated from the evidence records by
`scripts/research/generate_f017_native_status_v1.py` and checked in CI. Every
number below comes from that generator, not from transcription.

## What is done

| State | Result | Scope |
| --- | --- | --- |
| One token, real checkpoint | ✅ | Attempt 2 produced token **154820**, equal to the corrected oracle's expected token, and stopped. 1003.6 s: 704.0 s of shard identity rehash and 299.2 s for the 79-layer forward pass and logits. The authorization is consumed and can never be reused; nothing since has replayed it. |
| Checkpoint-free reconciliation | ✅ | Decoder differential 0 ULP over **107,502** values per seed across 11 quantisation formats; graph differential 6/6 against the corrected oracle. |
| Active source measurement / CI | ✅ | The V11 implementation measurement is repaired: v8 stays frozen and is re-verified against its own head, and an append-only v9 inventories the current head. 29 of 36 measured bodies are unchanged; 7 drifted in one accepted commit and are reviewed. |
| Multi-position temporal graph | ✅ synthetic | RoPE at nonzero positions, causal multi-key attention over the absorbed MLA latent, and a retained per-layer cache. 6/6 seeds against an independent binary64 reference on the MLX GPU backend: logits max abs 2.5e-8 … 1.5e-7 against frozen thresholds of 6.5e-3 / 3.5e-3 / cosine ≥ 1−1.9e-9, with selected token, expert selection and order, visible-key count and state growth exact. Plus 20 temporal tests covering causality, incremental-versus-recomputed prefixes, prefill chunking, A-B-A independence, reset, rollback and the refusal paths. |
| Multi-position decode, **real checkpoint** | ✅ | Stage A, 2026-09-20: eight teacher-forced positions against the real 222 GiB checkpoint with one retained state. **Position 0 reproduced the banked attempt-2 result bit for bit** — token **154820** and full-logits digest `db1456d8…`, both equal to the consumed one-shot's receipt. Retained state grew to exactly 1,456,128 bytes = 8 × 182,016, the figure the contract predicts. Positions 1-7 are recorded as measured, not qualified: no independent multi-token oracle exists for this checkpoint and the RoPE pairing is still a declared parameter. |
| Native text CLI | ✅ synthetic | `f017-native-generate` takes text and produces text with **no Python inference process**. 11 session tests and 12 CLI cases against a synthetic glm-dsa metadata shard and the repository's own identity records. |

## What is not done

| State | Status |
| --- | --- |
| Text generation on the real checkpoint | **In progress.** Stage A (teacher-forced positions) is done; the text stages are running under the same approval. |
| Performance baseline | **First real numbers, not a baseline.** Stage A: 716.6 s of checkpoint identity verification once per session, then 131.2 s for position 0 and 91.7-96.8 s for each of positions 1-7, 1501 s wall for the whole run. These are lower than attempt 2's 299.2 s forward pass because attempt 2 additionally banked 79 per-layer diagnostic records; the arithmetic is the same. No tokens-per-second figure is published: a teacher-forced ladder is not a decode rate. |
| The checkpoint's RoPE pairing | **Declared, not validated.** `NeoxHalfSplit` is the default and `Interleaved` the alternative; which one this GGUF conversion produced is a property of the checkpoint and is settled by the first approved multi-token run, not by assumption. |
| The sparse indexer | **Not implemented.** `glm-dsa` carries `blk.N.indexer.*` with `attention.indexer.top_k = 2048`. It is provably inert only while the whole sequence fits that budget, so the runtime refuses longer sequences rather than substituting dense attention beyond it. |
| Feature 017 formal closeout | **Pending the standing human approval.** Technical state and formal signoff are separate; no agent sentence replaces the signoff. |

## The supported invocation

```sh
cargo build -p f017-native --release --bin native_generate

./target/release/native_generate \
  --model /path/to/the/six-shard/checkpoint/root \
  --prompt "What is 17 times 6? Answer with the number only." \
  --max-tokens 8
```

The answer goes to stdout; one diagnostics JSON object goes to stderr, so
piping stdout yields exactly the model's text. Useful flags:
`--prompt-file` / `--prompt-stdin`, `--no-chat-template`, `--raw-tokens`
(a labelled diagnostic, not a text result), `--max-prompt-tokens`,
`--max-positions`, `--preflight-only` (identity, tokenizer and template with
no rehash), `--verify-only` (rehash then stop), `--cpu`.

Exit codes: `0` success, `2` usage or admission refusal, `3` identity or
verification failure, `4` runtime failure, `5` cancelled.

Bounds and behaviour are frozen in
[`f017-native-temporal-successor-contract-v1.json`](../../specs/017-rust-native-inference-runtime/contracts/f017-native-temporal-successor-contract-v1.json):
greedy only, lowest-token-id tie break, prompt + output must fit
`max_positions`, `max_positions` may not exceed the checkpoint's indexer
top-k, the identity rehash happens once per session and cannot be skipped,
and no decode rate is reported below two generated tokens.

The checkpoint root must contain exactly the six shards named in the manifest
and nothing else, must not be a symlink, and is opened read-only.

## What this runtime is and is not

It is a correct, bounded, stateful decoder with an honest interface. On the
real checkpoint it has demonstrated exactly one token. Everything multi-token
has been qualified on synthetic fixtures against an independent
implementation, which establishes that the state machinery, causality and
numerics are right — not that the real model produces good text, and not how
fast it runs.

Relationship to the frozen one-shot: the bounded-P1 admission contract is
terminal and consumed. This runtime is an explicit successor component. It
mints no authority, claims nothing under that contract, and leaves
`model.rs`, `executor.rs`, `contract.rs`, `loader.rs` and `bounded_p1.rs`
byte-identical; a test requires the temporal path at position 0 to reproduce
the one-token producer bit for bit.
