# F017 M1-E IQ3_XXS Decoder Adversarial Review

**Verdict: GO FOR FRESH M1-E ATTEMPT 2**

## Adversarial checks

1. The candidate decoded identity omitted by attempt 1 was independently
   reproduced; the review does not infer it from the failure.
2. The packed payload hash is unchanged and the same exact slice was supplied
   to all decoders.
3. Hashing order, shape, element count, endian, padding, transpose, signed
   zero, and NaN handling were eliminated as alternate causes before the
   implementation change.
4. The third decoder does not import the corrected Python functions, Rust,
   FFI, MLX, or candidate output. It agrees with the pinned upstream algorithm
   and with Rust.
5. The minimized fixture isolates the grid-order defect in one compressed
   block. Its expected f32 bits are source-controlled and content-hashed.
6. The mismatch distribution spans every real block rather than a tail,
   row-boundary, scale, codebook, or one-ULP subset; the declared root cause
   explains that distribution.
7. The correction is limited to Python logical ordering. Rust candidate
   decoding and all frozen M1-E tolerance semantics are unchanged.
8. Exact Python/Rust/spec identity holds on synthetic fixtures, the minimized
   block, selected real blocks, and the full authorized down payload.
9. Attempt 1 remains rejected and immutable. The corrected oracle is a new
   private decode-only artifact and does not retroactively qualify attempt 1.
10. All Python-IQ3-dependent historical claims are explicitly superseded
    pending rebank; M1-D is unaffected and M1-F remains blocked.

The fresh attempt-2 config is immutable, binds decoder v2 and attempt-1
evidence, and passed only the non-consuming preflight. A fresh execution is now
technically meaningful, but this review does not execute or promote it.
