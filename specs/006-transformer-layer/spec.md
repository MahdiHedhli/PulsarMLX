# Feature Specification: Complete Transformer Layer-0 Output

**Created**: 2026-08-06  
**Status**: Architecture oracle verified (via F005); llama bit-parity rejected  
**Root cause**: Feature 008  

## Architecture form (verified)

```
l_out-0 ≡ ffn_inp-0 + MoE_architecture(ffn_norm-0)
```

where `MoE_architecture` is the independent Q8_0 **weight dequant × f32 activation**
path (F003–F005). Residual capture and RMSNorm link: F007.

## Llama fused form (not bit-equal)

llama.cpp uses ggml `mul_mat` with `vec_dot_type=Q8_0`, requantizing activations
to Q8_0. That path differs by ~3.4e-3 max_abs from the architecture oracle while
preserving top-8 IDs and ~0.99999 cosine.

Rejected llama bit-parity evidence retained under `raw/006-layer-out/`.
