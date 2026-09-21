class Glm5NextDecoderLayer(nn.Module):
    def __init__(self, config: TextConfig, layer_idx: int):
        super().__init__()
        layer_type = config.layer_types[layer_idx]
        self.is_linear = layer_type == "linear_attention"
        if self.is_linear:
            self.self_attn = Glm5NextLinearAttention(config)
        else:
            self.self_attn = Glm5NextSparseAttention(config)

        is_sparse = (
            config.n_routed_experts is not None
            and layer_idx >= config.first_k_dense_replace
            and config.mlp_layer_types[layer_idx] == "sparse"
        )
        self.mlp = Glm5NextMoE(config) if is_sparse else ClampedMLP(config)

        self.input_layernorm = nn.RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = nn.RMSNorm(
            config.hidden_size, eps=config.rms_norm_eps
        )
        self.attn_hc = HyperConnection(config)
        self.ffn_hc = HyperConnection(config)
        self.compile_ffn = True
        self._ffn_c = None

    def __call__(
        self,
        x: mx.array,
        mask: Optional[mx.array] = None,
        cache: Optional[Any] = None,
    ) -> mx.array:
        residual = x
        xc, post, comb = self.attn_hc(x)
        r = self.self_attn(self.input_layernorm(xc), mask, cache)
        x = hc_expand(r, residual, post, comb)
        # Compile the FFN block only for single-stream decode (B=1, S=1) -- the shape it
        # was validated on and where its win lives. Compiling the 288-expert MoE at a
        # batched or prefill shape spikes memory (it can OOM alongside the resident
        # weights), so those shapes take the eager path.
        if self.compile_ffn and x.shape[0] == 1 and x.shape[1] == 1:
            if self._ffn_c is None:
                self._ffn_c = mx.compile(self._ffn_block)
            return self._ffn_c(x)
        return self._ffn_block(x)

    def _ffn_block(self, x: mx.array) -> mx.array:
        # Stateless FFN half (no cache) -> compiles cleanly at a fixed decode shape.
        residual = x
        xc, post, comb = self.ffn_hc(x)
        m = self.mlp(self.post_attention_layernorm(xc))
        return hc_expand(m, residual, post, comb)


class Glm5NextModel(nn.Module):
    def __init__(self, config: TextConfig):
        super().__init__()
        self.config = config
        self.hc_mult = config.hc_mult
        self.vocab_size = config.vocab_size
        self.embed_tokens = nn.Embedding(config.vocab_size, config.hidden_size)
        self.layers = [
            Glm5NextDecoderLayer(config, idx) for idx in range(config.num_hidden_layers)
        ]
        self.norm = nn.RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.ssm_idx = next((i for i, l in enumerate(self.layers) if l.is_linear), 0)
        self.fa_idx = next((i for i, l in enumerate(self.layers) if not l.is_linear), 0)

    def __call__(
        self,
        inputs: mx.array,
        cache: Optional[Any] = None,
        inputs_embeds: Optional[mx.array] = None,
    ) -> mx.array:
        h = self.embed_tokens(inputs) if inputs_embeds is None else inputs_embeds

        if cache is None:
            cache = [None] * len(self.layers)

        fa_cache = cache[self.fa_idx]
        fa_mask = create_attention_mask(
            h, fa_cache[0] if fa_cache else None, return_array=True
        )
        ssm_mask = create_ssm_mask(h, cache[self.ssm_idx])

        h = mx.broadcast_to(
            h[:, :, None, :], (h.shape[0], h.shape[1], self.hc_mult, h.shape[2])
        )
        h = mx.contiguous(h)

        for layer, c in zip(self.layers, cache):
            mask = ssm_mask if layer.is_linear else fa_mask
            h = layer(h, mask=mask, cache=c)

        h = h.mean(axis=2)
        return self.norm(h)


class source_language_model(nn.Module):
    def __init__(self, args: TextConfig, config: ModelConfig = None):
        super().__init__()
        self.args = args
        self.config = args
        self.model_type = args.model_type
        self.model = Glm5NextModel(args)
        if not args.tie_word_embeddings:
            self.lm_head = nn.Linear(args.hidden_size, args.vocab_size, bias=False)

    def __call__(
        self,
        inputs: Optional[mx.array] = None,
        inputs_embeds: Optional[mx.array] = None,
        cache: Optional[Any] = None,
        mask: Optional[mx.array] = None,
        **kwargs,
    ) -> LanguageModelOutput:
        if inputs is None:
            inputs = kwargs.get("input_ids")
        out = self.model(inputs, cache=cache, inputs_embeds=inputs_embeds)
        # Only the last few positions' logits are ever needed for generation; slicing
        # before the (vocab-wide) projection skips it on discarded prefill positions.
        nlk = kwargs.get("num_logits_to_keep", 0)
        if nlk:
            out = out[:, -nlk:, :]
        if self.args.tie_word_embeddings:
            out = self.model.embed_tokens.as_linear(out)
        else:
            out = self.lm_head(out)
        return LanguageModelOutput(logits=out)

    def sanitize(self, weights):
        weights = {k: v for k, v in weights.items() if "mtp." not in k}
        weights = DSV32Model.sanitize(self, weights)

        remapped = {}
        conv_parts = {}
        fg_parts = ("A_log", "dt_bias", "f_a_proj.weight", "f_b_proj.weight")
        for k, v in weights.items():
            nk = k.replace(".hc_attn_", ".attn_hc.").replace(".hc_ffn_", ".ffn_hc.")

            fused = False
            for part in ("q_conv1d.weight", "k_conv1d.weight", "v_conv1d.weight"):
                suffix = ".self_attn." + part
                if nk.endswith(suffix):
                    prefix = nk[: -len(part)]
                    conv_parts.setdefault(prefix, {})[part[0]] = v
                    fused = True
                    break
            if fused:
                continue

            for p in fg_parts:
                suffix = ".self_attn." + p
                if nk.endswith(suffix):
                    nk = nk[: -len(p)] + "forget_gate." + p
                    break

            remapped[nk] = v

        for prefix, parts in conv_parts.items():
            if all(c in parts for c in ("q", "k", "v")):
                remapped[prefix + "conv1d.weight"] = mx.concatenate(
                    [parts["q"], parts["k"], parts["v"]], axis=0
                )
            else:
                for c, w in parts.items():
                    remapped[prefix + c + "_conv1d.weight"] = w

        weights = remapped
        for k, v in list(weights.items()):
            if "conv1d.weight" in k and v.ndim == 3 and v.shape[-1] != 1:
                weights[k] = v.moveaxis(2, 1)
            if k.endswith(self.FP32_SUFFIXES) and v.dtype != mx.float32:
                weights[k] = v.astype(mx.float32)
        return weights

    @property
    def layers(self):
        return self.model.layers

    # Kept in float32, as the reference does (`_keep_in_fp32_modules_strict`): the mHC scalars —
    # whose Metal kernel reinterprets `base` as float4 and reads garbage if it is bf16 — and the
    # KDA decay parameters. `cast_predicate` protects them at conversion time, `sanitize` heals
    # checkpoints that were already cast.
    FP32_SUFFIXES = ("_hc.base", "_hc.scale", "forget_gate.A_log", "forget_gate.dt_bias", "e_score_correction_bias")

    @property
    def cast_predicate(self):
        def predicate(k):
            return not k.endswith(self.FP32_SUFFIXES)

        return predicate

    @property
    def quant_predicate(self):
        def predicate(path, _):
            if (
                path.endswith("mlp.gate")
                or "e_score_correction_bias" in path
                or ".indexer" in path
            ):
                return {"group_size": 64, "bits": 8}
            return True

        return predicate

    def make_cache(self):
        caches = []
        for layer in self.layers:
            if layer.is_linear:
                caches.append(ArraysCache(size=2))
            else:
                caches.append(CacheList(KVCache(), KVCache()))
        return caches
