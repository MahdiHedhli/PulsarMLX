# PulsarMLX F017 DPREFIX-REAL-1 Report

- Verdict: `DENSE-PREFIX M1-F(-1) REAL CAPTURE REJECTED`
- Terminal class: `NATIVE_RUNTIME`
- Reason: `NATIVE_CANDIDATE_MATVEC_SHAPE`
- Adjudication and execution head: `87492cc670bcb46348cda0a72b6481690b907dd3`
- Attempt: `DPREFIX-REAL-1`; authorized, consumed, executed, checkpoint accessed
- Checkpoint revision: `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- Checkpoint-set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Mount admission: `PASSED_SAME_REVIEWED_REGULAR_FILE_OBJECTS_NO_SYMLINK`
- Orchestrator: `4b69d8fcca3edf6edbe78e75d62d5b9558d58ac90f7d70fbae79484e017f18df`
- Config v5: `27774a11d933750cb9703a9889b5f83b88711ee27827c9d34eb585649545aadd`
- Authorization v4: `fc286651d4fa11ff43e0db926a801d24e30152509465d2d7f0510d79599e1e47`
- Candidate: `1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a`
- Oracle: `9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b`
- Metric engine: `cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738`
- Access: 1 shard open, 40 positional reads, 40 payloads, `1,431,263,232` packed bytes
- Ledger: `59 → 99`
- Q4_K actual packed: `3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef`; decoded: `e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1`; exact identity confirmed
- Q6_K actual packed: `845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede`; decoded: `ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a`; exact identity confirmed
- Remaining 38 packed first-observation identities: retained in raw evidence; decoded hashes were not persisted by the material manifest before the native failure
- Oracle finalized before candidate: yes by reviewed control-flow reachability; its runtime hash was not persisted before failure
- Oracle post-candidate rehash: not reached
- Candidate repeats and determinism: no evidence artifact produced
- Eight Tier-B rows and overall numerical result: not evaluated
- Dispatch/sync/readback/host-copy, fallback/backend-error, and lifecycle evidence: not produced
- Retained layer-2/layer-3 state: not created
- Representative M1-F0: `NOT_AUTHORIZED / NOT_EXECUTED`
- Raw evidence: `docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-rejected-native-runtime-v1.json`, SHA-256 `a21af1ed489382bfed211682f4cc471744235d13acd97e8a4866089532eaef34`
- Attempt ledger: `docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v8.json`
- Real-evidence commit: `594021194c8e70d92965e344780879ed53003f84`
- Checkpoint-free CI correction head: `6bcc721885b33df1fe3b4ca274ec58c2b42cd72c`
- Final Apple-native CI: run `31971520387` → `6bcc721885b33df1fe3b4ca274ec58c2b42cd72c`; both required jobs passed
- The first evidence-head CI run `31970941752` failed only because its workflow still asserted the historical live ledger value 59. The correction changed CI validation only; it did not reread the checkpoint, rerun the candidate or oracle, or rewrite execution evidence.

Exact next action: independent adversarial review of the failure evidence. No
retry is authorized.
