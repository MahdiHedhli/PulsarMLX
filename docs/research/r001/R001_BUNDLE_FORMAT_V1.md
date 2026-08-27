# R001 Expert Bundle Format v1

## Object

One `.pmlxexp` file represents exactly one `(layer, expert_class, expert)`.
Canonical paths and ordering are layer ascending, routed before shared, expert
ascending; components are gate, up, down.

## Physical layout

- 16 KiB header block with `PMLXEX01` preamble and canonical metadata.
- Gate, up, and down payloads at 16 KiB-aligned offsets.
- Zero alignment padding.
- 16 KiB `PMLXEND1` integrity footer.
- Exact declared file length and no trailing bytes.

All integers are unsigned little-endian. Version 1 permits exactly one
contiguous source extent per component.

## Alignment

The live GGUF uses 32-byte alignment, APFS reports 4 KiB allocation and I/O
blocks, and Apple silicon uses 16 KiB VM pages. The file format selects 16 KiB
component alignment as a versioned layout choice. It does not claim Linux
`O_DIRECT`, cold-cache behavior, physical-flash placement, or required reader
buffer alignment. Every live plane length is already a multiple of 16 KiB.

## Identity and integrity

- Component SHA-256 covers exact unpadded source bytes.
- Canonical payload SHA-256 domain-separates and role-frames gate/up/down.
- Layout identity binds role, type, dimensions, and block geometry.
- Object identity binds checkpoint, inventory, plan, object key, provenance,
  ordered descriptors, and payload identity.
- Footer integrity covers header, physical payload including padding, canonical
  payload, object identity, and its own zeroed digest field.
- Completion manifest stores the full finalized-file SHA-256.

Canonical metadata uses the byte-exact `CJ-R001-1` profile: ASCII strings,
nonnegative minimal integers, booleans, sorted ASCII keys, compact separators,
no null/floats/whitespace/BOM/CR, and LF-framed JSONL records.

Known-answer hashes:

- Canonical JSON: `1dc821aa6759740ae41a6a3feb610416c797f785dd200bd508a0892173f68304`.
- Layout projection: `765aa7eadd6d8503feebdc5726d19e32703161bb202e207044b9296d5dbecacf`.
- Empty-object plan projection: `7cbae85aee9fcb77eae87af07705f4d291ed39cd16d91f4ecfa3194299446b35`.
- Object projection: `3c53884383faaedd1051ea0ae0a8f9092c6791617e77c616496ad72a0c67d674`.
- Canonical payload vector: `767a766d738dd34c2012ac9ec96a10908edefdff30805a6355901544313668d7`.

## Atomicity and resume

Temporary payloads are exclusive and adjacent. A synced, fully verified object
is published without overwrite, then its directory is synced. Final objects
are reused only after complete identity and hash verification. Partials are
never complete and never authorize deletion; matching graph-owned partials are
preserved under staging before a new attempt. Unknown or mismatching files fail
closed.

## Manifest

Canonical `manifest.jsonl` contains one header, sorted object records, and one
footer. It uses relative locators only. A pre-output manifest plan identity
prevents stale-scope resume; the completed manifest hash is separate to avoid
cycles and preserve relocation.
