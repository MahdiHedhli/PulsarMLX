class Glm5NextIndexer(nn.Module):
    def __init__(self, args: TextConfig):
        super().__init__()
        self.dim = args.hidden_size
        self.n_heads = args.index_n_heads
        self.head_dim = args.index_head_dim
        self.index_topk = args.index_topk
        self.index_kpool = args.index_kpool
        self.index_kpool_always_select_tail = args.index_kpool_always_select_tail
        self.q_lora_rank = args.q_lora_rank
        self.wq_b = nn.Linear(
            self.q_lora_rank, self.n_heads * self.head_dim, bias=False
        )
        self.wk = nn.Linear(self.dim, self.head_dim, bias=False)
        self.k_norm = nn.LayerNorm(self.head_dim, eps=1e-6)
        self.weights_proj = nn.Linear(self.dim, self.n_heads, bias=False)
        self.softmax_scale = self.head_dim**-0.5
        self.index_kpool_compress_ape = mx.zeros((self.index_kpool, self.head_dim))
        self.index_kpool_compress_gate = mx.zeros((self.head_dim, self.dim))

    def _pooled_states(self, keys, gate_scores, valid):
        B, S, hd = keys.shape
        kp = self.index_kpool
        P = (S + kp - 1) // kp
        any_valid = mx.any(valid, axis=-1)
        first_key = mx.where(
            any_valid, mx.argmax(valid.astype(mx.int32), axis=-1), mx.array(S)
        )
        pool_offsets = mx.arange(P * kp).reshape(1, P, kp)
        pool_indices = first_key[:, None, None] + pool_offsets
        safe = mx.clip(pool_indices, 0, S - 1)
        flat = safe.reshape(B, P * kp)
        idxC = mx.broadcast_to(flat[..., None], (B, P * kp, hd))
        grouped_keys = mx.take_along_axis(keys, idxC, axis=1).reshape(B, P, kp, hd)
        grouped_gate = mx.take_along_axis(gate_scores, idxC, axis=1).reshape(
            B, P, kp, hd
        )
        grouped_valid = (
            mx.take_along_axis(valid.astype(mx.int32), flat, axis=1).reshape(B, P, kp)
            > 0
        )
        grouped_valid = grouped_valid & (pool_indices < S)
        pool_valid = mx.all(grouped_valid, axis=-1)
        pool_indices = mx.where(grouped_valid, pool_indices, -1)
        logits = grouped_gate + self.index_kpool_compress_ape[None, None]
        logits = mx.where(grouped_valid[..., None], logits, -1e30)
        probs = mx.softmax(logits, axis=2)
        probs = mx.where(mx.isnan(probs), 0.0, probs)
        pool_keys = mx.sum(probs * grouped_keys, axis=2)
        return pool_keys, pool_indices, pool_valid

    def _visible_tail(self, visible, valid):
        B, S, Kv = visible.shape
        kp = self.index_kpool
        mtw = kp - 1
        any_valid = mx.any(valid, axis=-1)
        first_key = mx.where(
            any_valid, mx.argmax(valid.astype(mx.int32), axis=-1), mx.array(Kv)
        )
        visible_count = mx.sum(visible.astype(mx.int32), axis=-1)
        tail_count = visible_count - (visible_count // kp) * kp
        tail_offsets = mx.arange(mtw)
        tail_start = first_key[:, None] + visible_count - tail_count
        tail_indices = tail_start[..., None] + tail_offsets
        tail_valid = (tail_offsets[None, None, :] < tail_count[..., None]) & (
            tail_indices < Kv
        )
        kv_idx = mx.clip(tail_indices, 0, Kv - 1)
        tail_vis = mx.take_along_axis(visible, kv_idx, axis=-1)
        tail_indices = mx.where(tail_valid & tail_vis, tail_indices, -1)
        return tail_indices

    def __call__(self, x, qr, mask, cache=None):
        B, S, _ = x.shape
        q = self.wq_b(qr).reshape(B, S, self.n_heads, self.head_dim)
        k = self.k_norm(self.wk(x)).reshape(B, S, self.head_dim)
        gate_scores = x @ self.index_kpool_compress_gate.swapaxes(-1, -2)

        if mask is not None and mask.dtype == mx.bool_ and mask.shape == (B, S):
            valid_cur = mask
        else:
            valid_cur = mx.ones((B, S), dtype=mx.bool_)

        # Pack per-token state and append to the indexer cache so pooling/selection
        # run over the full cached sequence -- unifies prefill and incremental decode.
        packed = mx.concatenate(
            [k, gate_scores, valid_cur.astype(k.dtype)[..., None]], axis=-1
        )
        if cache is not None:
            keys, _ = cache.update_and_fetch(packed[:, None], mx.zeros((B, 1, S, 0)))
            packed_full = keys[:, 0]
        else:
            packed_full = packed
        T = packed_full.shape[1]
        # Short-context bypass: when the whole cache fits within index_topk the indexer
        # would select every token, so skip the O(T) pooling/scoring/topk and let the
        # DSA fall through to dense MLA. The cache is already updated above so state
        # stays consistent; the full pool is rebuilt once when T first exceeds index_topk.
        if getattr(self, "bypass_short", True) and T <= self.index_topk:
            return None
        k_full, gate_full, valid_ch = mx.split(
            packed_full, [self.head_dim, 2 * self.head_dim], axis=-1
        )
        valid = valid_ch[..., 0] > 0

        offset = T - S
        kv_len = T
        kv_pos = mx.arange(T)

        # Incremental pooling at decode: complete pools are stable across steps, so
        # recompute only the suffix (last partial pool + any new pool) and reuse the
        # cached complete pools -- turns the per-step pool cost from O(T) to O(kpool).
        # Exact; falls back to full pooling on prefill, when padding is present, or when
        # the cached pool's batch axis no longer matches the current batch. That last
        # guard matters under continuous batching: BatchGenerator grows/shrinks the
        # batch (extend/filter) on the batch axis but does not carry this per-cache
        # _pool along, so a stale _pool must be discarded and rebuilt for one step.
        if (
            S == 1
            and cache is not None
            and getattr(cache, "_pool", None) is not None
            and getattr(cache, "_no_pad", False)
            and cache._pool[0].shape[0] == B
        ):
            ck, ci, cv, t_prev = cache._pool
            n_stable = t_prev // self.index_kpool
            s0 = n_stable * self.index_kpool
            pk_s, pi_s, pv_s = self._pooled_states(
                k_full[:, s0:], gate_full[:, s0:], valid[:, s0:]
            )
            pi_s = mx.where(pi_s >= 0, pi_s + s0, -1)
            pool_keys = mx.concatenate([ck[:, :n_stable], pk_s], axis=1)
            pool_indices = mx.concatenate([ci[:, :n_stable], pi_s], axis=1)
            pool_valid = mx.concatenate([cv[:, :n_stable], pv_s], axis=1)
        else:
            pool_keys, pool_indices, pool_valid = self._pooled_states(
                k_full, gate_full, valid
            )
            if cache is not None:
                cache._no_pad = bool(mx.all(valid))
        if cache is not None:
            cache._pool = (pool_keys, pool_indices, pool_valid, T)
        P = pool_keys.shape[1]
        select_k = min(self.index_topk // self.index_kpool, P)
        pool_end = mx.clip(pool_indices[..., -1], 0, kv_len - 1)
        pool_keys_t = pool_keys[:, None].swapaxes(-1, -2)
        tail_on = self.index_kpool_always_select_tail and self.index_kpool > 1
        output_width = self.index_topk + (self.index_kpool - 1 if tail_on else 0)

        # Chunk over the query dimension. A one-shot prefill otherwise materializes
        # [B, S, n_heads, P] scores (O(S*P)) and OOMs at long context; chunking bounds
        # peak to O(chunk*P). Decode (S=1) is a single chunk -> identical to before.
        chunk = 512 if S > 512 else S
        out = []
        for c0 in range(0, S, chunk):
            c1 = min(c0 + chunk, S)
            cs = c1 - c0
            q_pos = offset + mx.arange(c0, c1)
            visible = (kv_pos[None, None, :] <= q_pos[None, :, None]) & valid[:, None, :]
            scores = q[:, c0:c1] @ pool_keys_t
            scores = mx.maximum(scores * self.softmax_scale, 0.0)
            weights = self.weights_proj(x[:, c0:c1]) * (self.n_heads**-0.5)
            index_scores = mx.sum(weights[..., None] * scores, axis=2)
            pool_visible = mx.take_along_axis(
                visible, mx.broadcast_to(pool_end[:, None, :], (B, cs, P)), axis=-1
            )
            valid_candidates = pool_visible & pool_valid[:, None]
            index_scores = mx.where(valid_candidates, index_scores, -1e30)
            order = mx.argsort(-index_scores, axis=-1)
            selected = order[..., :select_k]
            selected_valid = mx.take_along_axis(valid_candidates, selected, axis=-1)
            pi = mx.broadcast_to(pool_indices[:, None], (B, cs, P, self.index_kpool))
            sel_exp = mx.broadcast_to(
                selected[..., None], (B, cs, select_k, self.index_kpool)
            )
            selected_indices = mx.take_along_axis(pi, sel_exp, axis=2)
            topk = selected_indices.reshape(B, cs, select_k * self.index_kpool)
            sv = mx.broadcast_to(
                selected_valid[..., None], (B, cs, select_k, self.index_kpool)
            ).reshape(B, cs, select_k * self.index_kpool)
            topk = mx.where(sv, topk, -1)
            if tail_on:
                topk = mx.concatenate([topk, self._visible_tail(visible, valid)], axis=-1)
            if topk.shape[-1] < output_width:
                pad = mx.full(
                    (B, cs, output_width - topk.shape[-1]), -1, dtype=topk.dtype
                )
                topk = mx.concatenate([topk, pad], axis=-1)
            topk = topk[..., :output_width]
            topk = mx.where(valid_cur[:, c0:c1][..., None], topk, -1)
            out.append(topk)
        topk = out[0] if len(out) == 1 else mx.concatenate(out, axis=1)
        return topk[:, None].astype(mx.int32)


class source_sparse_attention(nn.Module):
    def __init__(self, config: TextConfig):
        super().__init__()
        self.config = config
        self.hidden_size = config.hidden_size
        self.num_heads = config.num_attention_heads
        self.q_lora_rank = config.q_lora_rank
        self.qk_rope_head_dim = config.qk_rope_head_dim
        self.kv_lora_rank = config.kv_lora_rank
        self.v_head_dim = config.v_head_dim
        self.qk_nope_head_dim = config.qk_nope_head_dim
        self.use_nope = config.mla_use_nope or config.qk_rope_head_dim == 0
        # GLM-5-Next is NoPE by design (qk_rope_head_dim=0, mla_use_nope=True); the
        # config carries no rope parameters. Fail loudly rather than run wrong math
        # if a future config ever requests a RoPE MLA.
        if not self.use_nope:
            raise NotImplementedError(
                "glm5_next implements NoPE MLA only; qk_rope_head_dim>0 with "
                "mla_use_nope=False is not supported."
            )
        self.q_head_dim = config.qk_nope_head_dim
        self.scale = self.q_head_dim**-0.5

        self.q_a_proj = nn.Linear(
            self.hidden_size, self.q_lora_rank, bias=config.attention_bias
        )
        self.q_a_layernorm = nn.RMSNorm(self.q_lora_rank, eps=config.rms_norm_eps)
        self.q_b_proj = nn.Linear(
            self.q_lora_rank, self.num_heads * self.q_head_dim, bias=False
        )
        self.kv_a_proj_with_mqa = nn.Linear(
            self.hidden_size, self.kv_lora_rank, bias=config.attention_bias
        )
        self.kv_a_layernorm = nn.RMSNorm(self.kv_lora_rank, eps=config.rms_norm_eps)
        self.embed_q = MultiLinear(
            self.qk_nope_head_dim, self.kv_lora_rank, self.num_heads
        )
        self.unembed_out = MultiLinear(
            self.kv_lora_rank, self.v_head_dim, self.num_heads
        )
        self.o_proj = nn.Linear(
            self.num_heads * self.v_head_dim,
            self.hidden_size,
            bias=config.attention_bias,
        )
        self.indexer = Glm5NextIndexer(config)

    def __call__(
        self,
        x: mx.array,
        mask: Optional[mx.array] = None,
        cache: Optional[Any] = None,
    ) -> mx.array:
        B, L, D = x.shape

        qr = self.q_a_layernorm(self.q_a_proj(x))
        q = self.q_b_proj(qr)
        q = q.reshape(B, L, self.num_heads, self.q_head_dim).transpose(0, 2, 1, 3)

        compressed_kv = self.kv_a_proj_with_mqa(x)
        kv_latent = self.kv_a_layernorm(compressed_kv)
        kv_latent = mx.expand_dims(kv_latent, axis=1)

        if cache is not None:
            kv_latent, _ = cache[0].update_and_fetch(kv_latent, kv_latent)
        else:
            cache = [None] * 2

        topk_indices = self.indexer(x, qr, mask, cache=cache[1])
        attn_mask = mask
        if topk_indices is not None:
            Kv = kv_latent.shape[2]
            valid_sel = topk_indices >= 0
            if L == 1:
                clamped = mx.clip(topk_indices[:, :, 0, :], 0, Kv - 1)
                idx = clamped[..., None]
                kv_latent = mx.take_along_axis(
                    kv_latent,
                    mx.broadcast_to(idx, idx.shape[:-1] + (kv_latent.shape[-1],)),
                    axis=2,
                )
                sel_mask = valid_sel[:, :, 0, :][:, :, None, :]
                if mask is not None and mask.dtype == mx.bool_:
                    # Single-stream decode passes mask=None here; under continuous
                    # batching the batched cache supplies a left-pad mask that can be
                    # 4-D ([B, 1, 1, Kv]) while `clamped` is 3-D. At S=1 the mask is
                    # purely per-key (no causal), so reduce it to [B, Kv] and gather the
                    # selected key positions -- rank-agnostic and batch-safe.
                    mkeys = mask.reshape(B, -1, Kv)[:, 0, :]
                    gathered = mx.take_along_axis(
                        mx.broadcast_to(mkeys[:, None, :], (B, clamped.shape[1], Kv)),
                        clamped,
                        axis=-1,
                    )
                    sel_mask = sel_mask & gathered[:, :, None, :]
                attn_mask = sel_mask
            else:
                shape = list(topk_indices.shape)
                shape[-1] = Kv + 1
                safe_idx = mx.where(valid_sel, topk_indices, Kv)
                sparse_mask = mx.zeros(shape, dtype=mx.bool_)
                sparse_mask = mx.put_along_axis(
                    sparse_mask, safe_idx, mx.array(True), axis=-1
                )
                sparse_mask = sparse_mask[..., :Kv]
                if mask is not None and mask.dtype == mx.bool_:
                    sparse_mask = sparse_mask & mask
                attn_mask = sparse_mask

        if (
            cache is not None
            and cache[0] is not None
            and cache[1] is not None
            and cache[1].keys is not None
        ):
            cache[0].keys = mx.depends(cache[0].keys, (cache[1].keys, cache[1].values))

        if L == 1:
            q = self.embed_q(q)
            k = v = kv_latent
        else:
            k = self.embed_q(kv_latent, transpose=False)
            v = self.unembed_out(kv_latent)

        output = scaled_dot_product_attention(
            q, k, v, cache=cache, scale=self.scale, mask=attn_mask
        )
        if L == 1:
            output = self.unembed_out(output)

        output = output.transpose(0, 2, 1, 3).reshape(B, L, -1)
        return self.o_proj(output)
