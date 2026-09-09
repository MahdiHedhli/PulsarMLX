class Glm5NextRMSNormGated(nn.Module):
    def __init__(self, hidden_size: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = mx.ones(hidden_size)

    def __call__(self, hidden_states: mx.array, gate: mx.array) -> mx.array:
        dt = hidden_states.dtype
        x = hidden_states.astype(mx.float32)
        var = (x * x).mean(-1, keepdims=True)
        x = x * mx.rsqrt(var + self.eps)
        x = self.weight.astype(mx.float32) * x
        x = x * mx.sigmoid(gate.astype(mx.float32))
        return x.astype(dt)


class Glm5NextForgetGate(nn.Module):
    def __init__(self, config: TextConfig):
        super().__init__()
        self.head_dim = config.linear_head_dim
        self.num_heads = config.linear_num_heads
        self.qkv_dim = self.head_dim * self.num_heads
        self.f_a_proj = nn.Linear(config.hidden_size, self.head_dim, bias=False)
        self.f_b_proj = nn.Linear(self.head_dim, self.qkv_dim, bias=False)
        self.dt_bias = mx.zeros(self.qkv_dim)
        self.A_log = mx.zeros(self.num_heads)
        self.safe_gate_lower_bound = config.linear_lower_bound

    def __call__(self, hidden_states: mx.array) -> mx.array:
        B, S, _ = hidden_states.shape
        fg = self.f_b_proj(self.f_a_proj(hidden_states))
        g = (fg.astype(mx.float32) + self.dt_bias.astype(mx.float32)).reshape(
            B, S, self.num_heads, self.head_dim
        )
        decay = mx.exp(self.A_log.astype(mx.float32)).reshape(1, 1, self.num_heads, 1)
        if self.safe_gate_lower_bound is not None:
            return self.safe_gate_lower_bound * mx.sigmoid(decay * g)
        g_softplus = mx.where(g > 20.0, g, mx.log(1.0 + mx.exp(g)))
        return -decay * g_softplus


def _l2norm(x: mx.array, eps: float = 1e-6) -> mx.array:
    return x * mx.rsqrt((x * x).sum(axis=-1, keepdims=True) + eps)


class Glm5NextLinearAttention(nn.Module):
    def __init__(self, config: TextConfig):
        super().__init__()
        self.hidden_size = config.hidden_size
        self.num_heads = config.linear_num_heads
        self.head_dim = config.linear_head_dim
        self.qkv_dim = self.num_heads * self.head_dim
        self.conv_kernel_size = config.linear_conv_kernel_dim

        self.q_proj = nn.Linear(self.hidden_size, self.qkv_dim, bias=False)
        self.k_proj = nn.Linear(self.hidden_size, self.qkv_dim, bias=False)
        self.v_proj = nn.Linear(self.hidden_size, self.qkv_dim, bias=False)

        self.conv_dim = self.qkv_dim * 3
        self.conv1d = nn.Conv1d(
            in_channels=self.conv_dim,
            out_channels=self.conv_dim,
            bias=False,
            kernel_size=self.conv_kernel_size,
            groups=self.conv_dim,
            padding=0,
        )

        self.forget_gate = Glm5NextForgetGate(config)
        self.b_proj = nn.Linear(self.hidden_size, self.num_heads, bias=False)
        self.g_a_proj = nn.Linear(self.hidden_size, self.head_dim, bias=False)
        self.g_b_proj = nn.Linear(self.head_dim, self.qkv_dim, bias=False)
        self.o_norm = Glm5NextRMSNormGated(self.head_dim, eps=config.rms_norm_eps)
        self.o_proj = nn.Linear(self.qkv_dim, self.hidden_size, bias=False)
        self.fuse_in = True
        self._fused_ready = False

    def _fused_in_proj(self, inputs):
        # q,k,v,f_a,g_a,b all take `inputs`; fuse into one matmul via a lossless
        # output-axis concat of the (quantized) weights, built once and cached.
        if not self._fused_ready:
            mods = [
                self.q_proj,
                self.k_proj,
                self.v_proj,
                self.forget_gate.f_a_proj,
                self.g_a_proj,
                self.b_proj,
            ]
            pts, acc = [], 0
            for m in mods[:-1]:
                acc += m.weight.shape[0]
                pts.append(acc)
            self._split_pts = pts
            self._fq = hasattr(mods[0], "scales")
            self._fw = mx.concatenate([m.weight for m in mods], axis=0)
            if self._fq:
                self._fs = mx.concatenate([m.scales for m in mods], axis=0)
                self._fb = mx.concatenate([m.biases for m in mods], axis=0)
                self._gs, self._bits = mods[0].group_size, mods[0].bits
            self._fused_ready = True
        if self._fq:
            out = mx.quantized_matmul(
                inputs,
                self._fw,
                self._fs,
                self._fb,
                transpose=True,
                group_size=self._gs,
                bits=self._bits,
            )
        else:
            out = inputs @ self._fw.T
        return mx.split(out, self._split_pts, axis=-1)

    def __call__(
        self,
        inputs: mx.array,
        mask: Optional[mx.array] = None,
        cache: Optional[Any] = None,
    ) -> mx.array:
        B, S, _ = inputs.shape
        if self.fuse_in:
            q_o, k_o, v_o, fa_o, ga_o, b_o = self._fused_in_proj(inputs)
            mixed = mx.concatenate([q_o, k_o, v_o], axis=-1)
        else:
            mixed = mx.concatenate(
                [self.q_proj(inputs), self.k_proj(inputs), self.v_proj(inputs)], axis=-1
            )
            fa_o = self.forget_gate.f_a_proj(inputs)
            ga_o = self.g_a_proj(inputs)
            b_o = self.b_proj(inputs)
        if mask is not None and mask.dtype == mx.bool_:
            mixed = mx.where(mask[..., None], mixed, 0)

        if cache is not None and cache[0] is not None:
            conv_state = cache[0]
        else:
            conv_state = mx.zeros(
                (B, self.conv_kernel_size - 1, self.conv_dim), dtype=inputs.dtype
            )
        conv_input = mx.concatenate([conv_state, mixed], axis=1)
        if cache is not None:
            cache[0] = mx.contiguous(conv_input[:, -(self.conv_kernel_size - 1) :, :])
        conv_out = nn.silu(self.conv1d(conv_input))

        q, k, v = mx.split(conv_out, [self.qkv_dim, 2 * self.qkv_dim], axis=-1)
        q = q.reshape(B, S, self.num_heads, self.head_dim)
        k = k.reshape(B, S, self.num_heads, self.head_dim)
        v = v.reshape(B, S, self.num_heads, self.head_dim)

        fg = self.forget_gate
        a = fg.f_b_proj(fa_o).reshape(B, S, self.num_heads, self.head_dim)
        in_dtype = q.dtype
        q = (_l2norm(q.astype(mx.float32)) * (self.head_dim**-0.5)).astype(in_dtype)
        k = _l2norm(k.astype(mx.float32)).astype(in_dtype)

        state = cache[1] if cache is not None else None
        out, state = gated_delta_update(
            q,
            k,
            v,
            a,
            b_o,
            fg.A_log.reshape(self.num_heads, 1),
            fg.dt_bias.reshape(self.num_heads, self.head_dim),
            state=state,
            lower_bound=fg.safe_gate_lower_bound,
        )
        if cache is not None:
            cache[1] = state
            cache.advance(S)

        gate = self.g_b_proj(ga_o).reshape(B, S, self.num_heads, self.head_dim)
        out = self.o_norm(out, gate).reshape(B, S, -1)
        return self.o_proj(out)
