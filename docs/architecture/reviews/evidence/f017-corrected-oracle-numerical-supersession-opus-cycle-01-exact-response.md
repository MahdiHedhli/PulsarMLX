## F017 Corrected-Oracle Numerical-Authority Supersession — Opus Cycle 1

Reviewed exact committed bytes at `b691178` in detached read-only worktrees. Starting authority independently reconstructed from `84f0d1d` via `git show`/`git archive`.

### Independently verified as sound

1. The symbol inventory is complete and unique: primary 44, secondary 32, zero duplicates and zero unresolved symbols. Historical SHA-256 values match.
2. Both pure cores are free of checkpoint, authorization, lifecycle, file-I/O, access-event, and target CLI surfaces.
3. Both target sources contain authorization binding, identity-evidence reads, shard access, `pread`, tensor resolution, access events, and decoder dispatch, but no graph arithmetic.
4. Primary and secondary numerical independence is preserved. Per-symbol source comparison found historical and successor numerical expressions identical except the two declared row-matrix moves.
5. The complete qualification reran byte-identically: 24/24 historical/successor complete results, 44 decoder cases, all 11 formats, 16 mutations, and stable fresh-process runs.
6. The real parser, wrapper, target-source, and pure-core chain passed over six file-backed synthetic shards with `original_checkpoint_access: 0`.
7. Flattened contract comparison showed only schema, supersession, path/SHA repointing, and additive authority metadata changed; formulas, rules, thresholds, and top-N remained exact.
8. All ten superseded surfaces returned nonzero with `HISTORICAL_ONLY` and no worktree or state mutation.
9. Historical reconstruction uses immutable Git bytes; CI separates historical and current authority; active wrappers do not import retired scripts.

### Findings

`F1` — `NON_BLOCKING_REQUIRED`: the target-source arithmetic guard did not see class methods and omitted `matvec`/`transpose_mv`; a target `matvec` method could pass.

`F2` — `NON_BLOCKING_REQUIRED`: the validator did not enforce target-source, decoder, authority-binding, or requalification source SHAs, so materially rewritten target sources could still pass the static validator.

`F3` — `DEFENSE_IN_DEPTH`: the one-shot extraction helpers were stale and did not reproduce the committed successors.

`F4`–`F8` — `DEFENSE_IN_DEPTH`: a dead serialization helper in the pure cores; a narrow forbidden-import list; synthetic-root exclusion relying on the harness and inactive live generation; heavy qualifiers absent from CI; and missing secondary catalog-dimension checks.

No finding requires an intended formula change, threshold change, original-checkpoint access, or loss of primary/secondary numerical independence. Every required repair is validator, CI-binding, or provenance plumbing.

### Confirmations

Event 02 retry: no. Event 03 retry/resume: no. Event 04 authorization: absent. Event 04: unexecuted. Primary/secondary real executions: zero. Original checkpoint access: zero. P1 attempt 2: absent. Historical master ledger: 175.

`REJECT`
