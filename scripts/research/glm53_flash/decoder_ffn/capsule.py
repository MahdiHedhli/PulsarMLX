def source_ffn_block(self, x: mx.array) -> mx.array:
    # Stateless FFN half (no cache) -> compiles cleanly at a fixed decode shape.
    residual = x
    xc, post, comb = self.ffn_hc(x)
    m = self.mlp(self.post_attention_layernorm(xc))
    return hc_expand(m, residual, post, comb)
