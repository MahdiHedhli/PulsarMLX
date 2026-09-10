"""Original-owner secondary descriptor-to-durable-prefix composition.

This entry performs no numerical decode or graph execution. The active
secondary wrapper uses the same constructor before its unchanged graph call.
No descriptor ownership is transferred: callers still release their leases.
"""
from f017_secondary_read_observation_factory_v1 import create_descriptor_store
from f017_secondary_read_observation_v1 import (
    BINDINGS, _SecondaryObservation, _start_secondary_observation,
    _initialize_secondary_observation, _check_secondary_observation_source,
    _finish_secondary_observation, _finish_secondary_observation_while_raising,
    _read_secondary_observation, _incomplete_secondary_owner_snapshot, _missing,
)


class SecondaryDescriptorPrefix:
    def __init__(self, candidate, identities, descriptors, directory, authority):
        self.owner = _start_secondary_observation()
        self.directory = directory
        _initialize_secondary_observation(self.owner, candidate, identities, directory, authority)
        try:
            self.store = create_descriptor_store(candidate, identities, descriptors,
                                                   _observation_owner=self.owner)
            self.document = self.store.document
            _check_secondary_observation_source(self.owner, self.store)
        except BaseException:
            _finish_secondary_observation_while_raising(self.owner)
            raise

    def finish(self, outcome, stage):
        _check_secondary_observation_source(self.owner, self.store)
        live = _finish_secondary_observation(self.owner, outcome, stage)
        if type(self.owner) is not _SecondaryObservation:
            return _missing()
        expected = {key: self.owner.binding.get(key) for key in (
            "package_attempt_id", "consumer_event_id", "producer_measurement_sha256", "descriptor_set_sha256")}
        try:
            back = _read_secondary_observation(self.directory, expected)
        except Exception:
            return _incomplete_secondary_owner_snapshot(self.owner, "OBSERVATION_READBACK_UNAVAILABLE")
        compare = (*BINDINGS, "receipt_sha256", "terminal_sha256", "last_durable_boundary", "totals")
        if (live["completeness"] != "COMPLETE" or back["completeness"] != "COMPLETE"
                or any(live.get(key) != back.get(key) for key in compare)):
            return _incomplete_secondary_owner_snapshot(self.owner, "OBSERVATION_LIVE_OWNER_AND_READBACK_NOT_COMPLETE")
        return live

    def finish_while_raising(self):
        return _finish_secondary_observation_while_raising(self.owner)


def open_secondary_descriptor_prefix(candidate, identities, descriptors, directory, authority):
    return SecondaryDescriptorPrefix(candidate, identities, descriptors, directory, authority)
