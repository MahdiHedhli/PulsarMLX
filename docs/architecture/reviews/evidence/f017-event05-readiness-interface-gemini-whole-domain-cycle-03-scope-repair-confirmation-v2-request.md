# F017 Event 05 readiness interface whole-domain cycle 03 final scope-repair confirmation

This is the final repair confirmation within whole-domain cycle 03, not a fourth challenge cycle. Use `gemini-3.1-pro-high`, high effort, a fresh detached read-only checkout, and committed bytes only. Begin with `git rev-parse HEAD`; every finding and the global verdict must bind that exact detached head.

Read `docs/architecture/reviews/evidence/f017-event05-readiness-interface-scope-repair-confirmation-packet-v2.json` and verify every listed SHA. Reconstruct `CHAL-03-BIND` and `CHAL-03-CI` from the exact prior response.

For `CHAL-03-BIND`, verify prepared declaration v5 and prepared runtime authority manifest v5 both bind `f017-event05-readiness-interface-full-native-ci-v6.json`, run `33044253965`, and that prepared production instantiability v5 passes both consumer validators with zero side effects. Verify the final-readiness path remains structurally separate and cannot consume prepared authority under a live approval.

For `CHAL-03-CI`, verify `test_repository_bound_artifacts_are_canonical_and_tree_exact` reads FULL_NATIVE v6 and measurement v7, binds the exact measurement SHA, and enforces `git rev-parse <implementation_head>^{tree} == implementation_tree`. Verify fresh exact-head FULL_NATIVE run `33046311031` at repair head `6c92a9ce876b39537ca1eb8f0c6161018180ba45`: 480 repository tests, 231 generated mutations, zero unexpected passes, zero required native skips, zero numerical/result drift, and zero checkpoint access.

Reattack all twelve readiness-critical claims. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Finish with counts for open blocking, open non-blocking-required, defense-in-depth, and unresolved findings, followed by exactly `NO_UNRESOLVED_MATERIAL_CHALLENGE` or `UNRESOLVED_MATERIAL_CHALLENGES`.
