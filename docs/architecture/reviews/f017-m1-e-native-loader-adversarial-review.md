# F017 M1-E Native Loader Adversarial Review

**Verdict: GO FOR NEXT M1-E ATTEMPT**

The delta was attacked with an inherited alternate loader path, incorrect
`libmlx` and `libmlxc` hashes, missing pinned-installation metadata, an
unrelated working directory, and a no-`LC_RPATH` release executable. None can
silently select an unreviewed library. The manifest itself remains an
immutable execution-config artifact, and the runner independently verifies
the actually loaded library identities after launch.

The remediation cannot widen tensor access, change the expert, alter oracle
numbers, or consume an attempt during preflight. Attempts 1 and 2 remain
immutable and attempt 3 remains the next real attempt.
