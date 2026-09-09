#!/usr/bin/env python3
"""V11 primary descriptor source with explicit path-reopen accounting."""
from __future__ import annotations

import f017_primary_observed_descriptor_source_v1 as observed


class PrimaryDescriptorSourceV11(observed.PrimaryDescriptorSourceV10):
    """Preserve the V10 source semantics while exposing V11 telemetry."""

    def __init__(self, candidate: dict, identities: list[dict], descriptors: list[int], *, _observation_owner=None):
        super().__init__(candidate, identities, descriptors, _observation_owner=_observation_owner)
        self.path_reopen_count = 0


def source_from_inherited_descriptors(candidate: dict, descriptors: list[dict], file_descriptors: list[int], *, _observation_owner=None):
    source = PrimaryDescriptorSourceV11(candidate, descriptors, file_descriptors, _observation_owner=_observation_owner)
    source.exercise_format_probes()
    geometry = observed.numerical.Geometry.from_json(source.document["geometry"])
    return source, geometry, source.document["token"], source.document["position"]
