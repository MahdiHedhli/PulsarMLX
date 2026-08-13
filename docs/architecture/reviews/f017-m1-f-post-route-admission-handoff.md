# F017 M1-F Post-route Admission Handoff

Status: `PREPARED / NOT AUTHORIZED`

M1-F0 attempt 2 is accepted. Its immutable evidence SHA-256 is
`0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9` and
the sole downstream route artifact SHA-256 is
`980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`.
The frozen layer-3 route is `[166, 78, 26, 186, 163, 199, 233, 177]`.

The machine-readable post-route inventory is
`docs/architecture/reviews/evidence/f017-m1-f-post-route-inventory-v1.json`,
SHA-256 `9352dcb9486d2c1c1a9ff743453c0a973b0f003ba141f0c85602f7ce243d3799`.
It binds all 24 routed expert slices and the three architecturally required
shared-expert matrices. Together with the 12 accepted M1-F0 attention/router
payloads, the prospective complete-layer budget is 39 positional payload reads,
257,281,024 compressed bytes, and 2,025,384,960 decoded f32 bytes from one
shard open.

The accepted attention residual SHA-256 is
`1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7`.
Any complete-layer recomputation must qualify against that exact context while
retaining the frozen IDs and routing weights. A changed route is failure.

The dispatch estimate is 34 native matvecs per repeat and 340 for the future
ten-repeat gate: six attention projections, one router projection, 24 routed
expert matvecs, and three shared-expert matvecs. This remains predicted until
the complete M1-F scaffold and execution config independently re-derive it.

The routed families `IQ2_XXS` and `IQ3_XXS`, plus shared `Q5_K`, have accepted
real-byte qualification in the inherited chain. Shared-down `Q6_K` is a newly
introduced real-gate family and is not yet admitted. The next phase must first
cross-qualify one bounded real Q6_K payload, then freeze the full layer oracle,
numerical/scaffold contracts, exact access/dispatch budgets, synthetic native
integration, internal review, and separate adversarial review.

No M1-F execution or authorization is granted by this handoff. P1, P2,
golden-eight, logits, another layer, and Feature 018 remain blocked.
