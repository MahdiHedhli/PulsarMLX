# F017 Event 06 V12-to-V11 bridge design V2

This revision supersedes the descriptor and closure portions of design V1 while preserving its generation truth, sealed derivation, one-shot policy, and no-access plan.

## Exact numerical entry path

The bridge stores the exact nine-field descriptor identities already accepted by `validate_descriptors`, plus the exact six-record shard geometry required by the inherited target sources. The primary and secondary bridge adapters do not call `execute_target_and_bank` and do not fabricate a V11 candidate. Instead, each adapter validates its closed role view, calls the unchanged V11 descriptor-source constructor with a minimal source-authority projection (`shards`, `tensor_catalog_path`, `tensor_catalog_sha256`), then calls the unchanged V11 `execute_and_bank` function. Thus the exact historical V11 candidate validator remains closed, while the actual descriptor and numerical consumer signatures receive every required field.

## Event identity closure

The validated V12 installed authority supplies `event_identity_plan_sha256`. The separately validated execution plan supplies its own canonical digest, repeats that identity-plan digest, and carries the fresh primary and secondary event IDs. Bridge derivation independently validates the banked event-identity plan and requires equality of both IDs and the package attempt across all three authorities. Both `event_identity_plan_sha256` and `execution_plan_sha256` enter the bridge digest.

## Bridge-side transition closure

Closed V11 result, comparison, and accounting artifacts remain byte-for-byte unchanged. After bridge derivation, a V12 bridge-binding journal wraps the already durable package-start and identity-terminal SHAs before primary starts. Each later transition appends a closed eight-field record binding the bridge digest, package, exact subject artifact SHA, and predecessor binding. After the unchanged V11 package closure exists, its SHA is the final journal subject. A V12 package terminal then binds the bridge digest, the journal-chain head, the unchanged V11 closure root, and the accounting binding. It never includes its own SHA and is not a journal subject.

This produces transitive bridge closure without adding a field to any V11 schema. Reconstruction validates the unchanged V11 artifact with its historical validator, validates the adjacent V12 binding record, and walks the chain to the same bridge digest.

## Closed consumer views

The bridge contract enumerates the exact key census for primary numerical, secondary numerical, result bundle, comparison, release, accounting, and package-terminal views. Unknown, missing, aliased, or type-coerced fields fail before a consumer is called. Each view includes the bridge digest and only its role’s authority.

## Lifecycle correction

Lifecycle V3 adds an explicit durable-package-start phase covering exclusive creation, short write, write, fsync, directory fsync, readback, hash, and accounting failures. No descriptors exist in that phase. Identity failure releases exactly the acquired subset; every post-identity terminal path releases all five. No generic fallback, retry, or resume exists.
