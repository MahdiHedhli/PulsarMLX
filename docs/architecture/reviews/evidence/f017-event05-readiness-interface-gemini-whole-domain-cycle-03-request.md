# F017 Event 05 readiness interface whole-domain CHALLENGE cycle 03

Review the exact detached committed HEAD. Begin by returning `git rev-parse HEAD` and require it to equal the checkout you inspect. Review committed bytes only, read-only, with model identity `gemini-3.1-pro-high` and high effort.

Primary packet: `docs/architecture/reviews/evidence/f017-event05-readiness-interface-whole-domain-review-manifest-v2.json`.

This is the final Gemini whole-domain cycle. Re-test both cycle-02 challenges directly:

1. `AUTHORIZER_CANDIDATE_FORGERY`: verify the live installation boundary revalidates approval and readiness, rebuilds the candidate through the shared builder using fixed production catalog authority, compares exact canonical bytes/digest, protects candidate bytes against pre-install and during-install mutation, and fails before install with zero side effects.
2. `LIVE_CANDIDATE_UNINSTANTIABLE`: independently determine whether the accepted two-phase lifecycle intentionally requires `live:false` in candidate bytes until exclusive installation and an installation receipt establish authority. Do not demand a `live:true` candidate if the measured parser and lifecycle forbid it.

Attack every readiness-critical claim: exact schema/types and alias rejection, manifest/measurement/CI bindings, one canonical validator, absence of parallel readiness logic, shared candidate construction, validation-only isolation, historical supersession, 227 substantive mutations, repaired exact-head FULL_NATIVE run 33038039750 with zero required native skips, numerical/result drift, checkpoint access, Event 05 authority absence, and P1 attempt-2 absence.

Return structured challenge rows with challenge ID, claim ID, severity, attack, observed evidence, status, and required repair. Finish with counts for blocking, non-blocking-required, defense-in-depth, unresolved, and exactly one global verdict: `NO_UNRESOLVED_MATERIAL_CHALLENGE` or `UNRESOLVED_MATERIAL_CHALLENGES`.
