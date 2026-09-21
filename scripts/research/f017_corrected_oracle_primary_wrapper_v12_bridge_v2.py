#!/usr/bin/env python3
"""Prompt-bound adapter for the unchanged primary V12 wrapper."""
from __future__ import annotations

from pathlib import Path

from f017_event06_numerical_bridge_v2 import PromptBoundConsumerViewV2
from f017_corrected_oracle_primary_wrapper_v12 import (
    _qualification_execute_bridge_and_bank as _execute,
)


def _qualification_execute_bridge_and_bank(
    numerical: PromptBoundConsumerViewV2,
    result: PromptBoundConsumerViewV2,
    inherited_descriptors: list[int],
    output_directory: Path,
) -> dict:
    if type(numerical) is not PromptBoundConsumerViewV2 or numerical.get("role") != "PRIMARY_NUMERICAL":
        raise TypeError("prompt-bound primary numerical view required")
    if type(result) is not PromptBoundConsumerViewV2 or result.get("role") != "PRIMARY_RESULT":
        raise TypeError("prompt-bound primary result view required")
    if (numerical.get("bridge_sha256") != result.get("bridge_sha256")
            or numerical.get("event_identity_plan_sha256") != result.get("event_identity_plan_sha256")
            or numerical.get("prompt_sha256") != result.get("prompt_sha256")):
        raise ValueError("primary prompt-bound consumer continuity")
    return _execute(
        numerical.legacy_view, result.legacy_view, inherited_descriptors, output_directory,
        numerical.get("authority_mode"),
    )


def execute_bridge_and_bank(
    numerical: PromptBoundConsumerViewV2,
    result: PromptBoundConsumerViewV2,
    inherited_descriptors: list[int],
    output_directory: Path,
) -> dict:
    """Historical public facade; Sequence 39 owns the sole execution entry."""
    del numerical, result, inherited_descriptors, output_directory
    raise RuntimeError("superseded by F017 Sequence 39 minimum gate path")


__all__: tuple[str, ...] = ()
