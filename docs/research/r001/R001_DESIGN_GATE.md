# R001 Adversarial Design Gate

## Initial verdict

`REJECT`

The independent reviewer rejected underspecified canonical JSON, incomplete
hash projection schemas, unproved multi-extent support, overbroad semantic
decoder language, and an imprecise partial-owner protocol.

## Repair loop 1

The design froze:

- exact ASCII-only canonical JSON and JSONL framing;
- known-answer vectors for canonical JSON, layout, plan, object, and payload
  hash domains;
- literal projection schemas;
- a v1 restriction to one contiguous extent per component;
- semantic decoding as subordinate mapping sanity;
- a non-destructive sidecar/partial quarantine protocol;
- no-overwrite atomic publication.

## Final verdict

`ACCEPT`

The reviewer independently reproduced the known-answer hashes, confirmed the
live expert axis and coverage, found expert/component swaps detectable,
accepted the alignment and resume contracts, and admitted implementation. One
of two permitted repair loops was consumed.
