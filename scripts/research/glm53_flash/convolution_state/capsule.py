# SPDX-License-Identifier: Apache-2.0
# PipeNetwork/glm53-flash-mlx a61a7c7d2fbdf3d218a9909365a24bd794f3a247
# Modified: exact selected statements wrapped in research function seams.
# See provenance.json and LICENSE-PipeNetwork.txt. No full model import.

def source_construct(self):
    self.conv_dim = self.qkv_dim * 3
    self.conv1d = nn.Conv1d(
        in_channels=self.conv_dim,
        out_channels=self.conv_dim,
        bias=False,
        kernel_size=self.conv_kernel_size,
        groups=self.conv_dim,
        padding=0,
    )
    return self.conv1d

def source_step(self, inputs, mixed, cache):
    B, S, _ = inputs.shape
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
    return conv_out, (q, k, v)

