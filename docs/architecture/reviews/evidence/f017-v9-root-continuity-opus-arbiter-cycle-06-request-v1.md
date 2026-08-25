# F017 V9 Root-Continuity Graph — Opus Arbiter Cycle 06

Review exact committed bytes at head `573d9f803c5124d553762f05ded4b3a05418ee52` in a fresh detached read-only worktree.

Act as `claude-opus-5`, high effort, claim-by-claim ARBITER. Do not conditionally accept. Return one verdict for every one of the 25 readiness-critical claims: `ACCEPT`, `REJECT`, or `UNRESOLVED`, plus a global verdict of exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`.

Cycle 05 retained 23 claims and rejected only `C-JSON-005` and its dependent `C-IMPL-002`. Reconstruct cycle 05 from the exact response, challenge ledger v10, support ledger v9, claim ledger v11, authority manifest v12, implementation measurement v16, root/decode qualification v15, runtime qualification v15, rehearsal v16, and FULL_NATIVE evidence v10. Do not trust prose summaries over executable evidence.

Required attacks:

1. Re-run the exact cycle-05 bypasses through `pkgutil.resolve_name("json:loads")`, `pydoc.locate("json.loads")`, and every related string-keyed resolver.
2. Attack alternative import aliases and all newly unapproved imports. Verify the exact frozen active-runtime import-root allowlist rejects any root absent from current accepted bytes.
3. Attack module acquisition through `runpy.run_module`, `runpy.run_path`, `ctypes.pythonapi`, `modulefinder`, `inspect`, `ast.literal_eval`, `pickle`, `marshal`, `shelve`, and first-party transport or re-export paths.
4. Re-run every cycle-04 loader, dotted-json, bare imported `load`/`loads`, dynamic attribute, capability export, and introspection bypass.
5. Attempt new representation-independent routes to a genuine unbounded JSON decoder, including alternate decoders, subprocess/external interpreter surfaces, transported callables, globals, defaults, closures, class attributes, containers, and source-string resolution.
6. Independently census every active-runtime decode capability and every direct or indirect `json.load`/`json.loads`/decoder call. Verify the canonical bounded parser and documented offline allowance are the only authorized sites.
7. Verify the permanent parser-policy mutation census is exactly 97, the focused suite passes 145 tests, and the combined active root/runtime suite passes 190 tests. Confirm prior receipts' nonexistent test path and stale counts are superseded by R2 v10, R5 v10, and R7 v9.
8. Verify 204 decode attacks, 252 root attacks, all 47 modeled outcomes, runtime failures 201, runtime packages 50, and exact-head FULL_NATIVE run `32882085157`; verify EVIDENCE_ONLY run `32883636117` launched zero native jobs.
9. Re-run the decisive root-substitution, journal-corruption, fallback-unavailable, retained-handle, deep-artifact, and cross-product attacks supporting the 23 retained claims.
10. Verify exact implementation measurement head `443435f09cc5771828e298872ef8bb1b960e0239`, tree `f04d9ba3334f82b7d4319fd61e0658cf9b9b98ec`, all 43 measured bindings, numerical authority byte identity, original checkpoint access zero, Event-04 authority absent, Event-04 package start absent, Event-04 execution absent, and P1 attempt 2 absent.
11. Assess alternative decoder and external subprocess surfaces as defense in depth unless an executable current-byte path reaches an unbounded decoder or violates a readiness-critical claim. Do not convert a forward-hardening suggestion into a present mismatch without executable evidence.

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
