# F017 Event 06 V12 identity-authority design CHALLENGE cycle 2

Use `gemini-3.1-pro-high`, effort high, exact committed bytes only. Read the Event 05 terminal package, V10 producer, V11 coordinator, V12 authority design, V12 lifecycle design, graph state v2, and support ledger v2. Do not modify files or access checkpoint shards.

First reconstruct the exact Event 05 failure: V11 supplied `PRODUCTION_EVENT_05`; V10 producer admitted only `SYNTHETIC_QUALIFICATION` or `PRODUCTION_EVENT_04`; it raised `ValueError("checkpoint identity producer authority")` before any shard open. Do not invent cryptographic keys, caches, networking, concurrency, signatures, certificates, heaps, daemons, or other absent surfaces.

Create one evidence-backed challenge row for each exact claim ID: C-SCOPE-001, C-SCOPE-002, C-INTERFACE-001, C-VALIDATE-001, C-VALIDATE-002, C-VALIDATE-003, C-RUNTIME-001, C-RUNTIME-002, C-FAIL-001, C-FAIL-002, C-FAIL-003, C-HIST-001, C-SYN-001, C-NOACCESS-001, C-CI-001, C-GO-001. Every row must cite a committed path and line/key. Distinguish design-supported claims from claims that remain proposed until implementation. Challenge event-number smuggling, alias/coercion acceptance, candidate/installed divergence, package-start bypass, stale-report replay, producer/checkpoint drift, generic fallback, historical mutation, and validation side effects only where committed bytes support the attack.

Return counts for supported design claims, repairable design findings, implementation-required claims, unresolved material findings, blocking findings, and non-blocking-required findings. The acceptable design-review outcome is not blanket acceptance: implementation-required claims may remain proposed, but no material design contradiction may remain.
