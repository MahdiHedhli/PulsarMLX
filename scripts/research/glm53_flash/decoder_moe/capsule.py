class source_moe(nn.Module):
    """DeepseekV32MoE with the clamped activation and the fp32 router; same parameter names."""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.num_experts_per_tok = config.num_experts_per_tok
        self.switch_mlp = SwitchGLU(config.hidden_size, config.moe_intermediate_size, config.n_routed_experts, activation=ClampedSwiGLU(config.swiglu_limit))
        self.gate = Glm5NextMoEGate(config)
        if config.n_shared_experts is not None:
            self.shared_experts = ClampedMLP(config, intermediate_size=config.moe_intermediate_size * config.n_shared_experts)

    def __call__(self, x):
        inds, scores = self.gate(x)
        y = self.switch_mlp(x, inds)
        y = (y * scores[..., None]).sum(axis=-2).astype(y.dtype)
        if self.config.n_shared_experts is not None:
            y = y + self.shared_experts(x)
        return y
