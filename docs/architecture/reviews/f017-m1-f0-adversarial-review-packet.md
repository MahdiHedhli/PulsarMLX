# F017 M1-F0 Adversarial Review Packet

## Requested verdict

Return exactly one:

- `GO FOR ONE M1-F0 REAL ROUTE DISCOVERY`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

This packet does not authorize M1-F0 or M1-F.

## Frozen review boundary

- preparation base: `de25a5327cffbd30c8e4898df8f019ec9f084c94`
- tooling/runtime admission head: `bf11011badb0fef90abd3d8fcfd4850db536a35e`
- accepted M1-E evidence: `0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9`
- M1-F blocker: `f7f6d7bc387481f99386a19f13a5f561d3ee4bff18f5e197ffcfe9a42a18b4b6`
- layer/position: `blk.3` / `0`
- immutable config: `docs/architecture/reviews/evidence/f017-m1-f0-execution-config-v1.json`
- config SHA-256: `f97e2efe62b1718047f6ae7b6fca3bc4aa12714bf25bb77848641d15dd5aee76`
- input package identity: `eb5693c99f73c2a95d71aec947b8a18a6c07c71dbbb460490af82b617dba9283`
- input artifact SHA-256: `ea18e9ce6e96a0e6f2324733ee432af5b1c8cdcf80e3e28ca4d7e57c7fcd3d18`
- input generator SHA-256: `8dd7e9b8a4e4a6bfdb5a71535dabd28b4495209df326a88650b6831efc26d32d`
- oracle preparer SHA-256: `ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d`
- boundary contract: `43bfe807858d233a3cb96f11b6dd55379651b50be04d8791af979b80935f7dbd`
- decoder contract: `2ef792969f48398dd18b876eae2b4a45d063bcc76169b83d8c5561cc6f9da66e`
- exact scaffold: `6f6278715159c24e21c60ded97b993fd575393de9b4b16b3fc4dbfb16d1416cb`
- selection contract: `4207845cd22f89a42c42a5ab8ef240cf1af5db3434c2cabac0ecfe9d1beddd0a`
- numerical contract: `e380416041b750535f6339da25710ab8633f6fe1561c4494919b010d392dbb01`
- route schema: `1832abb9c925a5884ec26c915abf87b8bd36d28aa5f8ca2eaa9cb579d834e780`
- synthetic qualification: `5b63c0a6be3e5a1f60f78c4b0a492051ad3217c0cc6d7e1e0c083c5ffad16c7b`
- stress qualification: `8bdf041909cda62b0640f35de3faa5ec31b5f379bb1fe0bced993f5b356a74e7`
- soak evidence: `2b7568201684c27f22af28ec4de584b53501b536a5b5dc120beadfea5e746711`

## Access and isolation

The config names exactly 12 shard-2 tensor ranges. The budget is one shard
open, 12 positional reads, 139,217,920 compressed bytes, 666,430,464 decoded
bytes, and zero expert payloads. DSA position 0 uses range-fill and does not
load indexer weights. Expert, shared-expert, complete-layer, next-layer,
output-head, and logits access is prohibited.

## Oracle and selection

The preparer independently decodes F32/Q8_0/Q5_K, uses strict sequential f32
matvec/RMS arithmetic, computes the complete position-zero attention path and
attention residual, then computes the router. It serializes the sorted ranking
and exact top-8 as little-endian u16 and routing weights as little-endian f64.
The historical route `[15,177,233,41,166,26,10,152]` is neither an input nor a
fallback.

The future public route artifact must bind the input, checkpoint/catalog/map,
attention residual, router score, top-8 ID bytes, routing-weight bytes,
preparer, and selection contract. It must state `expert_computation=false`.

## Attempt and downstream semantics

Preflight/admission failures are unconsumed. Attempt 1 is consumed only after
external authorization, revalidation, admission, and transition to real
bounded oracle execution. No retry may reuse an attempt number.

Accepted M1-F0 evidence is the sole route source for M1-F. M1-F preparation
must resolve exactly the eight expert triplets from it, add a shared expert
only if the architecture contract requires one, and derive fresh tensor,
access, dispatch, oracle, and numerical contracts. A changed input requires a
new route discovery.

## Required falsification attempts

Try to demonstrate any of the following:

1. input generation depends on the historical route or checkpoint;
2. a non-allowlisted or expert tensor can be read;
3. catalog metadata can be changed without invalidating the config;
4. Python/Rust/spec decoder bytes disagree;
5. Rust, MLX, FFI, candidate data, or Feature 018 influences the oracle;
6. attention error bounds can change the exact selected experts;
7. tie-breaking or routing-weight serialization is ambiguous;
8. package relocation, cwd, traversal, or symlink behavior can widen access;
9. preflight consumes an attempt or opens a payload;
10. an authorization/config mutation can pass by path alone;
11. the future route artifact is insufficient to freeze M1-F experts;
12. M1-F0 and M1-F can collapse into one authorization.

The review must stop before any real checkpoint access.
