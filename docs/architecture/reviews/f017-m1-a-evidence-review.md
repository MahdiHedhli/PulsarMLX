# F017 M1-A Evidence Review

## Verdict

**M1-A ACCEPTED**

Exactly one `--adapter-preflight-only` execution ran at source
`42506d75b6b10d6fe3c1d804175f5dc5c9c69f45`. It completed on its first
attempt. No retry, checkpoint argument, checkpoint access, tensor read, tensor
decode, or tensor execution occurred.

## Evidence identity

- Public-safe evidence:
  [`evidence/f017-m1-a-adapter-preflight-v1.json`](evidence/f017-m1-a-adapter-preflight-v1.json)
- Raw local evidence SHA-256:
  `d59a3c1ebe383b880e08ed7d5eff9380ef4544fa2244f41eaf255992c50d4df1`
- Public artifact SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- Environment-manifest SHA-256:
  `33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251`
- Environment kind: `production_reviewed`
- Architecture: `arm64`

The public artifact is a formatting-only copy of the canonical JSON object;
its semantic content is identical to the raw local evidence. It contains no
machine-local path.

## Frozen review questions

### Was the environment production-reviewed?

Yes. The runner accepted only `production_reviewed`; the exact reviewed
manifest hash is recorded and the source worktree was clean.

### Were the actual libraries verified?

Yes. Dyld-resolved `libmlx.dylib` and `libmlxc.dylib` were both arm64 and their
actual hashes exactly matched the reviewed expected hashes:

- MLX native 0.31.2:
  `6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed`
- MLX C 0.6.0:
  `a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62`

### Was telemetry measured?

Yes. `telemetry_source` is `measured_host`:

- physical memory: 137,438,953,472 bytes;
- available memory: 83,626,033,152 bytes;
- required floor: 17,179,869,184 bytes;
- memory pressure: normal;
- swap used: 125,829 bytes;
- evidence-volume free: 384,553,979,904 bytes;
- competing processes: none;
- port 1234 listener: false;
- thermal state: normal;
- performance warning: false.

### Was checkpoint access truly zero?

Yes. Adapter-preflight CLI validation accepts no checkpoint argument and its
mode has no checkpoint dispatch. Evidence records:

- `checkpoint.accessed: false`;
- no shard identities;
- storage read bytes/count: 0/0;
- no layers or generated token;
- direct/tensor dispatch count: 0.

### Did lifecycle reconcile?

Yes:

- managed: 1 created / 1 destroyed;
- derived: 1 created / 1 destroyed;
- callbacks: 1;
- default CPU streams: 2 created / 2 freed;
- default GPU streams: 0 / 0;
- owned streams: 2 created / 2 freed;
- active contexts: 0;
- singleton claimed after teardown: false;
- registration, pending-destruction, in-flight, owner-token, and generation
  domains: explicitly `not_applicable`, not fabricated measured zero;
- `lifecycle.reconciled: true`.

### Did any hidden fallback/reference/scaffold path occur?

No. Dispatch was one native adapter preflight and zero direct, scaffold,
explicit-reference, fallback, or error dispositions.

### Is M1-B meaningful to run next?

Yes, as a separate identity-only gate. M1-A proves the reviewed environment,
actual MLX linkage, host admission, production adapter lifecycle, exclusive
evidence path, and teardown behavior on the M1 Ultra. It does not prove any
checkpoint identity. M1-B remains unexecuted and requires a separate explicit
authorization.

## Validation disposition

The banked artifact is parsed with duplicate-key rejection and passed the
canonical `Evidence::validate` and `Evidence::validate_success_ready` gates.
The repository test also freezes its public SHA-256 and zero-checkpoint/zero-
fallback assertions.

M1-A is accepted. Stop before M1-B.
