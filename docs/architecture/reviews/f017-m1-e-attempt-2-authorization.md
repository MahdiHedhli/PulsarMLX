# F017 M1-E Attempt 2 Authorization

**Status: PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This is a fresh authorization. Attempt 1 remains consumed and rejected; this
packet does not relabel it or permit a retry under its authorization.

## Direct immutable bindings

- runtime/tooling SHA: `942f23505e5829e55bc9b6611bd08d3c93481672`
- handoff path:
  `docs/architecture/reviews/f017-m1-e-attempt-2-handoff.md`
- handoff SHA-256:
  `3f5b896b9c34644a8b725f3a31feaa2ede38ada77d399c795ce8049db0e92781`
- execution-config SHA-256:
  `4778a2694fd4a80feb5789ee3641dcd13fea3b2ba1d144dc150dde8af7d14cd7`
- M1-E attempt-1 rejected evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
- M1-A/B/C/D evidence:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` /
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` /
  `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` /
  `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` /
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` /
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- decoder v2:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- corrected independent IQ3 decoder:
  `5faff93b578028065854d1f3717951126404e1a5ccbe9b16f7f5dc8d5343ab68`
- Rust candidate IQ3 decoder:
  `c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161`
- third specification decoder:
  `10b2c1eeda4d2955fbc61df659d28a4b2c1b72eb2d730145e74bbad86b347621`
- corrected real-reference preparer:
  `841279fe5a1467f6e8deaaa0e22c59c1c2828bb67f16d5f48ad42dd198f6e224`
- activation fixture/payload:
  `a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8` /
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- boundary/scaffold/Tier-B:
  `0b28cc94522c52cc21df3bce72084d07bdd22f92bd21f5f0dd9775066e675a1a` /
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- path/evidence/config schemas:
  `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d` /
  `8779b966080c21f6a287e096363b141158e54e7022df96b3786cb1a1a774b264` /
  `6683ca5fcc067bc15004987a5ab78249d6bc0bca3fe812860af75be06a787294`

## Payload identities

- gate packed / decoded:
  `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` /
  `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db`
- up packed / decoded:
  `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` /
  `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10`
- down packed / corrected decoded:
  `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` /
  `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`

## Authorization and mandatory stop

The operator must launch only from the hash-bound private execution config;
no expert, tensor, fixture, decoder, contract, path, or output override is
permitted. The config-only preflight must return exactly
`READY_TO_EXECUTE_M1_E`, then production admission must pass before the
exclusive attempt-2 state transition.

This packet authorizes one conceptual layer-3/expert-15 execution, exactly
three bounded payload reads, 10 complete deterministic repeats, and exactly 30
native matvec dispatches. The independent oracle must finalize before
candidate start. All frozen numerical, repeat, lifecycle, dispatch, access,
and privacy gates must pass without threshold changes.

No automatic retry is authorized. Stop after the first attempt-2 result. Do
not execute M1-F, another expert, a complete layer, logits, P1/P2/golden-eight,
or Feature 018 integration.
