# F017 M1-E Runtime/Authorization Identity Remediation

## Forensic reproduction

The pre-remediation config-only preflight failed before checkpoint access with
`m1d_repository_identity`: repository identity
`11a3a71653b136a47ca901bf8ea5a6e2430a677a` differed from compiled runtime
`942f23505e5829e55bc9b6611bd08d3c93481672`.

The failing comparison was in `TrustedRepositoryRoot::open`, which required
repository HEAD to equal the compiled runtime SHA. M1-D could use that model
because its executable checkout matched its reviewed execution head. The
later M1-E authorization status/evidence commits made that equality false even
though they did not alter executable semantics.

The complete old-runtime-to-old-authorization delta contained six files:
five docs/reviews and one immutable evidence JSON. Its deterministic
classification SHA-256 was
`8c22eaf8a16e9fc8e3c5bd14df7d54acd1a4d61488e7d9d70d9535758c6e5b48`.
No runtime compute, lifecycle, decoder, runner, resolver, tensor-store,
command/config, or attempt-consumption source changed.

## Identity contract v2

The replacement contract separates:

1. `compiled_runtime_sha`: embedded code identity of the executable.
2. `tooling_sha`: immutable execution-tooling/config-schema identity.
3. `authorization_head_sha`: exact Git commit of the trusted repository root.

The runner validates the compiled identity independently from repository HEAD,
requires compiled-runtime-to-tooling-to-authorization ancestry, rejects an
unexpected head, requires a clean canonical repository root, validates a
deterministic diff-classification hash, and directly hashes every
execution-controlling artifact before use. Only docs/reviews/evidence changes
are eligible between runtime and authorization head. All execution-relevant
categories require a new compiled runtime.

Contract: `f017-trusted-repository-identity-v2` / SHA-256
`88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`.

Schema: `pulsarmlx.f017.m1e-execution-config` `3.0.0` / SHA-256
`764dfa0a8e1a66ccbaecb5860d814440b2208902717fe13b2ce953eb56de490e`.

## Runtime attestation

- compiled/tooling SHA: `5c7694d6ba48640279e4725ea96104bc179a62cb`
- release executable SHA-256:
  `13900ecc2ea5b252c4a83b69ae04ee6b20916a7f3c0133c1b87c9a5c720b2bab`
- architecture: `arm64`
- build profile: `release`
- feature set: default production runner features

The executable identity is not inferred from Git HEAD. Loaded MLX library
identities remain part of production admission and are not replaced by this
repository check.

## Attack and compatibility disposition

Tests reject runtime, decoder, runner, resolver, or unclassified descendant
drift; wrong or unrelated heads; missing ancestry; dirty trees; stale
classification hashes; and artifact content mismatches. Exact-runtime,
docs-only, and evidence-only heads are eligible when all other bindings match.

M1-A/B/C and accepted M1-D evidence remain compatible historical evidence
under their then-current identity contracts and require no rewrite. M1-E
attempt 1 remains an immutable decoder-identity rejection; its pre-candidate
failure is unaffected. Attempt 2 remains unconsumed.

No real checkpoint payload, oracle, tensor decode, or MLX expert compute was
performed during this remediation.

## Rebuilt config and preflight

- authorization execution head:
  `f8a9910ca1c9242c2638556b0daee6a11949a090`
- permitted-delta classification SHA-256:
  `400ff607be3e4eb28b1d246c701abaf2140970bb4fdc269bcc1485f113a485d3`
- superseded config SHA-256:
  `4778a2694fd4a80feb5789ee3641dcd13fea3b2ba1d144dc150dde8af7d14cd7`
- rebuilt v3 config SHA-256:
  `a8905b8709aadf8d36bf94c2cb54c14a9ce5bcd31e7a1b184da33127af300f4e`
- canonical non-consuming result: `READY_TO_EXECUTE_M1_E`

The config points at a dedicated clean detached worktree at the exact
authorization execution head. Subsequent status-only authorization banking
therefore cannot silently move the execution root. Output targets for attempt
state, preflight evidence, oracle/package, and attempt evidence remained
absent after preflight.

The native synthetic expert integration passed with one conceptual expert,
10 deterministic repeats, and 30 native dispatches. M1-D native regression,
oracle-order failure injection, repeat-divergence injection, path/root tests,
and immutable-config tests passed. Internal and independent reviews both
returned `GO FOR M1-E ATTEMPT 2`.
