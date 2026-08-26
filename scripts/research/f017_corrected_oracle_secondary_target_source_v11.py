#!/usr/bin/env python3
"""V11 secondary descriptor source with explicit path-reopen accounting."""
from __future__ import annotations

import f017_corrected_oracle_secondary_target_source_v10 as historical


class SecondaryDescriptorStoreV11(historical.SecondaryDescriptorStoreV10):
    """Preserve the V10 source semantics while exposing V11 telemetry."""

    def __init__(self, candidate: dict, identities: list[dict], descriptors: list[int]):
        super().__init__(candidate, identities, descriptors)
        self.path_reopen_count = 0


def source_from_inherited_descriptors(candidate: dict, descriptors: list[dict], file_descriptors: list[int]):
    store = SecondaryDescriptorStoreV11(candidate, descriptors, file_descriptors)
    store.exercise_format_probes()
    return store, store.document
