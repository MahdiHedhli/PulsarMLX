I have completed the review of the proposed Event 06 V12-to-V11 bridge design against the terminal parent failure and the specified attack points.

### F017 Event 06 V12-to-V11 Bridge Challenge Report

| ID | Severity | Affected Claim | Evidence | Attack or Counterexample | Required Resolution | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FINDING-001** | `BLOCKING` | C-BRIDGE-LIFE-001 | In `f017-event06-v12-to-v11-bridge-lifecycle-v1.json`, the `outcomes` array assigns `durable_prefix: THROUGH_IDENTITY_TERMINAL` to all `BRIDGE_CONSTRUCTION` failures (including early failures like `INSTALLED_AUTHORITY_DRIFT` and `PROVENANCE_MISSING`). | If validation fails at `V12_INSTALLED_AUTHORITY_AND_RECEIPT_VALIDATED` (step 3), the identity terminal and leases (step 6) have not yet been reached. The coordinator will incorrectly record a durable prefix of `THROUGH_IDENTITY_TERMINAL`, falsifying the execution state and violating exact durable prefix preservation. | Split pre-identity phases (e.g., `READINESS_AND_INSTALLATION`, `PACKAGE_START`) from post-identity derivation phases in the `outcomes` matrix. Assign correct pre-identity durable prefixes (e.g., `BEFORE_START` or `THROUGH_START`) to these early failures. | OPEN |
| **FINDING-002** | `BLOCKING` | C-BRIDGE-LIFE-001 | In `f017-event06-v12-to-v11-bridge-lifecycle-v1.json`, the next state for the `BRIDGE_CONSTRUCTION` outcome is defined as `PACKAGE_FAILURE_NO_RETRY`. | If an `EXECUTION_PLAN_MISMATCH` or `MEASUREMENT_DRIFT` occurs during bridge derivation (steps 7/8), the system has already acquired five leases at step 6 (`V12_IDENTITY_TERMINAL_AND_FIVE_LEASES_VALIDATED`). Transitioning directly to `PACKAGE_FAILURE_NO_RETRY` bypasses the `DESCRIPTOR_RELEASE` phase, causing a permanent leak of the five file descriptors/leases for the run. | For post-identity derivation failures within the `BRIDGE_CONSTRUCTION` phase, change the `next` state transition to `RELEASE_THEN_PACKAGE_FAILURE_NO_RETRY` to ensure deterministic lease release on early termination. | OPEN |

### Design Verdict

`REPAIR_REQUIRED`
