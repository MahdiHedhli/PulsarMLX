#!/usr/bin/env python3
"""V11 primary descriptor source with explicit path-reopen accounting."""
from __future__ import annotations

import f017_corrected_oracle_primary_target_source_v10 as historical


class PrimaryDescriptorSourceV11(historical.PrimaryDescriptorSourceV10):
    """Preserve the V10 source semantics while exposing V11 telemetry."""

    def __init__(self, candidate: dict, identities: list[dict], descriptors: list[int]):
        super().__init__(candidate, identities, descriptors)
        self.path_reopen_count = 0


def source_from_inherited_descriptors(candidate: dict, descriptors: list[dict], file_descriptors: list[int]):
    source = PrimaryDescriptorSourceV11(candidate, descriptors, file_descriptors)
    source.exercise_format_probes()
    geometry = historical.numerical.Geometry.from_json(source.document["geometry"])
    return source, geometry, source.document["token"], source.document["position"]
