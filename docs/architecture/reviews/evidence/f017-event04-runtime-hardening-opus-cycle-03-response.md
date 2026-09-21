# F017 Event-04 execution-readiness final review — Opus cycle 03 response

Reviewer: `claude-opus-5`, high effort, fresh read-only session
`5a7117ad-1e9f-4bff-826e-564aa3a96db5`.

Reviewed evidence head `676ae3560b7acbd3489a5de52bfd359a024db4e7` and implementation head
`49628c1166b04f4f03ef3a5b0e0aff65ca711fec`, tree
`d6f24e5b7871a1fa398c5a2bd1c182a4b5bbe7bc`.

Independent reconstruction confirmed the banked qualification and rehearsal,
FULL_NATIVE run `32814639688`, evidence-only run `32815583882`, all twelve DID
closures, the 47/41/6/201 runtime census, 1,410 graph tensors, 399 non-access
tensors, unchanged numerical authorities, and zero original-checkpoint access.
Cycle-02 `B-01`, `N-01`, and `D-01` through `D-05` were closed or
substantively closed.

## Findings

### BLOCKING

None.

### NON_BLOCKING_REQUIRED

- `N-01-C03 ACCEPTED_IMPLEMENTATION_BINDING_MEASURES_A_COMMIT_OVER_AN_INCOMPLETE_PATH_SET_AND_NEVER_COMPARES_BYTES`:
  the mint path measured a Git commit over only 18 manifest paths. The actual
  runtime import closure contained 30 modules, including canonical
  serialization, lifecycle banking, decoder, and dequantization modules. A
  change to an unbound transitive module or an uncommitted change to a bound
  module did not invalidate candidate rendering.

### DEFENSE_IN_DEPTH

- `D-01-C03`: the irreversible installer did not replay the mint gates.
- `D-02-C03`: terminal roots were not compared to their authorized canonical
  strings before every write, permitting ancestor-symlink redirection.
- `D-03-C03`: two qualification counters were structurally constant rather
  than independent observations.
- `D-04-C03`: the no-authorized-root terminalization path skipped descriptor
  release by calling the evidence-banking release helper with `None`.
- `D-05-C03`: absent-root and Git-context errors retained raw exception
  classes at module boundaries.
- `D-06-C03`: maximal-constructible envelopes did not distinguish unauthorized
  roots from unusable roots.
- `D-07-C03`: partial installer root creation left opaque residue preventing
  reuse before any no-replace authority was consumed.

Gemini cycle 03 was accepted only at earlier implementation head `fd517315…`;
the reviewer recorded material disagreement with treating it as review of the
later bytes.

Verdict: `REJECT`.
