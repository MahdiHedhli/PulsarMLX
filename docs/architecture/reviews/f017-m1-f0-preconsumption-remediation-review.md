# F017 M1-F0 Pre-Consumption Remediation Review

## Finding

The reviewed numerical preparer produced one oracle evaluation but did not
persist an exclusive `EXECUTION_STARTED` marker or the required ten-repeat
integrity record. The defect was detected before authorization-driven private
package access, so attempt 1 remained unconsumed and checkpoint reads remained
zero. The blocker is banked in
`evidence/f017-m1-f0-preconsumption-blocker-v1.json`.

## Minimal remediation

The independently reviewed preparer remains byte-identical at SHA-256
`ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d`.
The separate execution wrapper:

- validates the immutable config and authorization before private access;
- validates private-package metadata and the frozen input before consumption;
- creates one exclusive immutable execution marker;
- opens one shard and reads the exact twelve allowlisted ranges once;
- checks the accepted Q5_K packed and decoded identities;
- invokes the frozen independent oracle exactly ten times;
- rejects any stage-hash divergence or historical/synthetic route substitution;
- writes one immutable private oracle package for public evidence banking.

The banker independently re-derives repeat equality and access/isolation
invariants before creating the route, evidence, and append-only ledger.

## Internal implementation review

The delta does not change decoder, attention, router, selection, scaffold, or
numerical semantics. The exclusive marker is created only after every
non-consuming identity check and before the shard is opened. Tests cover
marker reuse, authorization omission/mutation, route substitution, and repeat
record completeness.

Verdict: `GO FOR NEXT M1-F0 ATTEMPT`

## Independent-style adversarial delta review

False-pass attempts considered: stale config, altered authorization, marker
reuse, expert-name injection, traversal/symlink escape, Q5_K identity drift,
repeat-stage divergence, and historical/synthetic route substitution. Each is
rejected before acceptance; none broadens the twelve-tensor oracle-only scope.

Verdict: `GO FOR NEXT M1-F0 ATTEMPT`

This review does not authorize M1-F and does not permit expert computation.
