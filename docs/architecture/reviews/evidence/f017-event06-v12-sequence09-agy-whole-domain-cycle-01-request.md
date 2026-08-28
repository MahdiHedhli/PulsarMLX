# F017 Event 06 V12 Sequence 9 — independent whole-domain challenge

Review the exact committed repository bytes at the commit and tree named below. This is a CHALLENGE review, not an implementation task. Do not modify files, execute Event 06, create live authority, open checkpoint shards, run numerical inference, or contact external systems.

Reviewed commit: `695494ae2e2a68901a34504a9ea045483413ecb5`

Reviewed tree: `94ae1a5f045706f0ea6f59e11da07fbabca668a8`

Authoritative scope:

- Sequence 9 prompt SHA-256 `11c391452c32d3016c58ed034b8a30df5f073a28b655a000acd5b2c301274f49`.
- Freeze policy commit `e5ff7286047dfaeae5b4d0ecfb96c58bdc5b24f3`, SHA-256 `f442d2f2129bdb7fe8739244bd0745b1d843e83ec7f202e8d5822b24da8ff204`.
- Freeze Transition Table commit `0abe6601570a917c9a645f81d26a86071d779e68`, SHA-256 `9fd9db92c9c6c6c4a1e9f6f290d5bfa43bcbad989b84e6fb0555c17c0e74a754`.
- Q2 receipt `docs/architecture/reviews/evidence/f017-event06-v12-sequence09-freeze-transition-receipt-v1.json`.
- Q4 reproduction and five role artifacts named `f017-event06-v12-sequence09-*-qualification-v1.json`, `*-no-access-rehearsal-v1.json`, and `*-full-corpus-validation-v1.json`.
- Q5 FULL_NATIVE evidence `docs/architecture/reviews/evidence/f017-event06-v12-sequence09-full-native-ci-v1.json` for run `33193441295`.
- Source diff from `23c4c41540c6e780bb9d194f2b5f50f1ad75c892` through the reviewed commit.

Independently attack and mechanically verify:

1. the two Sequence 9 prequalification findings are actually resolved in runtime code, not merely declared resolved;
2. the real future-GO capability is the sole gate to production commit and no synthetic or direct-construction path can produce it;
3. the production wrapper owns a durable no-replace transaction with exact write/fsync/readback/rename/directory-fsync/reopen validation and faithful modeled failure outcomes;
4. the canonical readiness producer and the real consumer instantiate the same 86-field bytes, with aliases, type substitutions, stale bindings, and omitted fields rejected;
5. candidate/install/receipt identities and installation preparation are causally ordered and one-shot;
6. the qualifier installs access interposition before imports and proves zero checkpoint access, numerical operations, package starts, live authority, Event 06 execution, production success, and P1 attempt 2;
7. all 326 mutation cases, 16 installation outcomes, 10 race families, 6 sealed-token attacks, 11 future-GO rejection cases, 20 readiness reconstructions, and 20 installation reconstructions are substantive and fail closed as claimed;
8. generator and validator independence, all role schemas, cross-bindings, and the prepared 21-role manifest are coherent and cycle-free;
9. historical Event 05 and V11/V4/result authorities are unchanged;
10. FULL_NATIVE run `33193441295` is exact for the qualification head, both required native jobs passed, and required/unexpected skips are zero;
11. the implementation and evidence obey the Freeze Transition Table and do not prematurely operationally ratify readiness;
12. no authority exists to execute Event 06 in Sequence 9.

Return one JSON object followed by concise evidence notes. The JSON object must contain:

- `verdict`, exactly `NO_UNRESOLVED_MATERIAL_CHALLENGE` or `CHALLENGE_REQUIRES_REPAIR`;
- `findings`, an array of structured rows with stable ID, severity (`BLOCKING`, `NON_BLOCKING_REQUIRED`, or `ADVISORY`), claim, evidence, and required disposition;
- `counts` containing integer `blocking_findings`, `non_blocking_required_findings`, `advisory_findings`, and `unresolved_claims`.

Do not accept based on self-reported evidence alone. Recompute hashes and run safe synthetic validators/tests where useful. Any provider or filesystem limitation that prevents a material check is an unresolved claim, not an implicit pass.
