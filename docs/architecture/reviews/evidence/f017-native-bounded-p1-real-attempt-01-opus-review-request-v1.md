# F017 bounded M1 Ultra P1 post-execution independent review

Review committed repository evidence only. Do not execute P1, open checkpoint payload, mutate repository bytes, repair evidence, or infer a retry authority.

## Reviewer identity and verdict

- Required model: `claude-opus-5`
- Required effort: `high`
- Fresh session; no continuation from an earlier review.
- Finding severities: `BLOCKING`, `NON_BLOCKING_REQUIRED`, `DEFENSE_IN_DEPTH`.
- `BLOCKING` and `NON_BLOCKING_REQUIRED` prevent evidence acceptance.
- Return exactly one evidence verdict: `ACCEPT_POST_EXECUTION_FAILURE_EVIDENCE` or `REJECT`.
- This evidence verdict cannot change the numerical P1 result: produced token `17351` versus expected token `21615` is `M1_ULTRA_P1: FAIL`.

## Exact authority

- Branch: `feat/017-rust-native-inference-runtime`
- Final declaration head and executed Git identity: `fdb186d4df1c0ce6b3953eb97d1437a55ffd4c60`
- Accepted implementation head: `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13`
- Execution-code head: `4faa404c4205d172251436781b6d54042e8409f6`
- Execution-evidence commit: `91f4694c7676d93c0643c12e9b10a1cfb19dc6bd`
- Admission contract SHA-256: `91248295cac2f078e47576e5f22b4f7d0457bf9b3b11645c8e46406b8b1a2e03`
- Executor SHA-256: `21f405cae64469ab1aed89e571464f6b2278681578d714718cb7183ba01fb062`
- Historical ledger SHA-256: `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`; terminal value `175`.

## Exact evidence

- Human approval: `docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-human-approval-v1.json`, SHA-256 `3788fe3060f5d78002adc7f22f94e98c9163a09be1e71648bcade3bde65b3ec7`.
- Live authorization: `docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-live-authorization-v1.json`, SHA-256 `c1a81febcec0171a0aba63da44f645d630b7daca1b4031d52a4b3cecea6a42b7`.
- Owned claim and durable start: SHA-256 `35d95dacd3b0464c6f12d70adf318f60869b1d4366c04c8508be06948844b965`.
- Terminal: `docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-terminal-v1.json`, SHA-256 `de5f918324048fec8e49d63a60d9db6ba536171f4e1ea0dae6f5e5ddfdf7a6ed`.
- Execution evidence: `docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-execution-evidence-v1.json`, SHA-256 `c3dcc92cec8fde419bfdb437e0191a768fce8f48fc78b2e4b78171164caafb7b`.
- Native event ledger: `docs/architecture/reviews/evidence/f017-native-bounded-p1-native-event-ledger-v1.json`, SHA-256 `24d8bd899cf6809387c40d6bd37d5b8f30a2056fa23a19e84bd4f2758305b5dd`.
- Banking validation: `docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-banking-validation-v1.json`, SHA-256 `384e468aec6c9a241db6417e49c80eb3a1251e28e6b7744ae2c60081bfb4c490`.

Recompute every hash from committed bytes. Inspect the admission, D1, D2, executor, and terminalizer code transitively rather than trusting this request.

## Observed result

- Exactly one authorization ID: `F017-NATIVE-BOUNDED-P1-AUTHORIZATION-1`.
- Exactly one attempt ID: `F017-NATIVE-BOUNDED-P1-ATTEMPT-1`.
- Process exit: `2`.
- Prompt token: `9703`.
- Produced token: `17351`.
- Expected token: `21615`.
- Exact error: `bounded P1 token mismatch: expected 21615, got 17351`.
- Terminal: `TERMINAL_FAILURE_NO_RETRY`.
- Retries: `0`; resume: `false`; no second token; no further real inference.

## Mandatory adversarial checks

Independently verify:

1. The human approval and live authorization were valid, exact-head bound, one-shot, and consumed at durable owned start.
2. The executed executor, admission contract, D0/D1/D2/D3.5 authorities, checkpoint manifest/catalog/set, runtime, and M1 Ultra identity agree.
3. Exactly six named checkpoint shards were authorized and preflight hashes/sizes agree; no alternate root or retry path is evidenced.
4. Prompt `9703`, actual token `17351`, expected token `21615`, process failure, and terminal state agree.
5. Exactly one owned attempt started; ownership nonce/PID agree; no retry, resume, replacement terminal, second token, or subsequent inference occurred.
6. The terminal is owned by the process that durably started the attempt and RN1 rules were preserved.
7. Historical real-payload ledger remains `175`; the native execution event is a separate event with delta one on durable start and historical delta zero.
8. Mandatory stop occurred regardless of the token mismatch.
9. Machine-local authorization/claim/start/terminal bytes were copied exactly into committed evidence.
10. The post-execution Git-ref repair did not change reviewed execution bytes.

## Explicit evidence gaps and contract nonconformities

Do not overlook or waive these facts:

- The failure path emitted no `execution-receipt.json`.
- The terminal has `receipt_count: 0` and `receipt_sha256: null`.
- The 22 pre/post counter snapshots were validated in-process before the token comparison, as mechanically implied by control flow, but their exact values were not durably retained.
- The six-shard open/map and logical-tensor-use census was not durably receipted on the failure path.
- D2 says a native event receipt, shard/open/map census, and receipt-bound terminal are required.

Attack whether these gaps make the banking package unacceptable or merely prove that the execution itself failed under the accepted contract. Do not fabricate missing values and do not suggest a retry. If repair would require another P1, state that it is prohibited for this consumed authorization. Assess whether the smallest safe next action is offline diagnosis using already-banked evidence and code, with no checkpoint execution.

## Required response

Return:

1. Reviewed branch/head and all recomputed load-bearing hashes.
2. Authorization/single-use verdict.
3. Checkpoint/runtime/machine identity verdict.
4. Attempt/terminal/mandatory-stop verdict.
5. Numerical result adjudication.
6. 22-counter and receipt/accounting adjudication.
7. Historical/native-ledger adjudication.
8. Findings with stable IDs, severity, path/symbol, evidence, failure mode, and smallest repair that does not authorize rerun.
9. Exact verdict: `ACCEPT_POST_EXECUTION_FAILURE_EVIDENCE` or `REJECT`.
10. State `M1_ULTRA_P1: FAIL`, `P1_ATTEMPTS: 1`, `P1_RETRIES: 0`, `P1_RESUME: NO`, `MANDATORY_STOP: YES`, and `FURTHER_REAL_INFERENCE_EXECUTED: NO`.
