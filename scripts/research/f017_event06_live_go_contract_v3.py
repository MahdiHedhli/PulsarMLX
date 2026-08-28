"""Generated constants for the Event 06 V12 live-GO call path."""

from __future__ import annotations

from typing import Final

# This block is emitted directly from canonical JSON. Keeping each authority
# value on one line makes generator drift a plain byte comparison.
# fmt: off
REQUIREMENTS_RELATIVE: Final = 'specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-live-go-call-path-requirements-v1.json'
LIVE_GO_SCHEMA: Final = 'pulsarmlx.f017.event06-v12-future-human-go/3.0.0'
LIVE_GO_DECISION: Final = 'GO_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06'
LIVE_GO_SCOPE: Final = 'ONE_FUTURE_EVENT06_V12_PRODUCTION_INSTALL'
LIVE_GO_FIELDS: Final = ('schema', 'decision', 'live', 'raw_human_go_sha256', 'authorization_id', 'package_attempt_id', 'readiness_sha256', 'target_parent', 'target_leaf', 'issued_at_unix_ns', 'expires_at_unix_ns', 'nonce_sha256', 'scope', 'attempts', 'retries', 'resume')
LIVE_GO_TYPES: Final = {'schema': 'str', 'decision': 'str', 'live': 'bool', 'raw_human_go_sha256': 'sha256', 'authorization_id': 'typed_id', 'package_attempt_id': 'typed_id', 'readiness_sha256': 'sha256', 'target_parent': 'absolute_path', 'target_leaf': 'safe_leaf', 'issued_at_unix_ns': 'non_boolean_integer', 'expires_at_unix_ns': 'non_boolean_integer', 'nonce_sha256': 'sha256', 'scope': 'str', 'attempts': 'non_boolean_integer', 'retries': 'non_boolean_integer', 'resume': 'bool'}
APPROVAL_SCHEMA: Final = 'pulsarmlx.f017.event06-v12-live-operator-approval/3.0.0'
APPROVAL_FIELDS: Final = ('schema', 'live_go_envelope_sha256', 'readiness_sha256', 'authorization_id', 'package_attempt_id', 'execution_plan_sha256', 'event_identity_plan_sha256', 'candidate_sha256', 'live', 'attempts', 'retries', 'resume')
APPROVAL_TYPES: Final = {'schema': 'str', 'live_go_envelope_sha256': 'sha256', 'readiness_sha256': 'sha256', 'authorization_id': 'typed_id', 'package_attempt_id': 'typed_id', 'execution_plan_sha256': 'sha256', 'event_identity_plan_sha256': 'sha256', 'candidate_sha256': 'sha256', 'live': 'bool', 'attempts': 'non_boolean_integer', 'retries': 'non_boolean_integer', 'resume': 'bool'}
EVENT_IDENTITY_SCHEMA: Final = 'pulsarmlx.f017.event06-v12-prompt-bound-event-identity-plan/2.0.0'
EVENT_IDENTITY_FIELDS: Final = ('schema', 'authorization_id', 'package_attempt_id', 'primary_event_id', 'secondary_event_id', 'execution_plan_sha256', 'prompt_repository_commit', 'prompt_repository_path', 'prompt_sha256')
EVENT_IDENTITY_TYPES: Final = {'schema': 'str', 'authorization_id': 'typed_id', 'package_attempt_id': 'typed_id', 'primary_event_id': 'typed_id', 'secondary_event_id': 'typed_id', 'execution_plan_sha256': 'sha256', 'prompt_repository_commit': 'git_object', 'prompt_repository_path': 'repository_path', 'prompt_sha256': 'sha256'}
AUTHORITY_DAG: Final = ('RAW_HUMAN_GO_BYTES->LIVE_GO_ENVELOPE', 'READINESS->LIVE_GO_ENVELOPE', 'EXECUTION_PLAN->EVENT_IDENTITY_PLAN', 'PROMPT_BYTES->EVENT_IDENTITY_PLAN', 'EVENT_IDENTITY_PLAN->CANDIDATE', 'LIVE_GO_ENVELOPE->OPERATOR_APPROVAL', 'READINESS->OPERATOR_APPROVAL', 'EXECUTION_PLAN->OPERATOR_APPROVAL', 'EVENT_IDENTITY_PLAN->OPERATOR_APPROVAL', 'CANDIDATE->OPERATOR_APPROVAL', 'LIVE_GO_ENVELOPE->PREPARED_INSTALLATION', 'OPERATOR_APPROVAL->PREPARED_INSTALLATION', 'EVENT_IDENTITY_PLAN->PREPARED_INSTALLATION', 'PREPARED_INSTALLATION->FUTURE_GO_CAPABILITY', 'FUTURE_GO_CAPABILITY->DURABLE_INSTALLATION_TRANSACTION')
# fmt: on
