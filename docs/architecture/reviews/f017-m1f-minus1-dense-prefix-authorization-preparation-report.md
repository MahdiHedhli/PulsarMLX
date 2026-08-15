# PulsarMLX F017 M1-F(-1) Dense-Prefix Authorization Preparation Report

## Disposition

`BLOCKED — QUALIFIED REUSE`

The checkpoint-free preparation audit independently regenerated the exact
40-tensor boundary and the proposed 38-entry new-read partition, but it did not
create `DPREFIX-REAL-1`. The accepted Q4_K and Q6_K qualification artifacts
prove exact decoder truth and record packed/decoded hashes; they do not bind a
resolvable immutable private package containing the canonical bytes required
for cross-event reuse.

Treating those hash-only descriptors as payloads would violate the reviewed
separate-package reuse policy. Automatic reread fallback is forbidden, so the
execution config, authorization binding, and attempt ledger entry remain
absent.

## Reconciled state

- Starting head: `1f494fcd0d890797fadb4ac898d794ac02b7fa99`
- Real-payload ledger: `59`; unchanged by this audit.
- Q4_K evidence: `035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994`.
- Q6_K evidence: `375e6b852733e8ac885d53c3814a03deb3a80e639bf61d427f1e49f1aae57086`.
- Prompt package: `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff` (`Hello`, token 9703, position 0, `range_fill([0])`).
- Inventory: 40 tensors, 1,431,263,232 packed bytes, 8,504,653,824 aggregate decoded-f32 bytes; F32 12, Q8_0 12, Q5_K 12, Q6_K 3, Q4_K 1.
- Proposed 38-entry ordered allowlist identity: `3adfb54fa9460bbfd0358ae3d1cdcf0e92a86e2feb0e3a8a8f9828a17f9e495b`.
- Proposed remaining packed bytes: 834,066,432, derived by summing the 38 entries.

The 38-read arithmetic and hypothetical `59 -> 97` transition are valid only
if both reused components exist as independently validated immutable packages.
They are not execution authority.

## Load-bearing blocker

Both real qualification artifacts omit the private package identity, private
manifest SHA-256, package-relative packed/decoded names, creation ordinals, and
an immutable/read-only enforcement binding. A local filesystem search also
found no matching retained canonical file, but the stable repository blocker
is the missing cryptographic package binding: an unrecorded local path would
not be admissible even if later discovered.

Canonical preflight disposition:

`NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID`

No checkpoint path was opened, no payload was read, dense prefix was not
executed, and representative M1-F0 remains blocked.

## Preserved numerical and execution contracts

No dense-prefix numerical semantics changed. The independent oracle contract
remains `0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`;
Tier-B remains `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`;
the 27 GiB residency derivation remains
`56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76`.
The repeat, dispatch, lifecycle, retention, and future representative M1-F0
contracts were not widened or authorized.

## Internal review

Verdict: `NO-GO`.

1. All five quantization families in the inventory are real-byte qualified; IQ3 lineage is qualified where used by accepted F017 gates but is absent from this inventory.
2. Q4/Q6 cross-event reuse is not presently instantiable.
3. The proposed remaining count is exactly 38.
4. `59 -> 97` is conditionally exact, not currently authorizable.
5. The independent oracle contract is unchanged, but no real oracle package was created.
6. Tier-B remains pre-observation and unchanged.
7. The reviewed 27 GiB floor remains unchanged; no host admission was attempted.
8. Candidate/runtime isolation from oracle truth remains required.
9. Lifecycle accounting remains unchanged.
10. Hidden-state retention remains sufficient as a schema, but no hidden state exists.
11. Nothing can auto-chain: no attempt or authorization was created.

## Exact next action

Independent review of the qualified-reuse blocker, followed by a separately
authorized decision between recreating reviewed immutable Q4/Q6 reuse packages
or revising the future dense-prefix event to an explicitly reviewed 40-read
budget. Neither action is authorized here.

## Validation and final-head CI

- Preparation commit: `0d956229dd7566a19192ae2e73edc1b9daf99527`.
- Local clean-tree validation: `cargo check --workspace --all-targets`, full Rust workspace tests, 702 Python research/evidence tests, focused blocker mutations, JSON/duplicate-key/privacy checks, ledger validation, and `git diff --check` passed.
- Apple-native CI: run `31910532571` passed against exact preparation commit `0d956229dd7566a19192ae2e73edc1b9daf99527`.
- Apple Silicon workspace baseline job `95074785193`: passed.
- Apple MLX small-fixture validation job `95074785054`: passed, including the checkpoint-free dense-prefix authorization blocker regression.
- Real checkpoint access: `0`; ledger remains `59`.
