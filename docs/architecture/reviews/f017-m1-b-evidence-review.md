# F017 M1-B Evidence Review

## Verdict

**M1-B ACCEPTED**

Exactly one production `--checkpoint-identity-only` execution ran from the
clean immutable runtime source
`b29202171a279cd3bb2ac2cf4dc6b3be7486019e`. It completed on its first
attempt with `checkpoint_identity_complete`. The run did not decode or execute
a tensor and did not create inference, projection, expert, layer, logits, or
token-selection state.

## Evidence identity

- Public-safe evidence:
  [`evidence/f017-m1-b-checkpoint-identity-v1.json`](evidence/f017-m1-b-checkpoint-identity-v1.json)
- Raw local evidence SHA-256:
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`
- Public artifact SHA-256:
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`
- Accepted M1-A public evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- Environment-manifest SHA-256:
  `33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251`
- Reviewed private checkpoint-manifest SHA-256:
  `208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4`

The public artifact is byte-identical to the finalized runner output and
contains no machine-local path.

## Frozen review questions

### Were all six real shards verified?

Yes. The six expected basenames, sizes, and SHA-256 values exactly match the
reviewed manifest:

| Shard | Bytes | SHA-256 |
| --- | ---: | --- |
| `00001-of-00006` | 9,423,744 | `7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18` |
| `00002-of-00006` | 49,105,028,960 | `d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36` |
| `00003-of-00006` | 49,143,176,640 | `1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b` |
| `00004-of-00006` | 49,143,176,640 | `10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e` |
| `00005-of-00006` | 49,143,176,640 | `40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d` |
| `00006-of-00006` | 41,914,650,304 | `eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d` |

The checkpoint-set SHA-256 is
`d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.

### Did catalog, architecture, revision, and tokenizer identity match?

Yes:

- catalog SHA-256:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`;
- revision: `abc55e72527792c6e77069c99b4cb7de16fa9f23`;
- architecture: `glm-dsa`;
- tokenizer:
  `glm52-gguf-tokenizer-v1:149e907384517d91d236a819835aa0dc97e6d4a3c512e6d5806d6b162ced1c6d`.

### Did the production tensor map validate?

Yes. `Glm52TensorMap::from_gguf` returned `validated` for exactly 1,809 tensor
contracts across the required 79-layer architecture. The map contract is
`f017-glm52-tensor-map-v1` with SHA-256
`ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`.
The fail-closed production map therefore accepted every required name, shape,
quantization, and metadata binding without ambiguity or substitution.

### Was the production environment admitted?

Yes. Evidence records `production_reviewed` and `measured_host`:

- arm64 M1 Ultra, 137,438,953,472 physical bytes;
- available memory: 79,950,430,208 bytes;
- required floor: 17,179,869,184 bytes;
- memory pressure: normal;
- compressed memory: 3,101,491,200 bytes;
- swap used: 125,829 bytes;
- checkpoint/evidence volume free: 388,988,088,320 bytes;
- competing inference: clear;
- port 1234 listener: false;
- thermal state: normal;
- performance warning: false.

Dyld-resolved arm64 MLX native 0.31.2 and MLX C 0.6.0 actual hashes exactly
match their reviewed expected hashes.

### Was tensor execution exactly zero?

Yes. The repository-approved identity-mode evidence represents this isolation
as an empty layer list, no generated token, no numerical mode/classification,
zero residency, and dispatch counters of zero for native, direct,
qualification-scaffold, explicit-reference, fallback, and errors. The mode
implementation performs `VerifiedCheckpoint::verify` plus
`Glm52TensorMap::from_gguf`; it has no quant decode, projection, expert, layer,
logits, token, or adapter-compute call. Storage evidence (238,485,096,032 bytes
and 28,444 reads) is the permitted shard hashing and header/catalog work.

### Did lifecycle and evidence reconcile?

Yes. Managed, derived, callback, default/owned stream, and active-context
counters are zero before and after. Registration, pending destruction,
in-flight, owner-token, and generation domains are explicitly
`not_applicable`, not fabricated measured zero. `lifecycle.reconciled` is
true. The canonical PASS validator succeeded before final PASS persistence.

The evidence parses with duplicate-key rejection, contains no local absolute
path, and the exclusive output was finalized without overwrite.

## Disposition

M1-B is accepted. A single bounded M1-C local-only tensor boundary is now
meaningful to review, but it is **not authorized** by this result. T017-140
remains open until that separately authorized real fixture is generated and
validated. T017-141 and P1 remain blocked.

