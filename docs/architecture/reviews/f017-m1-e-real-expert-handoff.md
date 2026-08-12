# F017 M1-E Real Expert Handoff

**Status: PREPARED / NOT AUTHORIZED**

This document prepares the next bounded gate only. It does not authorize
checkpoint reads, decoder execution, MLX dispatch, or an M1-E attempt.

## Load-bearing chain

- M1-D runtime: 1c7705c130d5909bb4523d70bc7ec45e974e1b24
- reviewed tooling: 2e84a4e0899cea333deadb2c7f4a5022766e0784
- M1-A: aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805
- M1-B: 9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770
- M1-C: 343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e
- accepted M1-D attempt 3:
  dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c
- checkpoint set:
  d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee
- catalog:
  0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0
- tensor map:
  ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223

## Proposed single-expert boundary

The metadata-only proposal reuses the documented Feature 016 layer-3
expert-15 provenance; no payload was read while preparing this handoff.

- layer/expert: 3 / 15
- input: rms_norm(token_embedding[9703], blk.3.ffn_norm.weight)
- input activation SHA-256:
  b286b0baea31b825002e1dd5d7aa41f6055e7ca94cb7e2d27c0e97a50a56e3c9
- routing IDs: [15, 177, 10, 233, 166, 41, 152, 26]
- expert-15 routing weight: 0.3089511280251867
- gate: blk.3.ffn_gate_exps.weight, IQ2_XXS, shape [6144, 2048, 256]
- up: blk.3.ffn_up_exps.weight, IQ2_XXS, shape [6144, 2048, 256]
- down: blk.3.ffn_down_exps.weight, IQ3_XXS, shape [2048, 6144, 256]
- all three tensors: reviewed shard-2 metadata identity
- independent prior scalar output SHA-256:
  6c9a810bf876f2562f5425575d97c0145050ab8b4d9ad4f7813cc408719eecd2

## Admission package required before authorization

A future M1-E authorization must first freeze, review, and hash-bind:

1. exact expert-15 byte ranges within all three packed tensors;
2. independent IQ2_XXS and IQ3_XXS decoder contracts and bounded real oracle;
3. exact gate → up → SwiGLU → down → routing-weight scaffold order;
4. an immutable production expert numerical contract derived before candidate
   output, including signed-zero/non-finite and ten-repeat rules;
5. a canonical config-only one-expert runner entrypoint and evidence schema;
6. one conceptual expert, expected production dispatch counts, full teardown,
   and zero router/top-8/shared/layer/logits/P1 execution;
7. production-reviewed admission, a fresh exclusive evidence target, one
   attempt, no auto-retry, and a mandatory stop before M1-F.

The checkpoint-free R7 expert contract is inherited as methodology, not as an
automatic real-IQ2/IQ3 numerical authorization. Feature 018 kernels and
output-head residency remain out of scope.

## Stop policy

M1-E is **NOT AUTHORIZED**. A separate review must accept the complete package
and issue a fresh one-attempt authorization. M1-F/M1-G, P1, P2, golden-eight,
and Feature 018 remain blocked.
