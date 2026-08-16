# F017 DPREFIX-REAL-2 Preparation Adversarial Review Packet

This packet requests one checkpoint-free decision. It does not release or
execute `DPREFIX-REAL-2`.

## Primary questions

1. Has the exact real-shape native defect been reproduced and fixed?
2. Will REAL-2 durably retain oracle primary products and all 40 packed inputs
   before a candidate failure can destroy them?
3. Has the exact candidate-failure trajectory already been rehearsed?

## Bound findings

- REAL-1 is terminal, consumed, and retry-ineligible.
- The first failing operation was `layer_0.attention.k_head_0` using
  `blk.0.attn_k_b.weight`.
- Predecessor geometry was matrix `[512,192]` with vector `[512]`; the correct
  semantic geometry is `[192,512]` with vector `[512]`.
- The first divergence was the candidate `attn_k_b` per-head import/orientation.
- The successor applies only that required stored-to-semantic transpose.
- All 27 dense-prefix contraction families across layers 0–2 are statically
  valid, and the exact-shape native rehearsal completed 10 deterministic
  repeats with 4,050 native matvecs, zero fallback, and zero backend errors.
- Oracle `layer_2_output` and `layer_3_entry` are fsynced and made read-only
  before candidate spawn.
- All 40 packed payloads are retained at acquisition and hard-gated against
  REAL-1 packed identities. Only the two banked Q4_K/Q6_K decoded identities
  are decoded hard gates; the other 38 are not invented.
- A deliberate candidate death preserved and rehashed both oracle Class-A
  products and the complete packed package, while lifecycle cleanup reached
  zero live state.
- REAL-2 plans exactly 40 reads and ledger `99 → 139`; no automatic retry or
  M1-F0 continuation exists.

## Required verdict

Return exactly one:

- `GO FOR ONE DPREFIX-REAL-2 REAL CAPTURE`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

Review performs zero checkpoint access.
