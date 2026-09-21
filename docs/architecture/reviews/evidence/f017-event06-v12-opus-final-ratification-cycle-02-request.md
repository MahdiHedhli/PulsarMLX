# F017 Event 06 V12 final committed-byte ratification cycle 2

Use `claude-opus-5`, effort high, in a fresh detached read-only clone. Review exact committed bytes only. Verify HEAD `767266773e9c1551fbe9fc322abd1dcabd1ba92e`, tree `e12e35e819cf7955210778a772b86fb8fc6733c4`, and a clean worktree first. Do not modify files, access original checkpoint shards, mint Event 06 authority, execute Event 06, retry Event 05, or execute P1 attempt 2.

This is the final ratification after cycle 1 rejected and after whole-domain cycle 5 accepted the final hardening. Ratify the exact committed preparation bytes and independently verify every assertion.

Required final-byte surface:

- readiness declaration v12-v2, SHA-256 `33bf3456a7557a4be66bf534d117b8efb0cb82fd09b615acbf8e5a34e5a17e3d`, exact 47-field typed schema;
- authority manifest v9, SHA-256 `382c9bf657d4f55b2d7c3fa58227c9f159ff365eed5daaf0df46e082b5d9f0d2`, exactly 31 bindings;
- implementation measurement v7 at implementation head `5b98e53e6d9c4e2c2a8ae91bd71f55001517f5d0`, tree `e27590470ffb6ddf3885e8ae4e1a399e211aa27e`;
- measured readiness validator SHA-256 `d1ee8b80f7a6f9e778a7faffa8962a8795415db08b0c60308d01ee6650ba4bc8`;
- exact final instantiability v3, SHA-256 `57c44e0a201b89cd198581412cac50dcc2198b36c843204cfb757517ea64dd4b`;
- validation-only approval v2, SHA-256 `5b1f602b431242eedc7223083b27f4b191c7aa0f3034d661f2596ad12f2caa1b`;
- FULL_NATIVE run `33124907328`, PASS, zero required skips;
- final-declaration evidence-only run `33127220575`, PASS, native jobs zero;
- exact-instantiability evidence-only run `33127339764`, PASS, native jobs zero;
- Gemini canonical whole-domain result and Opus whole-domain cycle-4 zero-finding result directly referenced by the declaration;
- Opus whole-domain cycle-5 normalized acceptance and exact response additionally bound by manifest v9, covering the sole later execution-byte hardening.

Close every cycle-1 finding directly:

1. `B-1`: CI history v6 is append-only and covers the disclosed evidence-only lineage through the cycle-5 request; the two newer final-byte runs are the causal successors listed above and must be verified live and in this ratification.
2. `N-1`: producer callback capability is structurally absent. The exact producer signature is enforced, variadic and renamed callback surfaces fail, local regression v8 has 24 PASS, and FULL_NATIVE run `33124907328` covers the final implementation.
3. `N-2`: whole-domain cycle 5 reviewed the final execution-byte hardening at head `99b8cb08c31060caecb8cd532003f5699fd3c3b1` and accepted all sixteen readiness-critical claims. This final cycle reviews the exact declaration and instantiability successors.
4. `N-3`: raw qualification v1 is committed and byte-reproducible at SHA-256 `9c8b09e93da22ac5443683de0c696067e952fca187e0b61f9c4ef2adfe55ba7d`; successor qualifications bind both it and the exact qualifier script.
5. `U-1`: approval v2 and instantiability v3 expose the nonexistent checkpoint root, authorization ID, package ID, exact event-plan material and SHA, declaration path and SHA, builder SHA, validator SHA, implementation head and tree. Candidate SHA `94008a7d522d6216f05c92ffa7709c2941349db422680d2efe7e4f97812e6639` reproduces 20/20.
6. `U-2`: the final evidence-only runs are exact and successful as stated above.

Also verify:

- the real readiness validator accepts v12-v2 and rejects superseded v12-v1 SHA `eca5b5d3b56a019b03654987eab512951afc08c52d805540c53e8ce77e2cdf0d` before parsing;
- all declaration-to-manifest paths and SHAs resolve exactly;
- all 31 manifest bindings recompute;
- candidate triple is PASS for primary, secondary, and identity producer;
- installed-auth triple, receipt binding, capability, and package-start eligibility are PASS;
- validation-only side effects are all zero: state, live authority, checkpoint root and shard opens, identity reads, numerical operations, and consumed IDs;
- the cycle-5 non-blocking-required action is fully closed by instantiability v3;
- the declaration's direct cycle-4 Opus binding is the zero-finding result required by the typed validator, while manifest v9 additionally binds the later cycle-5 acceptance. Determine whether this causal dual binding is sound given that cycle 5 accepted all claims and required only the now-completed post-declaration instantiability step;
- numerical V4 and V11 result authority drift are zero;
- Event 05 remains terminal and non-retryable; Event 06 remains unexecuted with no live authority and no package start; original-checkpoint access remains zero; P1 attempt 2 is absent; historical ledger remains 175.

Return exact counts for blocking, non-blocking-required, and unresolved findings. Required verdict is exactly one of:

- `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION`
- `REJECT`

No conditional acceptance.
