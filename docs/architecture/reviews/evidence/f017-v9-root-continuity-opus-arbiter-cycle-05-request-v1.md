# F017 V9 Root-Continuity Graph — Opus Arbiter Cycle 05

Review exact committed bytes at head `0b1d0389d2d9c5cb6fdfb3ad1b4af12e431a47f0` in a fresh detached read-only worktree.

Act as `claude-opus-5`, high effort, claim-by-claim ARBITER. Do not conditionally accept. Return one verdict for every one of the 25 readiness-critical claims: `ACCEPT`, `REJECT`, or `UNRESOLVED`, plus a global verdict of exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`.

The cycle-04 arbiter retained 23 claims and rejected only `C-JSON-005` and its dependent `C-IMPL-002`. Reconstruct cycle 04 from the exact response, challenge ledger v9, support ledger v8, claim ledger v10, authority manifest v11, implementation measurement v15, root/decode qualification v14, runtime qualification v14, rehearsal v15, and FULL_NATIVE evidence v9. Do not trust prose summaries over executable evidence.

Required attacks:

1. Re-run every cycle-04 bypass: dotted `import json.decoder`, aliases, `JSONDecoder.decode`, `raw_decode`, scanner, encoder, tool, object hooks, and scan functions.
2. Attack `from json.decoder import ...`, `from json.<submodule> import ...`, and `from <first-party module> import load` or `loads`, including aliases and bare callable invocation.
3. Attack `__spec__`, `__loader__`, `.loader`, `load_module`, `exec_module`, `create_module`, `get_code`, and `get_source`, including type construction and transported aliases.
4. Attack adjacent module-acquisition routes through other import-system objects, first-party packages, dotted imports, re-exports, capability-root traversal, `sys.modules`, `builtins`, `os.sys`, `operator.attrgetter`, `methodcaller`, `itemgetter`, `getattr`, globals, and transported dynamic builtins.
5. Attack `__defaults__`, `__kwdefaults__`, `__code__`, and `__closure__` transport and introspection.
6. Independently census every active-runtime decode capability and every direct or indirect `json.load`/`json.loads`/decoder call. Verify the canonical bounded parser and documented offline allowance are the only authorized sites.
7. Verify 122 focused tests, 167 combined active-authority tests, 204 decode attacks, 252 root attacks, and exact-head FULL_NATIVE run `32877227000`; verify EVIDENCE_ONLY run `32879422129` launched zero native jobs.
8. Re-run the decisive root-substitution, journal-corruption, fallback-unavailable, retained-handle, deep-artifact, and cross-product attacks supporting the 23 retained claims.
9. Verify exact measurement head `7cf77a00201c4a2c59de8e7b8b9c43e7624d34d1`, tree `3413da5437601ea50e43f4e0702e1de284b298dc`, all 43 measured bindings, numerical authority byte identity, original checkpoint access zero, Event-04 authority absent, Event-04 package start absent, Event-04 execution absent, and P1 attempt 2 absent.
10. Assess cycle-04 defense finding O-C04-005 separately. Reject a readiness-critical claim only if the currently banked measurement is false or cannot bind load-bearing bytes; do not convert a truthful forward-hardening suggestion into a present mismatch without executable evidence.

Use classifications `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Both blocking and non-blocking-required findings prevent global acceptance. Every rejected or unresolved claim must name its earliest invalidation node. Preserve accepted claims unless a new executable attack invalidates them.

Return machine-readable JSON containing:

- reviewed head and reviewer model;
- 25 claim verdict rows with evidence and invalidation disposition;
- findings with IDs, classification, attack, observed behavior, and required repair;
- accepted, rejected, and unresolved claim counts;
- Event-04 authorization/package-start/execution observations;
- original checkpoint access observation;
- P1 attempt-2 observation;
- exact global verdict.
