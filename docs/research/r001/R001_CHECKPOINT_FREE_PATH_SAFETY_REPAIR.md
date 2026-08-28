# R001 Checkpoint-Free Path-Safety Repair

## Authority

- Sequence: F017 MacBook Pro M2 Max Sequence 15
- Starting R001 commit: `0a38f6c05816658b31d8a287d39d1df721a522ff`
- Starting R001 tree: `eaca9c4943b86b0eede11b7255e71717b88a860c`
- Repair commit: `e9c958a689a7e877ff40d5390d51a56167215fd8`
- Repair tree: `7ca1024c188a0f38b8c94a36f51bb26c332e91dd`
- Policy: `D6R1_PATH_SAFETY_REPAIR_AND_SYNTHETIC_ROUND_TRIP`
- Scope: checkpoint-free synthetic data only

## Counterexample

At the starting commit, a symlink substituted for the configured output root
was followed by the production bundle writer. A one-object fixture with 198
payload bytes wrote through the link. The counterexample failed as expected
and its owned temporary tree was removed exactly.

## Repair and trust boundary

The repacker now:

- opens configured roots as current-user-owned, non-symlink directories;
- pins each admitted directory by device and inode;
- traverses descendants with `openat` plus `O_DIRECTORY`, `O_NOFOLLOW`, and
  checked normal path components;
- creates children with `mkdirat` and files with `openat`, `O_EXCL`, and
  `O_NOFOLLOW`;
- enumerates partials from a duplicated directory descriptor;
- obtains metadata with `fstatat(..., AT_SYMLINK_NOFOLLOW)`;
- publishes with descriptor-relative `linkat` and removes with `unlinkat`;
- checks the opened inode before linking, the resulting inode after linking,
  and the original inode immediately before removing a temporary name;
- revalidates pinned path identity at every publication boundary;
- rejects aliased or nested output/staging roots, unsafe relative paths,
  symlinks, wrong types, multiply linked mutable files, and conflicting
  objects.

The security boundary begins at each configured root. Ancestors are trusted
configuration authority. The roots are current-user-owned and exclusively
controlled by the graph lease; the design does not claim protection from an
arbitrary hostile process running continuously as the same user outside that
exclusive-ownership contract.

Darwin does not permit directory traversal through `/dev/fd/<directory-fd>`.
The final implementation therefore uses descriptor-native `fstatat`,
`fdopendir`/`readdir`, `openat`, `mkdirat`, `linkat`, and `unlinkat` rather than
compatibility paths.

## Qualification

Commands:

```text
rustfmt --edition 2021 --check crates/repack/src/lib.rs
cargo test -p repack --lib
cargo clippy -p repack --all-targets -- -D warnings
uv run --with pytest python -m pytest -q scripts/research/tests/test_r001_verify.py
git diff --check
```

Results:

- Rust repack tests: 30 passed, 0 failed, 0 ignored.
- Independent Python verifier tests: 6 passed, 0 failed.
- Repack clippy with warnings denied: passed.
- Touched Rust file format check: passed.
- Diff whitespace check: passed.
- Complete-scope plan: 19,532 objects and 58,596 components.
- Complete-scope plan identity:
  `350ee7d581b425658f800c96cc877abdebd56e945a560d615ddfb38091b8f75a`.

The deterministic path matrix covers root symlinks, dangling roots, wrong root
types, aliased/nested roots, intermediate symlinks, root replacement, entry
substitution, existing final symlink/file/hard-link targets, abandoned-root
symlinks, summary-parent symlinks, unsafe relative forms, and unexplained
partial hard links. Each rejection preserves outside and unexplained bytes.

The round trip uses one synthetic routed object with exact gate/up/down
components and 198 canonical payload bytes. It exercises `build_plans`, the
production bundle writer, bundle verifier, reuse/source reconciliation,
partial quarantine, and manifest publication directly without calling the
production CLI or authority loader.

Known answers:

- Stored bundle SHA-256:
  `0acf896dcbef305bce581b7b182351590ed74286a3d741d519485df74f23db80`
- Canonical payload SHA-256:
  `0b52f43809ff751645664addadd1912ad19a8e6846b4a35d07713fef4d8693ef`
- Object identity SHA-256:
  `4af52a251fed6bdffa64a2a8bf1c806014b2b4c23acad532e6a68f90cbc438fb`
- Manifest SHA-256:
  `fe8ef7c82b436f842cf08b0ca64036538adedf203f31033d3ba0e109b36e6ab4`

Two independent fresh fixtures produced identical bundle, manifest, detached
hash, payload identity, and object identity bytes. Unchanged reuse preserved
the existing bundle without overwrite. Header, payload, padding, footer,
truncation, append, plan, source, and manifest conflicts failed closed.

Injected copy interruption left one owned partial/sidecar pair. A run without
explicit resume rejected it. Explicit resume quarantined the pair and restarted
the object from byte zero; this is not byte continuation. Injected interruption
after manifest publication left no detached hash, and the next run repaired
only that hash.

## Safety census

- F017 checkout accessed: no.
- Original checkpoint root resolved: no.
- Original checkpoint metadata, hash, and payload reads: zero.
- Production repack CLI execution: none.
- Production or full-store repack: none.
- Full-model inference: none.
- Event 05 retry/resume: none.
- Event 06 execution/launch: none.
- P1 action: none.
- Mac Studio action: none.

All generated source bytes, bundles, manifests, sidecars, and quarantine data
were tiny synthetic test artifacts beneath uniquely owned OS temporary roots.
Fixture destructors removed those roots by exact ownership after each test.
