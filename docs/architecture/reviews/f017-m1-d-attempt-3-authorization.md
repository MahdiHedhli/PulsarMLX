# F017 M1-D Attempt 3 Authorization

**Status: AUTHORIZED FOR EXACTLY ONE M1-D ATTEMPT 3 / NOT EXECUTED**

This packet authorizes one future M1-D attempt. It does not execute it. The
non-consuming preflight returned `READY_TO_EXECUTE_ATTEMPT_3` with zero
checkpoint access and rendered one immutable execution config.

## Execution identities

- runtime SHA: `1c7705c130d5909bb4523d70bc7ec45e974e1b24`
- tooling/validator SHA: `1c7705c130d5909bb4523d70bc7ec45e974e1b24`
- handoff: `docs/architecture/reviews/f017-m1-d-attempt-3-handoff.md`
- handoff SHA-256: `466c77344b301d9da68d8f31aac7252efe1c3e18ad59453c6373fd95dea6b85c`
- machine binding: `docs/architecture/reviews/evidence/f017-m1-d-attempt-3-authorization-v1.json`
- execution-config SHA-256: `d978a37d0a66067b14515cd617fbc7576617e0eafb1265e081969fd56311a7aa`
- command-assembly contract SHA-256: `8fde317e9da50a8f106149eac4e327c43946bf9c795a657984750cf08e4f59c5`
- execution-config schema SHA-256: `c617d0a539ff38a39168577425d7becfb141eca05647028f637b10d8022e0ae4`
- path contract SHA-256: `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d`
- package schema v2 SHA-256: `eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a`

Every execution-controlling repository artifact is directly bound:

| Role | Repository-relative path | SHA-256 |
|---|---|---|
| boundary | `specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json` | `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613` |
| decoder | `specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json` | `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd` |
| scaffold | `specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json` | `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5` |
| Tier-B | `specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json` | `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b` |
| repeat integrity | `specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json` | `1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f` |
| oracle ordering | `specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json` | `f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528` |
| path resolution | `specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json` | `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d` |
| package schema | `specs/017-rust-native-inference-runtime/contracts/m1d-projection-package-v2.schema.json` | `eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a` |
| command assembly | `specs/017-rust-native-inference-runtime/contracts/m1d-command-assembly-v1.json` | `8fde317e9da50a8f106149eac4e327c43946bf9c795a657984750cf08e4f59c5` |
| execution config | `specs/017-rust-native-inference-runtime/contracts/m1d-execution-config-v1.schema.json` | `c617d0a539ff38a39168577425d7becfb141eca05647028f637b10d8022e0ae4` |
| fixture finalizer | `scripts/research/generate_f017_m1d_projection_oracle.py` | `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92` |
| real-reference preparer | `scripts/research/prepare_f017_m1d_real_reference.py` | `a9474c8f9c5e76fd17beab3f84ab037105f0610dfe8f8972e4f92f52356ebb99` |

The runtime must be built and run from the clean runtime-pinned worktree. A
later documentation-only branch head is not a substitute for this runtime
identity.

## Canonical config-only invocation

```text
f017-glm52-runner --m1d-execution-config execution-config.json --execution-config-sha256 d978a37d0a66067b14515cd617fbc7576617e0eafb1265e081969fd56311a7aa
```

The two options must appear exactly once, in this order. The runner rejects a
loose activation path, duplicate option, conflicting override, extra argument,
environment-derived path, or cwd-derived path. It rehashes the immutable config
before admission and after teardown.

## Exact activation and provenance

- activation symbolic path: `specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json`
- activation artifact SHA-256: `1727e63a5daee0ffbb0bf6dea11ea5ecf1b559850632785d5c8864c2bbaf503a`
- activation payload SHA-256: `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`
- activation generator: `29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984`
- fixture finalizer: `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92`
- attempt-3 real-reference preparer: `a9474c8f9c5e76fd17beab3f84ab037105f0610dfe8f8972e4f92f52356ebb99`

The historical attempt-2 path
`specs/017-real-checkpoint-runner/fixtures/f017-m1d-projection-oracle-v1.json`
is explicitly forbidden, including when copied bytes have the correct hash.

## Prior evidence and checkpoint identity

- attempt 1: `a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62`
- attempt 2: `6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6`
- M1-A: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- M1-B: `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`
- M1-C: `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`
- checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- catalog: `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`
- tensor map: `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`

## Frozen numerical and ordering contracts

- boundary: `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`
- decoder: `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`
- scaffold: `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`
- Tier-B: `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`
- repeat integrity: `1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f`
- oracle ordering: `f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528`

Attempt 3 permits one conceptual projection and exactly ten native repeats.
Every complete output is hashed before buffer reuse, all hashes must match,
and the independent oracle must be finalized and validated before candidate
start.

## Consumption and mandatory stop

Preflight does not consume attempt 3. The attempt becomes consumed when the
explicitly authorized production invocation transitions to execution state.
There is no automatic retry. Attempts 1 and 2 stay preserved as rejected and
consumed.

Stop after attempt 3, regardless of result. This packet does not authorize
M1-E, a second projection, expert/layer/logit execution, P1, P2, golden-eight,
output-head residency, or Feature 018.
