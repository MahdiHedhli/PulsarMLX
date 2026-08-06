# Plan: Pre-FFN residual capture

1. Prove graph boundary from pinned qwen3moe.cpp + GGUF KVs.
2. Capture `ffn_inp-0` via single-target CPU helper (existing residual_inp_capture).
3. Validate CPU RMSNorm against frozen F002 `ffn_norm-0` without regenerating it.
4. Publish raw evidence and claim F007-C01.
5. Keep F003/F004 closed; enable F005 residual composition.
