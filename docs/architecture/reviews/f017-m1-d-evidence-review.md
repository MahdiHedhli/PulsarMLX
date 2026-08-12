# F017 M1-D Real Projection Evidence Review

**Verdict: M1-D REJECTED**

Date: 2026-08-12

## Binding

- Runtime: `d68cb10758693dc61d3af7cf76b8019f6b3b235d`
- Immutable tooling/validator: `15c0de64c342cb5541e643f5e212d2cf5d73da67`
- Authorized repository head: `12dfb226fe16b1f68fe08ad53eaca061e988eb4e`
- Handoff SHA-256: `eff56978ed066527dd9e42689b23c4f7a033b4f0dd5ed1815ee001d95bc5d789`
- Public attempt evidence SHA-256: `a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62`

The pre-access gate verified the bound M1-A/B/C evidence, checkpoint/catalog/map,
boundary, activation, decoder, scaffold, Tier-B, provenance, authorization, clean
remote parity, and final-head CI. Production admission passed with measured host
telemetry and exact loaded MLX identities.

## Oracle preparation

The independently bound preparer read exactly the authorized Q8_0 matrix range
for `blk.0.attn_kv_a_mqa.weight` and finalized the local-only oracle before the
candidate process:

- matrix payload SHA-256: `ff2b6a0e14f3e180ba6a8a8522ef4569c9cb82a0f10708f66da794305e3ee4cc`
- activation SHA-256: `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`
- finalized oracle SHA-256: `ac31bb18a3a14465c4a9bb4bb856aee062a05a7430e25a04ecbc613527056168`
- finalized package SHA-256: `beb16d98df24b15e99c4a80b9c40200bcca2238b9d88c29cf17c2b9532c48f7e`
- reference output SHA-256: `2e0add595e590ec1befec21402d059cb73ebcc6f0c63029e36901b4b6db8d96b`
- bound-vector SHA-256: `c1efe56ffabf38d0a413f9e901a886b59730111c43a7644e560ec451b9c6b2a7`

The oracle and package were fresh, mode `0400`, independently validated, and
retained outside the repository. No raw checkpoint bytes or private absolute
paths are present in the public attempt evidence.

## First failure

The exactly-once canonical candidate process failed before package validation
completed:

- classification: `FAIL_INFRASTRUCTURE_EVIDENCE`
- code: `m1d_contract_read`
- message: `No such file or directory (os error 2)`

The production runtime resolves each contract binding relative to the package
directory. The finalized private package carried repository-relative contract
paths, so `root.join(binding.path)` pointed beneath the private artifact
directory instead of the reviewed runtime worktree. The contract files and
their hashes are present in the runtime worktree; this is a package-path
composition defect, not a numerical result.

## Isolation and lifecycle disposition

- Authorized real oracle matrix payloads: exactly one.
- Candidate checkpoint reads: `0`.
- Candidate quant decodes: `0`.
- Candidate production projections: `0`.
- Native/scaffold/reference/fallback/error dispatches: `0/0/0/0/0`.
- Expert/layer/logits/P1 executions: `0/0/0/false`.
- Production repeats and repeat hashes: `0`; the numerical gate was never
  entered.
- Managed/derived/callback/stream/context counters remained zero. The failure
  evidence correctly does not claim successful lifecycle reconciliation.

The oracle package was finalized before the candidate process, but the runner
stopped before recording its candidate-start/oracle-order evidence fields.
Accordingly, no oracle-order PASS or numerical classification is claimed.

## Review answers

1. Exactly one real matrix payload? **Yes, for independent oracle preparation.**
2. Oracle finalized before candidate? **Yes, locally; candidate-side structural
   validation did not complete.**
3. Oracle independent? **Yes.**
4. Exact activation/decoder/scaffold/Tier-B bindings used? **Bound and verified
   before launch; candidate contract loading failed before use.**
5. Canonical production MLX path genuine? **Not reached.**
6. Exactly ten repeat hashes? **No; zero repeats.**
7. All ten identical? **Not applicable because execution did not start.**
8. Tier-B passed? **No result.**
9. Fallback/backend errors zero? **Yes; no dispatch occurred.**
10. Lifecycle reconciled? **No PASS claim; execution stopped before lifecycle
    creation and reconciliation.**
11. Oracle package unchanged after teardown? **The candidate never entered the
    production lifecycle; the retained package hash is unchanged.**
12. Is one complete real expert meaningful now? **No. M1-D remains blocked.**

The authorization is consumed. There was no retry. M1-E is not prepared and
remains blocked. A new reviewed package/path-semantics remediation and fresh
explicit M1-D authorization are required before another attempt.
