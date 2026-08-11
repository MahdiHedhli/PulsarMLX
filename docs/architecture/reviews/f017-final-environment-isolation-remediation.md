# F017 Final Environment Isolation Remediation

## Review status

This is the checkpoint-free internal re-review packet for the final two
pre-M1-A findings. The implementation baseline is
`153ad293` (descended from reviewed head
`49a35c225500e5808d595b282e67542d8ac1d5b3`). The final reviewer must bind the
full exact commit and final-head CI before returning GO.

No real checkpoint was accessed. No M1-A or M1-B stage ran. Numerical
contracts, fixtures, thresholds, checkpoint/tensor execution semantics, and
Feature 018 are unchanged.

## Finding 1 — production environment bypass

`mode_environment_policy` is the single authoritative mapping:

| Runner mode | Required environment policy |
| --- | --- |
| `adapter_preflight` | `production_reviewed` |
| `checkpoint_identity` | `production_reviewed` |
| `p1` and future real execution represented by that mode | `production_reviewed` |
| `fixture_checkpoint_identity` | `checkpoint_free_fixture` |
| `fixture` | any schema-valid environment; fixture evidence remains checkpoint-free |
| `dry_run` | any schema-valid environment |

`ValidatedEnvironment::validate_for_mode` runs immediately after environment
manifest validation and before evidence acquisition, host telemetry, adapter
creation, loaded-library verification, or checkpoint work. Invalid production
mode/fixture-environment combinations fail as `AdmissionEnvironment` with
`mode_environment_kind`.

The separate `--fixture-checkpoint-identity-only` mode preserves the public
split-GGUF identity fixture without allowing its evidence to masquerade as
production M1-B evidence. The production `--checkpoint-identity-only` flag is
therefore unambiguous.

Defense-in-depth validation independently rejects a production PASS unless:

- `environment_kind` is `production_reviewed`;
- telemetry is `measured_host` and admission is safe;
- exactly the reviewed `libmlx.dylib` and `libmlxc.dylib` identities are
  present, arm64, and hash-matched;
- production dispatch, lifecycle, and tensor-map rules remain satisfied.

## Isolation and negative tests

The following tests cover the bypass class:

- `mode_environment_policy_is_explicit_for_every_mode`
- `production_stage_modes_reject_fixture_environments`
- `reviewed_and_fixture_environments_obey_the_authoritative_policy`
- `production_stage_modes_reject_fixture_environment_before_stage_work`
- `p1_rejects_fixture_environment_before_checkpoint_access`
- `production_stage_pass_rejects_fixture_environment_and_synthetic_telemetry`
- `production_stage_pass_requires_exact_loaded_library_evidence`
- `checkpoint_identity_pass_requires_production_environment_and_validated_map`
- `fixture_checkpoint_identity_pass_requires_fixture_environment`

The actual-binary M1-B rejection test passes a nonexistent checkpoint manifest
path and proves the invalid fixture environment is rejected before the path is
opened and before an evidence target is created. M1-A still rejects every
checkpoint argument at CLI validation and performs no checkpoint work.

Fixture dry-run, explicit fixture identity, and fixture execution remain
available; they cannot satisfy M1-A or M1-B.

## Finding 2 — Apple-native loaded-library test coverage

The existing native-only unit tests are:

- `environment::tests::loaded_library_mismatch_is_rejected`
- `environment::tests::loaded_library_match_is_accepted`

They previously passed locally under the pinned native MLX installation but
were omitted from the Apple-native workflow because that job ran the stream
bridge and runner integration tests without running the F017 runner library
tests.

The Apple-native job now executes:

```sh
cargo test -p f017-runner --lib \
  environment::tests::loaded_library -- --nocapture
```

The command inherits the job's pinned `MLX_PREFIX`, `MLX_C_PREFIX`, and
`PULSAR_REQUIRE_NATIVE_MLX=1`; absence of the native installation fails the
build rather than skipping. The test filter emits both match and mismatch test
names in the qualifying job log.

## Local validation

Before this packet was prepared:

- all 43 F017 runner library tests passed;
- all 8 checkpoint-runner integration tests passed;
- both native loaded-library identity tests executed and passed under the
  pinned arm64 MLX native 0.31.2 / MLX C 0.6.0 installation;
- `git diff --check` passed.

The complete workspace, native adapter, R7-R12, evidence/schema, privacy,
generated-artifact, and Spec Kit gates must pass before the final review.

## Task and admission state

- T017-140 remains open and blocks M1-C.
- T017-141 remains open and blocks the canonical P1 command.
- T017-160 remains open until this internal re-review returns GO.
- T017-161 is closed by the independent adversarial GO on the preceding
  remediated boundary.
- M1-A is not executed by this remediation.
- M1-B requires separate authorization after M1-A evidence review.
- M1-C and P1 remain blocked.

## Internal re-review question

Do the authoritative mode/environment policy, early rejection, PASS validator
defense, explicit fixture identity mode, zero-checkpoint-open proof, and
Apple-native execution of both loaded-library identity tests close the final
pre-M1-A implementation blockers?

