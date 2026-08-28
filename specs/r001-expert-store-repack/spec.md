# R001: Expert Store Repack

## Scope

R001 repacks byte-identical GLM GGUF expert components into deterministic,
independently addressable `(layer, expert)` bundles. It does not alter tensor
bytes, quantization, shapes, inference numerics, F017 state, or model-output
claims. A complete checkpoint repack is explicitly outside the foundation
graph.

## Mandatory gates

1. Isolated standalone clone from current `origin/main`.
2. Live source-layout inventory with byte-confirmed coverage.
3. Independent bundle-format and verification designs.
4. Adversarial design acceptance before implementation.
5. Bounded Rust copy path and independent verifier.
6. Bounded fixtures plus one complete representative routed-expert layer.
7. Evidence-backed same-device read-pattern benchmark.
8. Independent final acceptance.

## Accepted live authority

- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- Six verified GGUF v3 shards, `238,458,632,928` bytes total.
- Architecture `glm-dsa`, 79 layers, MoE layers 3 through 78.
- 456 expert tensors and 19,532 routed/shared expert objects.
- Routed expert axis is GGUF dimension 2 with 256 contiguous planes.
- Expert payload is `224,974,307,328` bytes.
- All live expert ranges are bounded, unique, contiguous, and preserve whole
  quantization blocks; no expert object spans a shard.

## Accepted format boundary

Version 1 uses one contiguous source extent per component, 16 KiB bundle
component alignment, exact gate/up/down ordering, domain-separated identities,
canonical JSON/JSONL test vectors, and fail-closed no-overwrite publication.
The independent verifier parses GGUF and reconstructs ranges without importing
the Rust packer's mapping implementation.

## Current state

`R001_FOUNDATION_ACCEPTED`

The live checkpoint and design gates passed. Production implementation is
admitted for the bounded 269-object foundation scope only. Full-store repack,
inference integration, placement policy, caching, replication, and F017 changes
remain out of scope.
