# F017 M1-F0 Adversarial Delta-Review Packet

## Requested verdict

Return exactly one:

- `GO FOR ONE M1-F0 REAL ROUTE DISCOVERY`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

This is a narrow external review. It does not authorize M1-F0 or M1-F and
must not access checkpoint payloads.

## Frozen delta boundary

- remediation base: `1c80f6419112f3410cdb26e3294a8610c31a9c22`
- runtime semantic boundary: `7e4c3f37049444443164964aea2fc630752d17ce`
- tooling/config content commit: `7d7b972ce541ca1f62fad5269283249510ff67e8`
- rebuilt execution config:
  `docs/architecture/reviews/evidence/f017-m1-f0-execution-config-v1.json`
- rebuilt config SHA-256:
  `444ab5d0c0c763ee6af52d8b3a8859e1edcfa17dd8609e03551a554f6cfd8a3f`
- input regeneration evidence:
  `docs/architecture/reviews/evidence/f017-m1-f0-input-regeneration-v1.json`
- tooling defect evidence:
  `docs/architecture/reviews/evidence/f017-m1-f0-tooling-provenance-finding-v1.json`
- Q5_K qualification evidence:
  `docs/architecture/reviews/evidence/f017-m1-f0-q5-k-real-byte-qualification-v1.json`

## Finding 1: tooling/config provenance

At `3192b31`, the config declared `bf11011`, contained the old fixture
artifact `ea18e9ce...`, and was absent from the declared commit. At `1c80f64`,
the config used the new fixture artifact `33be5f7e...` but still declared
`3192b31`. No historical config revision was self-consistent.

The repaired identity model keeps distinct:

- runtime semantic boundary: `7e4c3f37049444443164964aea2fc630752d17ce`
- tooling/config content commit: `7d7b972ce541ca1f62fad5269283249510ff67e8`
- authorization head: unset pending external review
- final documentation/evidence head: resolved separately from tooling content

The validator uses Git object identity, not prose: it checks ancestry, tree
OID, a canonical execution-content manifest, and the bytes of every bound
artifact at the exact tooling commit. Negative tests reject its parent, a
descendant, an unrelated commit, stale fixture provenance, and identical
fixture bytes paired with wrong provenance metadata.

The fixture was regenerated into a fresh temporary target with:

`uv run --project scripts/research --python 3.13.13 python scripts/research/generate_f017_m1f0_input.py --output <fresh-temporary-file>`

The runtime reported CPython 3.13.13, NumPy 2.4.5, PCG64, seed 17017006. The
result was byte-identical:

- fixture: `33be5f7ed93a29621b39034246a8bf088111fa4138b0966179aad94a138e63c4`
- package: `eb5693c99f73c2a95d71aec947b8a18a6c07c71dbbb460490af82b617dba9283`
- hidden: `decc4ef42e1cf5d6cbee2fe6d46f3cd29b6dd39b9bb997d1083e7a7228ed86cf`
- position: `af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`
- MLA cache: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- DSA: `2bb5d053425b308fbef711827f82a50aa05a6cc2ae11952f3f90447ff0d27764`
- mask: `4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a`

## Finding 2: real-byte Q5_K qualification

Exactly one payload was read: `blk.3.attn_output.weight` from shard 2 at
offset 2,008,658,784, length 69,206,016. Its logical shape is
`[6144,16384]`, packed row width 11,264, and packed SHA-256 is
`30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084`.

Decoder A is the existing scalar M1-F0 oracle in
`scripts/research/prepare_f017_m1f0_real_reference.py`, SHA-256
`ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d`.

Decoder B is a separate NumPy vector transcription in
`scripts/research/qualify_f017_m1f0_q5_k_real.py`, SHA-256
`57d5de26453b52ac569fd72bc84512f65bd73c5aff5c59280c42ae145bff1e30`.
It neither imports nor calls decoder A. Its layout was independently
transcribed from pinned llama.cpp commit
`a94d563ed801d1da1b8c2432946de07d0231bb3d`, source SHA-256
`2c927a1b3d9f0920dcf4007fb686e1b0999333e9f65ce43dcc689900c0beae8b`.

Both decoded 100,663,296 row-major little-endian f32 elements to exactly:

`2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8`

The comparison was bit-exact with no first divergence, non-finite value, or
signed zero. The harness retains first-element/block/raw-block diagnostics for
future mismatches. Three synthetic scale/quant-pattern blocks and the existing
Rust format fixture also pass exactly.

The public qualification contract is
`specs/017-rust-native-inference-runtime/contracts/m1f0-q5-k-real-byte-exact-v1.json`,
SHA-256 `06e9acf6838fbfe8bb11a653b631d126dadab37590f50cba4db9bdaf16656510`.
No checkpoint path or packed/decoded bytes are public.

## Downstream hardening

The strengthened route schema is
`specs/017-rust-native-inference-runtime/contracts/m1f0-route-v1.schema.json`,
SHA-256 `ad423bec7dc2513521a36e9d98758bb5718d520350bf384282e72971ba8a7add`.
It directly binds the original input package, attention normalized input,
attention output and residual, router normalized input and scores, exact ID
bytes, routing-weight bytes, oracle/preparer, decoder set, selection contract,
and numerical contract.

Downstream M1-F must carry the exact M1-F0 attention-residual bytes/hash. If it
recomputes attention, the residual must qualify against that bound value while
the route IDs remain frozen; route divergence is a failure.

The first-real-quantization policy is
`specs/017-rust-native-inference-runtime/contracts/f017-first-real-quantization-admission-v1.json`,
SHA-256 `fcec2aef9d17efe4973f5561b7fc9eb2cee8428c04889c4582b133f53bc66370`.
It records F32, Q8_0, IQ2_XXS, IQ3_XXS, and now Q5_K qualifications without
overclaiming unqualified Q4_K/Q6_K families.

## Rebuilt gate

The config binds the exact 12-tensor expert-free allowlist and original
139,217,920-byte future M1-F0 access budget. The non-consuming preflight
returns exactly `READY_TO_EXECUTE_M1_F0` with zero checkpoint reads, route
discovery false, zero MLX dispatches, and no attempt consumption.

Checkpoint-free qualification passes 10 deterministic synthetic repeats,
exact top-8 and routing bytes, all six stress families, historical-route
rejection, expert-access rejection, config mutation rejection, M1-E/M1-D
regressions, identity/loader regressions, and full workspace tests. The
synthetic route remains test-only and is not a real route artifact.

## Questions for the reviewer

1. Is finding 1 closed?
2. Is finding 2 closed?
3. Is Q5_K decoder truth independently established?
4. Is the rebuilt M1-F0 execution config self-consistent?
5. Is the route artifact sufficient for downstream M1-F?
6. Is one real M1-F0 route-discovery attempt now meaningful and fail closed?

