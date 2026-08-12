# F017 M1-D package-root forensics

Status: checkpoint-free reproduction complete; semantic contract frozen before resolver changes.

## Failed attempt preserved

- Attempt: M1-D attempt 1
- Verdict: `REJECTED`
- Failure class: `FAIL_INFRASTRUCTURE_EVIDENCE`
- Failure code: `m1d_contract_read`
- Public evidence SHA-256: `a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62`
- Candidate checkpoint reads: 0
- Candidate projections: 0
- Production MLX dispatches: 0

The rejected evidence and its real-oracle hashes remain historical. This remediation neither overwrites attempt 1 nor reclassifies it.

## Exact failure

The projection package stored repository artifact paths such as
`specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json`.
The canonical runner used the parent of the private projection package as the
single generic resolution root. The resulting lookup was therefore:

`<private-package-root>/specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json`

instead of:

`<trusted-repository-root>/specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json`.

The failed source site was `crates/f017-runner/src/projection_boundary.rs` in
`validate_package`, at the `fs::read(root.join(&binding.path))` call.

## Checkpoint-free reproduction

The existing synthetic package and oracle were copied to a random directory
outside the repository, the runner was started with `/tmp` as its current
working directory, and the committed fake checkpoint manifest was used. The
unmodified runtime reproduced `m1d_contract_read` with projection and native
dispatch counters both zero.

The prior integration missed this because its package stayed in the committed
fixture directory and its `../contracts/...` strings accidentally resolved to
the repository contract directory.

## Frozen path model

The authoritative contract is
`specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json`.

It defines two non-interchangeable namespaces:

- `repository_relative`: resolve only from an explicit, canonical, Git-identity-verified repository root; verify the content hash before parsing or use.
- `package_relative`: resolve only inside the canonical private-package root; reject traversal and symlink escape; verify the content hash before parsing or use.

No resolver may fall back to the current working directory, package parent for
repository artifacts, or an unvalidated environment-variable guess.
