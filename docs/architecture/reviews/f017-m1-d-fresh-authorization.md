# F017 Fresh M1-D Authorization Packet

## Status

**AUTHORIZED FOR EXACTLY ONE M1-D ATTEMPT / NOT EXECUTED**

This packet authorizes exactly one conceptual M1-D projection experiment and
ten deterministic native repeats inside that experiment. It does not authorize
a second projection, M1-E, expert/layer/logits execution, P1/P2/golden-eight,
Feature 018, output-head residency, threshold retuning, or automatic retry.

## Immutable source and handoff

- runtime SHA: `d68cb10758693dc61d3af7cf76b8019f6b3b235d`;
- previous reviewed tooling head:
  `9d355cc3e1da55696a47b02170b40bd7bb5aeea7`;
- immutable tooling/validator boundary:
  `15c0de64c342cb5541e643f5e212d2cf5d73da67`;
- handoff: `docs/architecture/reviews/f017-m1-d-real-projection-handoff.md`;
- handoff SHA-256:
  `eff56978ed066527dd9e42689b23c4f7a033b4f0dd5ed1815ee001d95bc5d789`;
- machine-readable binding:
  `docs/architecture/reviews/evidence/f017-m1-d-authorization-binding-v1.json`.

The authorization artifact is a documentation-only descendant of the tooling
boundary. Runtime and tooling identities are deliberately distinct; neither
may substitute for the other.

## Direct evidence and checkpoint bindings

- M1-A: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`;
- M1-B: `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`;
- M1-C: `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`;
- checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`;
- catalog: `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`;
- tensor map: `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`.

## Direct numerical and execution bindings

- boundary `f017-m1d-projection-boundary-v1`: `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`;
- activation payload: `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`;
- decoder `f017-q8-0-decoder-v1`: `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`;
- scaffold `f017-m1d-q8-0-sequential-f32-v1`: `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`;
- Tier-B `f017-production-m1d-projection-tier-b-v1`: `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`;
- repeat integrity `f017-m1d-repeat-integrity-v1`:
  `1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f`;
- oracle ordering `f017-m1d-oracle-ordering-v1`:
  `f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528`.

## Unambiguous provenance roles

- original activation generation source, commit `992081315073d8eb4eb31a2bb2f1b7b77b9c0ccd`:
  `29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984`;
- remediated fixture/finalization source, commit `d68cb10758693dc61d3af7cf76b8019f6b3b235d`:
  `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92`;
- real-reference preparer source, commit `d68cb10758693dc61d3af7cf76b8019f6b3b235d`:
  `bdcf8b999de5426872cb31f971b455028746959b30fb2bdf4c2f750f335b7fea`.

The finalization remediation changed metadata/order proof only. The original
and current fixtures contain identical 6,144 little-endian f32 activation
bytes at the bound activation SHA.

## Execution order and stop

1. validate the machine-readable binding and exact local environment;
2. exclusively create and finalize the independent real oracle/package;
3. validate and rehash the finalized package before candidate start;
4. execute exactly one conceptual projection with ten native repeats;
5. require ten ordinal hashes, exact equality, and ten native dispatches;
6. rehash the oracle after teardown, reconcile lifecycle/evidence, bank result;
7. stop before M1-E regardless of PASS or failure.

Any stale source, handoff, evidence, checkpoint, provenance, contract,
repeat-integrity, oracle-ordering, lifecycle, fallback, or numerical binding
fails closed. No automatic retry is authorized.
