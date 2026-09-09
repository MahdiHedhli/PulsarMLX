# Sequence54 primary observation qualification sources

These are retained copies of the fixed synthetic cases and independent oracle
used by the Sequence54 confined loader. They are **not** a standalone test runner
and must not be imported by ordinary unconfined CI, test discovery, or an
interactive executor session.

The authorized method initializes its declared standard-library closure, seals
the process, verifies actual read/write/network permission-denial fences against
independent positive controls, and only then imports the exact measured primary
code view and these helpers. Synthetic files are created/opened after the fences.
The archived Sequence54 harness, batch plans, captures, code hashes and results
are the execution evidence. Storage at these repository paths is not itself an
additional execution or qualification result.

`primary_cases54.py` is fixed dispatch; `primary_suite54.py` supplies tiny public
fixtures, actual read-call transcripts and real primary wrapper cases;
`primary_faults54.py` injects measurement-only faults and evidence mutations;
`observation_oracle54.py` independently checks counters and durable-prefix bytes.
The historical comparison baseline is source commit
`c23e58ec87c7e73a23cf37ac64aa4dee6c45896f`.

Scope is primary Python API observations and durable exception prefixes only.
The tiny real result writer's full-geometry refusal is not bypassed. Full-result
success, secondary/NumPy/native instrumentation, physical disk I/O and production
confinement are not qualified here. There is no checkpoint, retained Event06,
GO, replay, P1, live registry or ledger authority in these fixtures.
