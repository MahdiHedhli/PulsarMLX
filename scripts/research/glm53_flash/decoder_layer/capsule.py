class source_decoder_layer(nn.Module):

    def __init__(self, config: TextConfig, layer_idx: int):
        super().__init__()
        layer_type = config.layer_types[layer_idx]
        self.is_linear = layer_type == 'linear_attention'
        if self.is_linear:
            self.self_attn = Glm5NextLinearAttention(config)
        else:
            self.self_attn = Glm5NextSparseAttention(config)
        is_sparse = config.n_routed_experts is not None and layer_idx >= config.first_k_dense_replace and (config.mlp_layer_types[layer_idx] == 'sparse')
        self.mlp = Glm5NextMoE(config) if is_sparse else ClampedMLP(config)
        self.input_layernorm = nn.RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = nn.RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.attn_hc = HyperConnection(config)
        self.ffn_hc = HyperConnection(config)
        self.compile_ffn = True
        self._ffn_c = None

    def __call__(self, x: mx.array, mask: Optional[mx.array]=None, cache: Optional[Any]=None) -> mx.array:
        residual = x
        xc, post, comb = self.attn_hc(x)
        r = self.self_attn(self.input_layernorm(xc), mask, cache)
        x = hc_expand(r, residual, post, comb)
        if self.compile_ffn and x.shape[0] == 1 and (x.shape[1] == 1):
            if self._ffn_c is None:
                self._ffn_c = mx.compile(self._ffn_block)
            return self._ffn_c(x)
        return self._ffn_block(x)

    def _ffn_block(self, x: mx.array) -> mx.array:
        residual = x
        xc, post, comb = self.ffn_hc(x)
        m = self.mlp(self.post_attention_layernorm(xc))
        return hc_expand(m, residual, post, comb)
