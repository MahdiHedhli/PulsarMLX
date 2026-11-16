# Pinned pageable affine geometry regression

Local, unpublished synthetic/source check on 2026-10-16. No checkpoint tensor
payload, bundled model Python, full-model loader, inference, benchmark, or
external reviewer was run.

## Contract evidence

The installed MLX 0.32.0 `quantize`/`quantized_matmul` docstrings state that
affine values are packed from low to high bits into unsigned 32-bit words and
one scale/bias applies to each group of values in a row. A tiny generated CPU
shape observation confirmed:

```text
input (2, 3, 64), 4-bit/group-64 -> packed (2, 3, 8), scales/biases (2, 3, 1)
input (2, 64), 4-bit/group-32 -> packed (2, 8), scales/biases (2, 2)
```

Reading the pinned local `config.json` (metadata only) confirmed 128 exact
PLE shard overrides at 4-bit/group-32, no switch-MLP expert overrides, and
498 other overrides at 8-bit/group-64; the default is 4-bit/group-64. The
old admission checked only the aggregate override counts. It did not bind
the 4/32 overrides to PLE shard names or compare packed word count with the
number of affine groups.

## Gap and narrow repair

A synthetic catalog previously accepted eight packed U32 words (64 four-bit
values) with **two** scales/biases at group size 64 (metadata for 128 values).
The existing scales/biases equality check was satisfied. A new isolated
regression constructs valid expert and PLE triples, then changes one expert
pair's group count and proves the strict geometry check rejects it. A second
regression rejects a misplaced PLE override and an expert override. The
pinned `admit_checkpoint` path now requires:

- all 128 PLE override keys exactly identify PLE shards and remain 4/32;
- no expert-specific override changes the pinned 4/64 default;
- for every expert and PLE triple, packed and affine arrays have the same
  leading dimensions, and `packed_last * (32 / bits) == scales_last * group_size`.

The direct `PageCatalog` constructor remains usable for old synthetic
scheduler fixtures; the strict method is called by pinned checkpoint
admission. The bound-admission synthetic checkpoint fixture was updated to
valid 4/64 and 4/32 shapes. Focused results:

```text
test_qwen38_bounded_pager.py: 26 tests, OK
test_qwen38_verified_files.py: 14 tests, OK
test_qwen38_adapter_contract.py: 39 tests, OK
```

A header-only scan of the actual checkpoint was started to compare shapes,
but opening a shard stalled, so it was interrupted before completion. The
parser reads header bytes only; no tensor payload was intentionally read.
**The pinned real checkpoint has not passed this new strict gate.** Do not
advance to real page I/O until the actual headers are admitted when the host
can serve them promptly and the source change receives independent review.
This remains a layout gate, not numerical parity or norm-folding proof.
