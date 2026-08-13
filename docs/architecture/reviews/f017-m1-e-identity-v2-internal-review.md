# F017 M1-E Identity v2 Internal Implementation Review

## Scope

This review is limited to compiled-runtime identity, authorization-head
identity, Git ancestry, runtime-drift classification, executable attestation,
trusted-root semantics, dirty-worktree handling, and immutable config binding.

## Findings

- Compiled runtime identity is embedded and validated independently of HEAD.
- Tooling and authorization head are distinct semantic fields.
- Exact authorization head and ancestry are mandatory.
- Descendant runtime/decoder/runner/resolver drift fails closed.
- Exact artifact SHA-256 checks remain authoritative.
- A stale binary with a correct checkout fails compiled identity or executable
  hash validation.
- A correct binary with a wrong checkout fails exact-head validation.
- Dirty repository state fails closed.
- Attempt 2 is not consumed by config-only preflight.
- The historical M1-D resolver remains available only for its immutable
  historical config; M1-E v3 cannot silently fall back to it.

## Verdict

GO FOR M1-E ATTEMPT 2
