# F017 Dense-Prefix, Decoded-Reuse, and Colibrì Adversarial Packet

## Phase boundary

This packet requests review only. It authorizes no checkpoint read, decoder
qualification, dense-prefix execution, route discovery, M1-F, M1-G, P1, or
Feature 018 work. The real-payload ledger is 57.

Review the package consisting of the existing dense-prefix preparation report
and contracts, the decoded-reuse use-case amendment, the pinned Colibrì audit
and risk/adoption evidence, the new independent regressions, and the combined
internal review.

## Questions for the reviewer

1. Is decoded reuse safe for each of the seven named use cases?
2. Does the separate-package policy preserve candidate/oracle independence?
3. Is the Colibrì audit pinned, scoped, Apache-2.0-aware, and non-copied?
4. Did the audit yield valid generic numerical regressions without treating Colibrì as an MLX oracle?
5. Is `M1-F(-1) REAL DENSE PREFIX` the minimal representative-state boundary?
6. Is the P-MIN/token-9703 selection demonstrably anti-cherry-picking?
7. Are all 40 tensors, family counts, and byte budgets correct?
8. Is peak residency derived from lifetimes rather than aggregate volume or current host availability?
9. Is the independent NumPy oracle complete and sufficiently isolated?
10. Is one mechanically selected Q4_K real payload enough to qualify its exact format contract?
11. Is one mechanically selected Q6_K real payload enough to qualify its exact format contract?
12. Is Q4_K → Q6_K → dense prefix the correct separately authorized sequence?
13. Are attempt consumption and hypothetical ledger transitions fail-closed?
14. Does private canonical hidden-state retention prevent another analytical-recovery gap?
15. Does representative M1-F0 bind only the accepted dense-prefix state and stop on H=2 failure?
16. Which exact single real-access event, if any, should be authorized next?

## Requested verdict

Return exactly one:

- `GO FOR ONE Q4_K REAL-BYTE QUALIFICATION`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO authorizes consideration of a separately explicit execution instruction;
this packet itself does not execute or authorize the event.
