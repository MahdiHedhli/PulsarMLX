# F017 Event 06 V12→V11 Bridge — Opus Design Arbitration

## Independent reconstruction

The parent failure was reproduced from in-tree bytes. V12 candidate and installed authorities enforce 28 and 30 fields. Both V12 wrappers import the exact V11 execution function. The V11-required fields are absent, the candidate-schema intersection is empty, and the V12 coordinator has no numerical graph. Both wrappers fail with the recorded V11 candidate-authority errors. Parent failure, no-go, terminal manifest, design bindings, and immutable runtime bindings were hash-verified.

## Findings

### FINDING-A — BLOCKING — descriptor-record census reproduces the parent defect one layer down

Claims: `C-BRIDGE-CALLPATH-001`, `C-BRIDGE-PROV-001`.

The bridge contract fixes a closed six-key descriptor record, while the unchanged V11 numerical consumer requires the nine keys enforced by `f017_descriptor_lease_manager_v10.py`: `ctime_ns`, `device`, `inode`, `lease_id`, `mode`, `mtime_ns`, `role`, `shard_ordinal`, and `size`. The bridge record misses five required keys, adds two incompatible keys, and the document contains no `shards` array needed for descriptor-size validation. Contract-shaped records fail with `ValueError: descriptor key census`.

### FINDING-B — BLOCKING — digest binding conflicts with the drift prohibition

Claims: `C-BRIDGE-DIGEST-001`, `C-BRIDGE-DRIFT-001`.

The design requires each result, comparison, accounting, and terminal transition to bind the bridge digest, but the named V11 artifacts are closed-key schemas with no bridge field. Adding the field would change V11 result-authority bytes, which is prohibited. No separate bridge-side durable binding journal was defined.

### FINDING-C — REQUIRED — event-identity provenance is not closed

Claim: `C-BRIDGE-PROV-001`.

Primary and secondary event IDs enter only from the execution plan. The bridge omits both the V12-installed `event_identity_plan_sha256` and the execution plan’s own digest, so no equality edge closes event identity provenance.

### FINDING-D — REQUIRED — durable package start has no failure outcome

Claim: `C-BRIDGE-LIFE-001`.

Lifecycle V2 assigns neither torn nor failed durable package-start writes. The package gate is before start and identity assumes a later prefix. With generic fallback prohibited, that seam has no truthful outcome.

### FINDING-E — REQUIRED — role views have no closed censuses

Claim: `C-BRIDGE-DIGEST-001`.

Seven views are named, but no per-view field census is enumerated. Least-authority view enforcement is therefore unfalsifiable.

Advisory: the design authority manifest remains bound to superseded lifecycle and ledger versions.

## Claim verdicts

| Claim | Verdict | Invalidation disposition |
|---|---|---|
| `C-BRIDGE-GEN-001` | ACCEPT | No laundering vector found |
| `C-BRIDGE-PROV-001` | REJECT | Bind event/execution plan digests and use a consumer-compatible descriptor census |
| `C-BRIDGE-DIGEST-001` | REJECT | Define bridge-side durable binding journals or change forbidden V11 schemas |
| `C-BRIDGE-LEGACY-001` | ACCEPT | Closed in both directions |
| `C-BRIDGE-CALLPATH-001` | REJECT | Exact consumer signatures reject the descriptor census and lack shards |
| `C-BRIDGE-LIFE-001` | REJECT | Add a durable-package-start failure phase |
| `C-BRIDGE-CAP-001` | ACCEPT | Capability census is sound, subject to call-path repair |
| `C-BRIDGE-DRIFT-001` | ACCEPT | All six immutable runtime bindings verified with zero drift |

Five accepted, four rejected, zero unresolved, two blocking, three required.

## Global verdict

`REJECT`
