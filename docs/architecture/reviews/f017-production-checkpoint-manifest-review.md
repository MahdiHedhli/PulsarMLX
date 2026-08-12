# F017 Production Checkpoint Manifest Review

## Verdict

**PROVISIONED AND VALIDATED FOR A FUTURE M1-B IDENTITY-ONLY RUN**

This review does not authorize M1-B. Provisioning used streaming shard hashing
and GGUF header/catalog parsing only. It did not invoke the canonical runner,
decode a tensor, execute a tensor range, construct an MLX context, or dispatch
model compute.

## Source and schema

- required runtime source:
  `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`
- manifest schema: `pulsarmlx.f017.checkpoint-manifest` `1.0.0`
- manifest kind: production / `production_f017_checkpoint`
- immutable revision:
  `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- privacy: local-only private manifest; public hashes and basenames below
- private manifest SHA-256:
  `208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4`

The private manifest is stored adjacent to the unique canonical checkpoint set
and selected through a permission-restricted local environment file. The public
review does not contain that filesystem path.

## Six-shard identity

| Ordinal | Basename | Bytes | SHA-256 |
|---:|---|---:|---|
| 1 | `GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf` | 9,423,744 | `7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18` |
| 2 | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` | 49,105,028,960 | `d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36` |
| 3 | `GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf` | 49,143,176,640 | `1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b` |
| 4 | `GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf` | 49,143,176,640 | `10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e` |
| 5 | `GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf` | 49,143,176,640 | `40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d` |
| 6 | `GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf` | 41,914,650,304 | `eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d` |

- total bytes: 238,458,632,928
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

Every size and hash matches the immutable Feature 016 checkpoint and remote
revision bindings already committed in `docs/validation`.

## Header, catalog, and tokenizer validation

- GGUF architecture: `glm-dsa`
- catalog tensors: 1,809
- expected layers: 79
- catalog SHA-256 using the runner's exact catalog algorithm:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`
- tensor map version: `f017-glm52-tensor-map-v1`
- tensor map contract SHA-256:
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- tokenizer identity:
  `glm52-gguf-tokenizer-v1:149e907384517d91d236a819835aa0dc97e6d4a3c512e6d5806d6b162ced1c6d`
- tokenizer model/pre-tokenizer: `gpt2` / `glm4`
- vocabulary: 154,880
- BOS/EOS/EOM/EOT: 154822 / 154820 / 154829 / 154827
- chat-template SHA-256:
  `bf78575b301b56fa74337b470f6560d5366ff15378ddf88d623fd0496152fa77`

The actual parsed tensor names, dimensions, quantization IDs, shard assignment,
and relative offsets were compared in order against the committed public C01
catalog. The existing checkpoint-free Rust tensor-map test validates that exact
catalog against all production map contracts. The actual production map will be
invoked again by M1-B if separately authorized.

## Provisioning mechanism and isolation

The canonical set was resolved from the project-documented local model
directory and cross-checked against the immutable repository identity. Exactly
one matching six-shard root exists; each entry is a readable non-symlink regular
file with a unique expected basename.

The provisioning verifier is
[`scripts/research/provision_f017_checkpoint_manifest.py`](../../../scripts/research/provision_f017_checkpoint_manifest.py).
It uses exclusive creation for the private and public manifests and rejects
missing/extra/duplicate shards, altered sizes/hashes, symlinks, architecture or
tokenizer drift, catalog drift, path leakage, unsupported schema, or any
execution-enabled policy.

Isolation counters for this provisioning pass:

- shards opened for streaming identity hash: 6
- GGUF headers/catalogs parsed: 6
- tensor payload ranges read for execution: 0
- tensor executions: 0
- quant decodes: 0
- model compute dispatches: 0
- canonical M1-B runner executions: 0
- M1-B attempts: 0

The public machine-readable review is
[`evidence/f017-production-checkpoint-manifest-review-v1.json`](evidence/f017-production-checkpoint-manifest-review-v1.json)
with SHA-256
`7add53ba16bb14f2e14c18ac5044acdd2ddcd2c5a0009dfe4796880f968531e0`.
