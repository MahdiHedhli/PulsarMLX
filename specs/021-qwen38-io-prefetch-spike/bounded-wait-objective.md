# Resumable bounded-wait objective

Base: `ebe7ddfe47bbb85ff85074981cad2363a382bf2a`, existing `research/qwen38-strata-pager-m2-20261003` owner/worktree. Native objective editing is unavailable through the status-only API; computer-use access to Codex is denied. This repository graph preserves the full goal without claiming the native objective was edited or bypassing that restriction.

| Node | Depends on | State | Evidence / next action |
| --- | --- | --- | --- |
| M0 Checkpoint/authority | None | Complete | Clean base and branch verified; source/fixtures and permitted Gemini/Grok review authorized by active goal. |
| M1 Implement | M0 | Complete | Temporary competing demand may defer; preserve impossible-page stop, deadline/cancellation, priority, byte reservations and original ownership. |
| M2 Tests | M1 | Complete | Focused fake-clock/generated-file acceptance and applicable Qwen regression; retain exact commands and results. |
| M3 Independent review | M2 | Complete | Freeze and scan scoped source/test/spec packet, select permitted Gemini or Grok; retain raw report and packet hashes. No Anthropic identity, new credentials, purchase or approval bypass. |
| M4 Repair | M3 | Complete | Triage findings locally; repair confirmed defects, test and seek follow-up review when warranted. |
| M5 Validate/checkpoint | M4 | Ready | Final source/result hashes and scope/secret/large-file checks; clean local commit. |
| P1 Push authority | M5 | Recognized, conditional | Separately recognize the current active goal's explicit normal-push instruction at action time; do not reuse the prior one-time checkpoint/push approval. |
| M6 Publish | P1 | Pending | Normal non-force push of existing branch to MahdiHedhli/PulsarMLX; verify remote SHA. No extra merge or rewrite. |
| M7 CI/completion | M6 | Pending | Observe the specific run for that SHA, triage failures, verify terminal conclusions, final remote SHA and clean checkout before completion. |

Graph: `M0 → M1 → M2 → M3 → M4 → M5 → P1 → M6 → M7`. Continue the next ready authorized node after each batch. Record a live review/CI handle and re-poll it rather than restarting after an observation timeout. Stop on genuine missing authority/resources or approval denial. No additional owner, worktree or implementation worker.

## Bounded wait and preserved gates

An unresident actual demand receives a fixed finite monotonic deadline. Duplicate demand, hint activity and unrelated progress cannot extend it. IO admission or relevant IO completion clears the wait. Callers must poll `next_io`, `observe` or `check_waits` while blocked: this cooperative contract is not an autonomous backend timer or latency qualification. Expiry stops new work and cancels the request while retaining pending IO and GPU owners until original completion/release. An impossible page is refused even if IO slots are occupied. The finite default requires calibration before production.

Numerical/reference behavior and tolerances are unchanged. Preserve the 48 GiB process, 40 GiB all-weight and 16 GiB OS reserve gates, actual demand priority, bounded queues, reservations, hint invalidation and GPU completion lifetime. Real checkpoint access, checkpoint Python, installs, MLX/model loading, inference, benchmarks, weight downloads and GLM Studio remain excluded. Future hardware, sampler and numerical milestones require the owner's actual explicit permission.

## Review and checkpoint status

Gemini static review accepted the frozen packet with no confirmed defects; [disposition](evidence/bounded-wait-review-disposition-2026-10-08.md). Nonblocking cleanup suggestions are deferred. M6/M7 are external-state milestones: this file captures pre-publication state; resume by querying the actual remote SHA and its CI rather than treating this snapshot as proof of unfinished or completed execution. No native goal-text update is claimed.

Publication authority: the current active bounded-wait goal expressly requests a normal non-force push of this existing branch after source tests and permitted review, followed by exact-commit CI. That instruction is recognized separately from the old one-time checkpoint/push grant. It covers the existing CI verification requested by the goal, not extra manual hardware/model qualification. No instruction has revoked it. Source and review gates have passed; final scope checks and commit remain before push.
