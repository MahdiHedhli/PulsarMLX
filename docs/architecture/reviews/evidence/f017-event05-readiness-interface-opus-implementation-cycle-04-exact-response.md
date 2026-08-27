```json
{
  "model": "claude-opus-5",
  "reviewed_head": "fa7b3b6a512f4cef5bfa9e9ab6ba36def34f29ce",
  "effort": "high",
  "claim_verdicts": {
    "C-SCHEMA-001": "ACCEPT",
    "C-SCHEMA-002": "ACCEPT",
    "C-VALIDATOR-001": "ACCEPT",
    "C-AUTHORIZER-001": "ACCEPT",
    "C-INSTANT-001": "ACCEPT",
    "C-INSTANT-002": "ACCEPT",
    "C-BIND-001": "ACCEPT",
    "C-SAFETY-001": "ACCEPT",
    "C-LEGACY-001": "ACCEPT",
    "C-CI-001": "ACCEPT",
    "C-REVIEW-001": "ACCEPT",
    "C-GO-001": "ACCEPT"
  },
  "findings": {
    "F-F": {
      "severity": "BLOCKING",
      "status": "REPAIRED_AND_INDEPENDENTLY_VERIFIED",
      "evidence": "f017_event05_readiness_authority_v1.py:166-180 now enforces HEAD and RESPONSE: reviewed_head must be a real commit object (_git_object) and measured_implementation_head must be its ancestor (git merge-base --is-ancestor); exact_response_path is resolved repository-relative under _resolve and sha256(bytes) must equal exact_response_sha256. 15 independent FINAL-scope probes: stale ancestor commit, root commit, nonexistent commit, tree-instead-of-commit, response-SHA substitution, response-path substitution, absolute path, .. traversal, missing path, uppercase head, cross-scope schema, role swap, declaration/manifest path divergence all rejected; baseline accepts. The superseded gemini cycle-03 scope-repair result is now rejected as 'readiness gemini reviewed head ancestry'."
    },
    "F-G": {
      "severity": "NON_BLOCKING_REQUIRED",
      "status": "REPAIRED_AND_INDEPENDENTLY_VERIFIED",
      "evidence": "Generated campaign raised 231 -> 251 with 20 FINAL-scope reviewer-binding mutations (10 gemini + 10 opus). Line trace over run_campaign() shows the FINAL branch (lines 155-180) executing (previously 0); all 20 rejections land inside it (14 at the required-dict check, 2 in _git_object, 4 at the exact-response binding). Campaign reproduces byte-identically at the reviewed head: e83527e220d937143b9de201352d42a3e58c0967ae91600e989fbc36e20bc119, matching qualification-v4.json, and is CI-gated by cmp in macos.yml:393-396. Mutation plan v3 preregisters final_review_bindings:20 and floors 251/245."
    },
    "defense_in_depth": [
      "Review artifacts and the runtime manifest have no key census: an opus FINAL result carrying both global_verdict=ACCEPT... and a conflicting verdict=REJECT is accepted (contract alias_policy declares conflicting_representations_permitted:false). Not exploitable — global_verdict is the sole authoritative field and must equal the exact acceptance token, so no REJECT can be laundered into an ACCEPT.",
      "CI-evidence readers still accept dual keys: full_native.get('run_id', full_native.get('run')) and the same for evidence_only. Same-artifact result=='PASS' and skip/job counts are checked, so no false authority is reachable.",
      "contract review_protocols.* (runtime_enforcement, gemini/opus_exact_acceptance_token, *_result_scope) remains read by zero validating code; the acceptance tokens are hardcoded at f017_event05_readiness_authority_v1.py:155-157 and duplicated in the qualifier. They currently match the contract exactly, but nothing detects future divergence.",
      "The ancestry rejection path (line 177) has no generated mutation: reviewed_head='0'*40 exercises only the real-commit half. A regression deleting the merge-base check would leave all 251 cases green.",
      "measured_implementation_head f35d3411 is a commit at which the measured implementation cannot execute — it forward-references measurement v8, which is first banked one commit later at 5939dd45. Harmless in practice: --check gates 36/36 blob identity from that head through CI head 5357dbf5 to HEAD (zero drift), and nothing executes at f35d3411.",
      "The prepared VALIDATION_ONLY fixture still binds FULL_NATIVE v6 (run 33044253965), and graph manifest v5 binds full-native-ci-v7; CI v8 (run 33049485460) is bound by no authority manifest at this head. Neither authorizes anything.",
      "The inert GO template v11-v2 still pins consumer-interface v1 (ee1d627d), not v3; it is sha-bound but read by no code and carries state INERT_TEMPLATE_NOT_APPROVAL with all identities null."
    ]
  },
  "accepted_claims": 12,
  "rejected_claims": 0,
  "unresolved_claims": 0,
  "blocking_findings": 0,
  "non_blocking_required_findings": 0,
  "original_checkpoint_access": 0,
  "global_verdict": "ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION"
}
```
