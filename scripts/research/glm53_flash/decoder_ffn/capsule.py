"""The retained decoder caller body, adapted only by name for explicit execution."""

def source_ffn_block(self, x):
    residual = x
    xc, post, comb = self.ffn_hc(x)
    m = self.mlp(self.post_attention_layernorm(xc))
    return hc_expand(m, residual, post, comb)
