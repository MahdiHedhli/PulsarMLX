# F017 V2 Antecedent Recovery Evidence Review

Status: **ACCEPTED / INDEPENDENT ADVERSARIAL REVIEW REQUIRED**

## Scope and execution identity

The one authorized event ran from reviewed head
`493a087a4aafc28aee1e5933400ac77366521361` with execution-controlling
tooling commit `6b56dc88f89b92ebaeb525a35e48b3c2c1bc8fec`, tooling tree
`61eda4e19c57b0ddeea92a73468cbb5edff6019e`, final v2 contract
`36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7`,
and execution config
`649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2`.
The authorization SHA-256 is
`46c1f8e0ef0ee38aee5565ccf3f389a29266beba1bcca32a41848bacde6ab906`.

The event consumed the recovery authorization but did not consume an M1-F0
route attempt. It performed no new route selection, expert computation, MLX
candidate dispatch, Q6_K qualification, or M1-F execution.

## Identity and access review

All accepted-computation gates reproduced exactly, including the accepted
input and twelve packed/decoded tensor identities, attention output, attention
residual, router-normalized input, logits, probabilities, scores, ranking,
ordered top-8 bytes, and routing weights. The immutable raw result SHA-256 is
`f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a`.

Actual access exactly matched the authorization: one shard open, twelve
positional reads, twelve payloads, 139,217,920 compressed bytes, and
666,430,464 decoded bytes. Expert payloads, expert computation, MLX candidate
dispatches, and M1-F executions were all zero. The append-only cumulative
payload ledger advances from 45 to 57.

## Retention review

The public result retains all 256 logits, probabilities, biases, post-bias
scores, the 256-entry ranking, ordered selected IDs, unselected IDs, routing
weights, all 1,984 selected-versus-unselected pair bounds, and all seven
adjacent-selected pair bounds. The public-safe private manifest SHA-256 is
`1007112a0642919321d0081e79bba12fe3809c456e79a22b9623d19689b78112`.
It binds eight immutable private antecedents by relative symbolic identity,
shape, dtype, element count, byte length, source tensors, and SHA-256 without
publishing a machine-local path.

## Retrospective v2 review

Every membership pair passes the strict mathematical bound, but engineering
headroom fails. The worst membership pair is selected expert 177 versus
unselected expert 98: margin `0.003818698540044352`, bound
`0.003055557606453781`, and safety factor `1.2497550469932908`.

Ordered-selected stability fails. The worst adjacent pair is expert 233 versus
expert 177: margin `0.0006498095249156677`, bound
`0.0028814413437103334`, and safety factor `0.22551544432236478`. The global
minimum mathematical safety factor is therefore `0.22551544432236478`; with
reviewed engineering headroom H=2, the minimum engineering factor is
`0.11275772216118239`.

Retrospective statuses:

- Membership set: mathematically stable; no H=2 engineering headroom.
- Normative selected order: not mathematically stable; no H=2 engineering headroom.
- Exact ordered top-8: `NOT_MATHEMATICALLY_STABLE` / `NO_ENGINEERING_HEADROOM`.
- Historical v1 status: unchanged.

## Raw-summary amendment

The immutable executor result stopped its ordered stability scan at the first
failing adjacent pair and reused exact-ordered stability for its route-set
summary. Consequently, its overall failure classification was correct, but its
reported minimum factors were not global minima and its route-set sub-summary
was overly broad. The raw result remains unchanged. The checkpoint-free audit
recomputed summaries from every retained pair, added a regression test, and is
banked as
`docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-review-v1.json`
with SHA-256
`dd235d3e006e8721cf2f3decb1ea822c76cbce65a1660941661e7f68816f76ea`.
No checkpoint retry or execution-controlling change occurred.

## Verdict

The authorized analytical recovery is accepted: it reproduced the accepted
M1-F0 computation, retained the complete reviewed antecedent surface, and
reconciled access exactly. The retrospective v2 result does not qualify the
fixture for normative ordered-route use. M1-F, Q6_K, and P1 remain blocked.

Exact next action: independent adversarial review of the recovery evidence and
its checkpoint-free summary amendment.
