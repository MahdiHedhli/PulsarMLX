# Synthetic affine partner shape regression

Local unpublished slice, 2026-10-16. No checkpoint payload, checkpoint Python,
MLX, model inference, or external reviewer was run. The Qwen worktree remains
at published head `d2d77047`; this addition awaits the applicable review.

`PageCatalog._triple()` required U32 packed weights, BF16 scales/biases,
positive row bytes and the expected first dimension, but admitted **different
scales and biases shapes** if both had valid byte spans. A synthetic gate
projection with scales `[experts, 2]` and biases `[experts, 1, 2]` therefore
passed catalog construction despite equal total BF16 bytes. The partner arrays
do not have the same tensor geometry. The new test first failed with
`CatalogError not raised`, demonstrating the gap. Catalog construction now
rejects `scales.shape != biases.shape` for every expert and PLE triple.

Focused synthetic validation after the change:

```text
test_qwen38_bounded_pager.py: 24 tests, OK
test_qwen38_verified_files.py: 14 tests, OK
test_qwen38_adapter_contract.py: 39 tests, OK
```

This check prevents a mismatched partner pair from entering the page catalog.
It does **not** prove the U32 packed-weight axis agrees with the per-module
bits/group size, that the pinned real checkpoint passes this new check, or
that the runtime's affine numerical convention is correct. Those remain
separate header/runtime and parity gates before a real model-data page test.

At a later read-only host observation, `memory_pressure -Q` reported 58%
system-wide free, but `top` reported only 393 MiB physically unused, 16 GiB
in the compressor and 63 GiB physically used; swap used was 26,965.25 MiB.
The 58% figure describes reclaimable pressure headroom, not a reservation.
The proposed tiny page-test preflight also requires 2 GiB physically unused,
bounded process RSS and MLX allocations, and stable swap counters. It was
**not met** at that observation. No page test was started.
