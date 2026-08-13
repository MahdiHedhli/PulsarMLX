# F017 M1-F0 Attempt 2 Pre-consumption CI Remediation Review

CI run `31753025028` failed before attempt consumption because the package
validator selected the historical attempt-1 config while the canonical
preflight selected attempt 2. The primary classification was
`EVIDENCE_VALIDATION`; checkpoint payload reads and route computations were
zero.

The validator now accepts an explicit repository-contained config path, CI
passes the same immutable attempt-2 path as preflight, and a subprocess
regression proves the alignment. Repository-root escape and stale-config cases
remain fail closed. No execution, oracle, decoder, selection, numerical, input,
or access binding changed.

Internal implementation review verdict:

`GO FOR NEXT M1-F0 ATTEMPT`

Independent-style adversarial delta review verdict:

`GO FOR NEXT M1-F0 ATTEMPT`

Apple-native CI `31753754835` passed at
`7ea94595f9003ed79ecdd188ad3cf643f530e089` before attempt 2 began.
