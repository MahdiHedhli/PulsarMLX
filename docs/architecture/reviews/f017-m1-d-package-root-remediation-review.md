# F017 M1-D Package-Root Remediation Review

## Verdict

**GO FOR FRESH M1-D ATTEMPT 2 AUTHORIZATION**

The narrow review covered only path namespaces, root derivation, content
binding, relocation/cwd independence, traversal/symlink defense, attempt-1
preservation, and fresh-authorization semantics.

1. Moving a private package cannot change repository artifact resolution.
2. Changing cwd cannot change resolution; there is no cwd fallback.
3. A stale file at the right path fails its content SHA-256.
4. Absolute, traversal, symlink, and canonical-containment escapes fail.
5. Typed package schema 2.0.0 prevents repository/package namespace confusion.
6. Attempt 1 remains rejected, consumed, and linked by evidence hash.
7. Attempt 2 requires a new explicit authorization.
8. Frozen numerical semantics are unchanged.

The canonical native integration copied package/oracle outside the repository,
changed cwd, then passed one conceptual projection with ten native dispatches,
ten identical hashes, valid oracle ordering, Tier-B qualification, zero
production scaffold/reference/fallback/errors, and reconciled lifecycle. The
one-bit repeat-divergence injection still failed as required.
