# F017 M1-D Attempt 3 Handoff

**Status: PREPARED / NOT EXECUTED**

This handoff replaces the consumed attempt-2 launch. It authorizes no execution
by itself. A separate attempt-3 authorization binds this document by content
hash and binds the immutable execution config rendered by the non-consuming
preflight.

## Runtime and command source

- runtime SHA: `1c7705c130d5909bb4523d70bc7ec45e974e1b24`
- tooling/validator SHA: `2e84a4e0899cea333deadb2c7f4a5022766e0784`
- attempt: `3`
- source of truth: `docs/architecture/reviews/evidence/f017-m1-d-attempt-3-authorization-v1.json`
- execution-config SHA-256: `42fb54d08c2c8ee8c7b06360e04743e8c8a976df649e1a0b8ef505c94c01a9fa`
- command contract: `f017-m1d-command-assembly-v1`
- execution-config schema: `pulsarmlx.f017.m1d-execution-config` version `1.0.0`

The production command is config-only:

```text
f017-glm52-runner --m1d-execution-config <immutable-config> --execution-config-sha256 <sha256>
```

No activation, contract, checkpoint, package, evidence, mode, or repeat option
may appear separately. Extra or duplicate arguments fail before admission and
before checkpoint access.

## Exact activation identity

- path kind: `repository_relative`
- symbolic path: `specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json`
- fixture artifact SHA-256: `1727e63a5daee0ffbb0bf6dea11ea5ecf1b559850632785d5c8864c2bbaf503a`
- activation payload SHA-256: `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`

The historical attempt-2 path under `specs/017-real-checkpoint-runner` is
forbidden even if it contains identical bytes.

## Immutable bindings

- attempt 1 evidence: `a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62`
- attempt 2 evidence: `6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6`
- M1-A: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- M1-B: `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`
- M1-C: `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`
- checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- catalog: `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`
- tensor map: `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- boundary: `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`
- decoder: `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`
- scaffold: `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`
- Tier-B: `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`
- repeat integrity: `1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f`
- oracle ordering: `f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528`
- path resolution: `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d`
- package schema v2: `eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a`
- activation generator: `29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984`
- fixture finalizer: `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92`
- attempt-3 real-reference preparer: `a9474c8f9c5e76fd17beab3f84ab037105f0610dfe8f8972e4f92f52356ebb99`

## Attempt consumption and stop

Preflight validates and renders the immutable config without consuming attempt
3 and without checkpoint access. Attempt 3 becomes consumed only when the
separately authorized production runner transitions into execution state.
Attempts 1 and 2 remain immutable rejected attempts.

Attempt 3 permits one conceptual projection with exactly ten native repeats,
no retry, and a mandatory stop before M1-E. M1-E, P1, P2, golden-eight, and
Feature 018 remain unauthorized.
