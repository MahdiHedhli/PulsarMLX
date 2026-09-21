"""GLM-5.3-Flash multi-token-prediction layer on the pinned pipenetwork runtime (graph 25).

The original checkpoint's layer `num_hidden_layers` (45) is a plain residual DSA+MoE decoder layer with the DeepSeek-V3
MTP additions - enorm, hnorm, eh_proj (2D -> D), shared_head.norm - and no hyper-connection weights; structure
identical to mlx-vlm's GlmMoeDsaMTP. Built from the runtime's own Glm5NextSparseAttention and Glm5NextMoE so the
attention (indexer + MLA), the router and the clamped SwiGLU are the qualified ones. Forward (one MTP step):

    x = eh_proj(concat(enorm(embed(next_token)), hnorm(hidden)))      # hidden: the target's pre-final-norm hidden
    x = x + self_attn(input_layernorm(x), mask, cache)                  # (the 4-stream mean before Glm5NextModel.norm)
    x = x + mlp(post_attention_layernorm(x))
    return shared_head_norm(x)                                          # -> target.lm_head for the draft logits
"""
from __future__ import annotations

from typing import Any, Optional

import mlx.core as mx
import mlx.nn as nn

from glm53_flash_mlx.glm5_next.language import Glm5NextMoE, Glm5NextSparseAttention


class Glm5NextMTP(nn.Module):
    def __init__(self, config):
        super().__init__()
        d = config.hidden_size
        self.enorm = nn.RMSNorm(d, eps=config.rms_norm_eps)
        self.hnorm = nn.RMSNorm(d, eps=config.rms_norm_eps)
        self.eh_proj = nn.Linear(2 * d, d, bias=False)
        self.input_layernorm = nn.RMSNorm(d, eps=config.rms_norm_eps)
        self.self_attn = Glm5NextSparseAttention(config)
        self.post_attention_layernorm = nn.RMSNorm(d, eps=config.rms_norm_eps)
        self.mlp = Glm5NextMoE(config)
        self.shared_head_norm = nn.RMSNorm(d, eps=config.rms_norm_eps)

    def __call__(self, hidden: mx.array, next_embed: mx.array, mask: Optional[mx.array] = None, cache: Optional[Any] = None) -> mx.array:
        x = self.eh_proj(mx.concatenate([self.enorm(next_embed), self.hnorm(hidden)], axis=-1))
        x = x + self.self_attn(self.input_layernorm(x), mask, cache)
        x = x + self.mlp(self.post_attention_layernorm(x))
        return self.shared_head_norm(x)
