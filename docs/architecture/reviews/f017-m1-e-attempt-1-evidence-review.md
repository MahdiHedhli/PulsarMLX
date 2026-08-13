# F017 M1-E Attempt 1 Evidence Review

**Verdict: M1-E REJECTED**

## Binding and admission

- runtime: `466770362e3066fa5fd9827ec1f454e03afe3006`
- tooling: `3387bb6d4508eb04e672dc6194da2855ba72f072`
- reviewed head: `4569867cfc6f9c7a2c99502a1e2abb957b36f9f7`
- execution config: `7f69550bfd7ccd5e820f23d2bcce7f0e287d2c2bfc5f1ae2adb59ec5467b0a1b`
- accepted M1-A/B/C/D evidence: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` / `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` / `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` / `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- preflight: exactly `READY_TO_EXECUTE_M1_E`
- admission: `production_reviewed`, `measured_host`, arm64, normal memory
  pressure and thermal state, port 1234 clear, competing inference clear
- loaded `libmlx.dylib` and `libmlxc.dylib`: actual hashes matched reviewed
  expected hashes

The attempt transitioned once to `EXECUTION_STARTED` and is consumed. No
automatic retry or command correction occurred.

## Tensor access and independent oracle

Exactly the three authorized layer-3/expert-15 payloads were read, through one
shard open and three positional reads totaling 11,304,960 bytes.

| Role | Packed payload SHA-256 | Independent decoded-f32 SHA-256 |
|---|---|---|
| gate | `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` | `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` |
| up | `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` | `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` |
| down | `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` | `c252537660deb00330ec289338daaf89d550ce8a3553d7e34ac59353156f756d` |

The independent package finalized before candidate execution:

- oracle SHA-256: `c48c746f86ef01d52f2d6d1cb7e274010b4dddbf392d96e8cd27a2d1b1d9d491`
- package SHA-256: `4ca8d1d5b2423bf3f10e888e8e98145a71e2b319c3dc8ae5f982100e00af0693`
- input fixture payload: `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- gate/up/activated-hidden/final reference hashes:
  `c81dda8c2127ab694981b447df4dd7f15eb23ca2257af021fbb8776342215ec9` /
  `808988d579fd1e77fd8c45c2fbb5cc79a58260de5f79f7e867833b5a156782ed` /
  `8f4414e53c027b18f704ef41b9b08b5c9272e31e5877371608baeb78d79f9fbd` /
  `4b6029ef1f39a6685ca3584c4a5537b0c764c72c831898ec9bbed59852fcac97`
- gate/up/activated-hidden/final bound-vector hashes:
  `7da8cb86e1c594eb96dfb3d701e4796901000fa218c69e316e6b43849bd756c7` /
  `eec11d311a3063298f41377a6de97dc02fd52b2c46939af7cef2df237352a60a` /
  `c1f0cb57293ae83456a14c9f60735dc4bb121edafe4f3ebbc6dc7819ba55204d` /
  `b67a9dca795ae68db49f4201ce05461796b5ac6e74058fec490b923c4eae8fd4`

Raw packed tensors and the oracle package remain local-only and uncommitted.

## First failure and isolation

The runner rejected the attempt with:

- classification: `FAIL_INFRASTRUCTURE_EVIDENCE`
- code: `m1e_down_decoded`
- message: `SHA-256 mismatch`

The failure occurred while reconciling the candidate's decoded down matrix
against the independent oracle identity, before candidate start. The candidate
did not persist its divergent decoded hash, so this review does not infer it.

- conceptual expert executions: 0
- production projections: 0
- native MLX dispatches: 0
- production repeats: 0
- qualification scaffold/reference/fallback/backend errors: 0/0/0/0
- router, second/shared expert, layer, logits, M1-F, P1, P2, golden-eight,
  Feature 018: 0/false

No MLX context or stream was created. Lifecycle evidence is therefore terminal
pre-candidate failure state rather than a successful reconciliation record;
PASS validation was never entered and no numerical classification was issued.

## Timing and evidence integrity

- storage: 0.067751792 seconds
- candidate gate/up/down decode checks: 0.017399917 / 0.013309833 /
  0.013238083 seconds
- oracle gate/up/down decode: 0.083468458 / 0.052470833 / 0.087183500 seconds
- oracle gate/up/activation/down: 0.056719667 / 0.056654625 /
  0.000043916 / 0.054907417 seconds
- public-safe evidence SHA-256:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`

The banked artifact is byte-identical to the canonical private runner evidence,
contains no absolute private path, passes duplicate-key parsing, and preserves
the first failure. M1-F is not prepared or authorized. Any investigation or
new M1-E attempt requires a new remediation/review/authorization cycle.
