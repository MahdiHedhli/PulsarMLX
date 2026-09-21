| Claim | Attack | Observed Evidence | Severity | Disposition |
| :--- | :--- | :--- | :--- | :--- |
| Fresh approval and IDs | Replay authority | `authorization_id` is `F017-CORRECTED-ORACLE-LIVE-AUTHORIZATION-05-V11-2`, attempts=1, retries=0 | NONE | PASS |
| Exact candidate/install identity | Altered SHAs | `candidate_install_bytes_equal=true`, `candidate_sha256` exactly matches `installed_sha256` (`2876a...7e3`) | NONE | PASS |
| Package durable start exactly once | Missing durable artifacts / Hidden consumer execution | `event_05_package_executed=true`, package accounting consumption equals exactly 1 | NONE | PASS |
| Accounting root binding | Fabricated accounting | `accounting-root-authority.json` and `accounting-transition-journal.ndjson` are explicitly bound in authority manifest v3 | NONE | PASS |
| Failure at CHECKPOINT_IDENTITY_START | Inference that event may be retried | `last_completed_transition` is exactly `CHECKPOINT_IDENTITY_START` with declaration `TERMINAL_FAILURE_NO_RETRY` | NONE | PASS |
| Exact exception `ValueError("checkpoint identity producer authority")` | Altered SHAs / Hidden Exception | `failure_class` is `ValueError`, `failure_message` is exactly `checkpoint identity producer authority` | NONE | PASS |
| Static root cause in measured `f017_checkpoint_identity_producer_v10.py` | Altered SHAs / Missing durable artifacts | Manifest binds `producer_path` to the v10 script and `producer_sha256` (`d33fd...c9f`) | NONE | PASS |
| Zero shard opens, identity reads, payload reads, primary starts, secondary starts, and live leases | Hidden shard access / Hidden consumer execution | Checkpoint access is zero; primary/secondary executions are zero; live leases after terminal are zero | NONE | PASS |
| Package accounting delta one | Fabricated accounting | `accounting.package=1`; authorization, primary, and secondary deltas are zero | NONE | PASS |
| Historical ledger 175 | Fabricated accounting | CI and execution report historical before/after exactly 175 | NONE | PASS |
| Complete failure capsule and package terminal | Missing durable artifacts | Failure capsule and package terminal SHAs are measured and bound | NONE | PASS |
| EVIDENCE_ONLY run 33071927245 with zero native jobs | Hidden consumer execution | Run is EVIDENCE_ONLY and `native_jobs_launched=0` | NONE | PASS |
| No P1 attempt 2 | Inference that event may be retried | `p1_attempt_2_executed=false`, readiness false | NONE | PASS |

NO_UNRESOLVED_MATERIAL_CHALLENGE
