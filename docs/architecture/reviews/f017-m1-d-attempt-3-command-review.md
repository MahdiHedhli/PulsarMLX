# F017 M1-D Attempt 3 Command-Assembly Adversarial Delta Review

## Verdict

**GO FOR FRESH M1-D ATTEMPT 3 AUTHORIZATION**

Scope was limited to the attempt-2 command defect, command/path source of
truth, typed config, non-consuming preflight, immutable config binding, and
historical-attempt preservation. Frozen numerical semantics were not changed.

## Findings

1. **Can a human-assembled command silently diverge from the packet?** No. The
   only accepted runner form contains the config path and exact config hash;
   extra, duplicated, or reordered arguments fail closed.
2. **Can an alternate activation path with the same bytes pass?** No. The
   authorized repository-relative symbolic path is an identity field. The
   historical wrong path and a copied fixture both fail.
3. **Can cwd or environment change the launch?** No. Repository and package
   roots are explicit typed inputs. The relocation integration runs from an
   unrelated cwd, and local input documents reject added override fields.
4. **Can duplicate CLI arguments override a bound field?** No. The parser
   accepts exactly four config-only arguments and rejects every extra token.
5. **Does preflight prove the exact production config before checkpoint
   access?** Yes. It resolves and hashes every repository artifact, validates
   private metadata and target-shard identity without opening shard payload,
   round-trips the typed config, and emits `READY_TO_EXECUTE_ATTEMPT_3` with
   `checkpoint_accessed: false`.
6. **Is the exact execution config immutable/hash-bound?** Yes. It is created
   with exclusive-create semantics, made read-only, bound by SHA-256 in the
   packet, and rehashed by the runner before admission and after teardown.
7. **Are attempts 1 and 2 preserved?** Yes. Their evidence hashes are required
   fields and mutations fail validation.
8. **Is attempt 3 still unconsumed?** Yes. Preflight records
   `attempt_consumed: false`; only the future production transition consumes
   it.

## Delta safety

- command source of truth: closed
- activation path source of truth: closed
- duplicate/conflicting CLI behavior: closed
- preflight non-consumption: closed
- immutable config binding: closed
- synthetic relocation/cwd path: qualified
- real checkpoint access during remediation: false

Required fixes: none.
