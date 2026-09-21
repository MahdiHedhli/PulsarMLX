"""Explicit fixed secondary source factory; no arbitrary source injection."""
from f017_secondary_descriptor_source_v1 import SecondaryDescriptorStore


def create_descriptor_store(candidate, identities, descriptors, *, _observation_owner):
    return SecondaryDescriptorStore(candidate, identities, descriptors,
                                    _observation_owner=_observation_owner)


def source_from_inherited_descriptors(candidate, identities, descriptors, *, _observation_owner=None):
    store = create_descriptor_store(candidate, identities, descriptors,
                                    _observation_owner=_observation_owner)
    store.exercise_format_probes()
    return store, store.document
