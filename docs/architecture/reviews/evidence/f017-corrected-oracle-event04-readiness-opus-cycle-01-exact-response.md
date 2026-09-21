# REJECT

The packet is very strong, and almost everything reconstructs cleanly — but one BLOCKING defect prevents acceptance.

## What I confirmed independently

**All five CI runs verified** against `MahdiHedhli/PulsarMLX` (the census is accurate; `gh` defaults to the `upstream` fork and 404s — not an evidence problem). FULL_NATIVE `32686907019` @ `2d6c5e69`: both native jobs **success**, zero required native skips. All four EVIDENCE_ONLY runs: success with **zero** native jobs.

**Gemini Cycle 03**: `ACCEPT`, 0/0/0 findings, no material disagreement, request+response byte SHAs match.

**Numerical closure**: 187 mutations, contract v3, 10 tombstones, 24 equivalence cases, unchanged pure cores, bytecode audit, 9-member runtime proxy. I mounted **20 novel alias/escape attacks** beyond the 187-case corpus — import-as rename, submodule ancestor, star import, dict-valued alias, walrus, decorator, `getattr`, `__dict__`, argument transport, closure capture, and more. **All 20 rejected**; baseline approved use accepted. The policy is genuinely representation-independent.

**Lifecycle V6**: 26 states / 36 transitions / 29 artifacts / 163 identities / 3918 cells / 56 mutations rejected; independent checker agrees without importing the generator; 31/31 tests pass; canonical JSON closed against duplicate keys, BOM, non-finite constants, and float-spelling ambiguity.

**The new operator-approval gate holds.** It runs at the top of `install_candidate`, before any scope branch or file creation. `new_go: false`, wrong decision, reused prior GO, P1 permission, incomplete/extra bindings, and rehearsal/inert schema all fail closed. Quarantine intact: Event 02/03 untouched, ledger 175, no minted Event-04, P1 attempt 01 only, `install_candidate` unreachable from any CLI.

## The blocking finding — measurement substitution, already latent

`f017_corrected_oracle_authorization_v6.py:23` hard-pins the production authority to measurement manifest **v1**, which attests `implementation_head = 10ebfcb1` — the *pre-fix* head. Regenerating the manifest at the reviewed head reproduces **v2** byte-for-byte. Six of 61 load-bearing entries in v1 are stale, including `validate_f017_corrected_oracle_access_v6.py` at blob `e9426d13` — **the version without `validate_operator_approval`**, the very gate this review certifies.

The v2 manifest was banked in `e15ba84a` and is referenced by **nothing**. And the binding is unenforced: `validate_authority_bindings` only checks the file's SHA, never its content; `implementation_measurement_head` is a required authorization key but is absent from `pinned_values`, with no cross-check to the manifest. The retired V3 surface did perform exactly this check.

The sharpest form: a future mint **cannot** bind the correct manifest — declaring v2 raises `canonical production authority path`. The contract *mandates* binding the stale one while letting the operator declare any head they like. That defeats the sole mechanism tying Event-04 authority to the reviewed implementation, and contradicts the shipped `evidence_descendant_may_not_change_load_bearing_bytes: true`.

Also filed DEFENSE_IN_DEPTH: `execute_f017_corrected_oracle_event_v6.py:107` skips `require_active` for synthetic scope, removing the registry's synthetic kill switch. No production path; low severity.

Full record, including a remediation sketch, is in the plan file. I made no repository modifications — all execution ran from a byte-identical scratch extraction, and I did not run the rehearsal locally because the real 465 GB checkpoint is present on this host.
