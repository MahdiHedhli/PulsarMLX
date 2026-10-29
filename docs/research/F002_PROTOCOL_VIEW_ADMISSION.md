# Feature 002 protocol public-view admission v1

This admission separates the frozen experimental method from its redacted public
presentation. It changes no scientific rule, experimental version, seed, tolerance,
population, oracle identity, approval or recorded result. The cleanup changed only
notification presentation at original protocol lines 60 and 652. The historical
bytes remain in Git; they must never be copied into the public working tree.

The original 1.2 method retains its ID, version, path and SHA-256. Its immutable
protocol-specific source is commit `7721525af437a97a9ae733c4b8171e082205e5ea`.
The exact current public view has a different ID and digest. The small adjacent
JSON admission binds both representations and the cleanup commit. The validator
pins the admission's exact bytes, checks the current public file independently,
and resolves and hashes the original object locally. Missing Git objects refuse
validation; validation never fetches, substitutes a revision or prints old bytes.

Historical 1.2 records and their frozen-protocol artifact links remain unchanged.
Both checks resolve the original protocol from the admitted immutable pin. Legacy
1.1 records retain their existing declared-source resolution. Both paths also
check the admitted current view, so historical replay cannot hide public-file
tampering. Every unrelated artifact retains its exact current-byte validation.

Fresh synthetic fixtures and the directly coupled sanitizer use a shared producer
that actually verifies the historical object and current view before emitting an
original-method tuple with an additive `public_view` annotation. That annotation
identifies the distinct public bytes, admission digest, and both immutable sources.
The frozen-protocol artifact continues to identify the actual original bytes.
It is not a digest copied onto the current representation. Existing historical
records need no annotation or rewriting; newly built records must be truthful.

The envelope's closed schema gains only that optional, closed representation
annotation. Method, envelope and payload versions remain unchanged. Legacy 1.1
does not accept the new annotation. Unknown views, crossed hashes, wrong paths or
sources, relation mutation and inconsistent links refuse admission.

Local validation uses inspected host-only modules and fixture/package commands.
The consolidated workflow suite also contains a native-linked contract test and
must execute on the hosted runner. Required local Git inputs are the exact method
pin above and the retained 1.1 source declared by any legacy record under test;
no dependency installation or native execution is needed for this admission.

This document freezes the implementation design before the admission code changes.
