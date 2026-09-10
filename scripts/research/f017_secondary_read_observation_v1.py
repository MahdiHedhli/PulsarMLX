"""Secondary Python pread observations, never execution or result authority.

FORMAT_PROBE and NUMERICAL_PAYLOAD counters are derived from the validated
catalogue and descriptor context. Catalog/code/identity reads and this module's
append/fsync/readback persistence are separate non-payload I/O classes; they are
not counted as tensor pread calls and are not claimed to be zero.

The fixed append-only format reuses Sequence54's durable-prefix architecture.
An intent is not a known API call. Only a durable return/error resolves it.
Interrupted suffixes, invalid owners and persistence failures remain UNKNOWN.
The unchanged primary module supplies only role-neutral bounded primitives.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from f017_descriptor_lease_manager_v10 import validate_descriptors
# These role-neutral persistence primitives are byte-unchanged from Sequence54.
# No primary owner, decoder or numerical graph is invoked or parameterized.
from f017_primary_read_observation_v1 import (
    _canonical, _sha, _rows, _copy_rows, _exact, _parse, _read_record, _validate_rows,
)

__all__: tuple[str, ...] = ()
LIMIT = 32768
VOCABULARY_SHA256 = "9974e6531377b16398fc65d433e923789c757b21c3223d2454bd83bf0297ff43"
DIRECTORY = "secondary-read-observations"
RECEIPT = "observation-receipt.json"
TERMINAL = "observation-terminal.json"
FIELDS = ("attempts", "requested_bytes", "successful_returns", "error_returns",
          "short_returns", "zero_returns", "returned_bytes")
PURPOSES = ("FORMAT_PROBE", "NUMERICAL_PAYLOAD")
BINDINGS = ("role", "package_attempt_id", "consumer_event_id",
            "producer_measurement_sha256", "vocabulary_sha256",
            "measurement_implementation_sha256", "descriptor_set_sha256")


def _encode_record(value):
    raw = _canonical(value)
    if len(raw) > LIMIT:
        raise ValueError("MEASUREMENT_SERIALIZATION_OVERFLOW")
    return raw


def _implementation_sha():
    from f017_secondary_read_observation_inputs_v1 import measurement_digest
    return measurement_digest()


def _bank_record(directory_fd, leaf, value):
    """Actual fixed measurement writer; fault tests may replace OS operations."""
    raw = _encode_record(value)  # Size refusal precedes exclusive creation.
    fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            if count <= 0:
                raise OSError("MEASUREMENT_SHORT_WRITE")
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)
    if _read_record(directory_fd, leaf) != raw:
        raise ValueError("MEASUREMENT_READBACK_MISMATCH")
    return _sha(raw)


def _missing(failure="OBSERVATION_OWNER_ABSENT_OR_INVALID"):
    return {"schema": "pulsarmlx.f017.secondary-read-observation-attachment/1.0.0",
            "role": "SECONDARY", "package_attempt_id": None, "consumer_event_id": None,
            "producer_measurement_sha256": None, "vocabulary_sha256": VOCABULARY_SHA256,
            "measurement_implementation_sha256": None, "descriptor_set_sha256": None,
            "completeness": "INCOMPLETE", "measurement_failure": failure,
            "last_durable_boundary": None, "unknown_suffix": True,
            "totals": None, "validated_prefix_counters": [],
            "receipt_sha256": None, "terminal_sha256": None}


class _SecondaryObservation:
    def __init__(self):
        self.binding = {}; self.identities = []; self.directory_fd = None
        self.counters = []; self.pending = None; self.entered = False
        self.sequence = 0; self.last = None; self.last_record = None
        self.failure = None; self.finished = False; self.stage = "FACTORY"
        self.receipt_sha = None; self.terminal_sha = None
        self.source = None; self.records = {}; self.catalog_identity = None
        self.source_bound = False

    def initialize(self, candidate, identities, directory, authority):
        """Fallible startup runs only after the wrapper owns this instance."""
        try:
            self.counters = _rows()
            validate_descriptors(identities)
            for key in ("package_attempt_id", "consumer_event_id"):
                value = authority[key]
                if type(value) is not str or re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,127}", value) is None:
                    raise ValueError("OBSERVATION_ATTEMPT_IDENTITY")
            if (candidate.get("package_attempt_id") != authority["package_attempt_id"]
                    or candidate.get("secondary_event_id") != authority["consumer_event_id"]):
                raise ValueError("OBSERVATION_EXECUTOR_CONTEXT_MISMATCH")
            measured = authority["producer_measurement_sha256"]
            if type(measured) is not str or re.fullmatch(r"[0-9a-f]{64}", measured) is None:
                raise ValueError("OBSERVATION_MEASUREMENT_IDENTITY")
            catalog_path = candidate["tensor_catalog_path"]
            catalog_sha = candidate["tensor_catalog_sha256"]
            if (type(catalog_path) is not str or not Path(catalog_path).is_absolute()
                    or type(catalog_sha) is not str or re.fullmatch(r"[0-9a-f]{64}", catalog_sha) is None):
                raise ValueError("OBSERVATION_CATALOG_IDENTITY")
            self.catalog_identity = (catalog_path, catalog_sha)
            self.identities = [dict(item) for item in identities]
            self.binding = {"role": "SECONDARY", "package_attempt_id": authority["package_attempt_id"],
                "consumer_event_id": authority["consumer_event_id"],
                "producer_measurement_sha256": measured, "vocabulary_sha256": VOCABULARY_SHA256,
                "measurement_implementation_sha256": _implementation_sha(),
                "descriptor_set_sha256": _sha(_canonical(self.identities))}
            if not isinstance(directory, Path) or not directory.is_absolute():
                raise ValueError("OBSERVATION_EXECUTOR_DIRECTORY")
            directory.mkdir(parents=True, exist_ok=True)
            if directory.resolve(strict=True) != directory or directory.is_symlink():
                raise ValueError("OBSERVATION_DIRECTORY_ALIAS")
            parent_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.mkdir(DIRECTORY, 0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
                self.directory_fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                            dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
            self._persist("OWNER_STARTED")
        except BaseException as exc:
            self._fail("OWNER_INITIALIZATION_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def _fail(self, reason):
        if self.failure is None:
            self.failure = reason

    def _persist(self, boundary):
        if self.failure is not None or self.directory_fd is None or self.finished:
            return
        try:
            record = {"schema": "pulsarmlx.f017.secondary-read-observation-record/1.0.0",
                      **self.binding, "sequence": self.sequence + 1,
                      "previous_sha256": None if self.last is None else self.last["sha256"],
                      "boundary": boundary, "counters": _copy_rows(self.counters),
                      "pending": None if self.pending is None else dict(self.pending)}
            digest = _bank_record(self.directory_fd, f"record-{self.sequence + 1:08d}.json", record)
            self.sequence += 1
            self.last = {"sequence": self.sequence, "sha256": digest, "boundary": boundary}
            self.last_record = record
        except BaseException as exc:
            self._fail("OBSERVATION_PERSISTENCE_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def bind(self, source, candidate, identities):
        try:
            from f017_secondary_descriptor_source_v1 import SecondaryDescriptorStore
            if type(source) is not SecondaryDescriptorStore:
                raise ValueError("OBSERVATION_FIXED_SECONDARY_SOURCE")
            if (candidate.get("package_attempt_id") != self.binding["package_attempt_id"]
                    or candidate.get("secondary_event_id") != self.binding["consumer_event_id"]
                    or identities != self.identities or self.source is not None
                    or (candidate.get("tensor_catalog_path"), candidate.get("tensor_catalog_sha256")) != self.catalog_identity):
                raise ValueError("OBSERVATION_SOURCE_CONTEXT")
            self.source = source
            self.records = {name: (record, _sha(_canonical(record)), record["shard_ordinal"],
                                  "FORMAT_PROBE" if record["purpose"] == "FORMAT_PROBE" else "NUMERICAL_PAYLOAD")
                            for name, record in source.records.items()}
            self._persist("SOURCE_BOUND")
            self.source_bound = self.failure is None
        except BaseException as exc:
            self._fail("OBSERVATION_SOURCE_BINDING_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def intent(self, source, record, identity, requested):
        if self.failure is not None or self.finished:
            return None
        try:
            known, digest, ordinal, purpose = self.records[record["name"]]
            if (source is not self.source or record is not known or _sha(_canonical(record)) != digest
                    or identity != self.identities[ordinal - 2] or self.pending is not None
                    or type(requested) is not int or requested < 0):
                raise ValueError("OBSERVATION_READ_ATTRIBUTION")
            self.pending = {"shard_ordinal": ordinal, "purpose": purpose, "requested_bytes": requested}
            self._persist("READ_INTENT")
            return self.sequence if self.failure is None else None
        except BaseException as exc:
            self._fail("OBSERVATION_ATTRIBUTION_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise
            return None

    def enter(self, ticket):
        if ticket is None or self.failure is not None:
            return
        try:
            if ticket != self.sequence or self.pending is None or self.entered:
                raise ValueError("OBSERVATION_CALL_TICKET")
            row = self.counters[(self.pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(self.pending["purpose"])]
            row["attempts"] += 1; row["requested_bytes"] += self.pending["requested_bytes"]
            self.entered = True  # Memory-only until a known return/error.
        except BaseException as exc:
            self._fail("OBSERVATION_CALL_ENTRY_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def complete(self, ticket, returned=None):
        if ticket is None or self.failure is not None:
            return
        try:
            if ticket != self.sequence or self.pending is None or not self.entered:
                raise ValueError("OBSERVATION_RETURN_TICKET")
            row = self.counters[(self.pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(self.pending["purpose"])]
            if returned is None:
                row["error_returns"] += 1; boundary = "READ_ERROR"
            else:
                if type(returned) is not int or not 0 <= returned <= self.pending["requested_bytes"]:
                    raise ValueError("OBSERVATION_RETURN_LENGTH")
                row["successful_returns"] += 1; row["returned_bytes"] += returned
                row["short_returns"] += int(returned < self.pending["requested_bytes"])
                row["zero_returns"] += int(returned == 0); boundary = "READ_RETURN"
            self.pending = None; self.entered = False
            self._persist(boundary)
        except BaseException as exc:
            self._fail("OBSERVATION_RETURN_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def phase(self, stage):
        try:
            if stage not in {"PRIMARY_PREREQUISITE", "CORE", "CORE_COMPLETE", "BANK"}:
                raise ValueError("OBSERVATION_PHASE")
            self.stage = stage
            self._persist("PHASE_" + stage)
        except BaseException as exc:
            self._fail("OBSERVATION_PHASE_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise

    def attachment(self):
        if self.finished and (not self.source_bound or self.source is None
                or getattr(self.source, "_observation_owner", None) is not self):
            self._fail("OBSERVATION_SOURCE_OWNER_NOT_CURRENT")
        result = _missing(self.failure)
        result.update(self.binding)
        result["last_durable_boundary"] = None if self.last is None else dict(self.last)
        result["validated_prefix_counters"] = [] if self.last_record is None else _copy_rows(self.last_record["counters"])
        complete = (self.finished and self.failure is None and self.pending is None
                    and self.receipt_sha is not None and self.terminal_sha is not None)
        result.update(completeness="COMPLETE" if complete else "INCOMPLETE", unknown_suffix=not complete,
                      totals=_copy_rows(self.counters) if complete else None,
                      receipt_sha256=self.receipt_sha, terminal_sha256=self.terminal_sha)
        return result

    def finish(self, outcome, stage):
        if self.finished:
            return self.attachment()
        try:
            if outcome not in {"RETURNED", "RAISED"} or stage not in {"FACTORY", "PRIMARY_PREREQUISITE", "CORE", "CORE_COMPLETE", "BANK", "COMPLETE"}:
                self._fail("OBSERVATION_FINAL_OUTCOME_OR_STAGE")
            if self.source is None or not self.source_bound:
                self._fail("OBSERVATION_SOURCE_NEVER_BOUND")
            if self.source is not None and getattr(self.source, "_observation_owner", None) is not self:
                self._fail("OBSERVATION_SOURCE_OWNER_LOST_OR_REPLACED")
            if self.pending is not None:
                self._fail("OBSERVATION_PENDING_CALL_OR_RETURN_UNKNOWN")
            self._persist("OWNER_FINISHED")
            complete = self.failure is None and self.pending is None and self.last is not None
            receipt = {"schema": "pulsarmlx.f017.secondary-read-observation-receipt/1.0.0", **self.binding,
                "numerical_outcome": outcome, "diagnostic_stage": stage,
                "completeness": "COMPLETE" if complete else "INCOMPLETE", "unknown_suffix": not complete,
                "measurement_failure": self.failure, "last_durable_boundary": self.last,
                "totals": _copy_rows(self.counters) if complete else None,
                "validated_prefix_counters": [] if self.last_record is None else _copy_rows(self.last_record["counters"])}
            if self.directory_fd is not None:
                self.receipt_sha = _bank_record(self.directory_fd, RECEIPT, receipt)
                terminal = {"schema": "pulsarmlx.f017.secondary-read-observation-terminal/1.0.0",
                            **self.binding, "receipt_sha256": self.receipt_sha,
                            "last_durable_boundary": self.last, "completeness": receipt["completeness"]}
                self.terminal_sha = _bank_record(self.directory_fd, TERMINAL, terminal)
        except BaseException as exc:
            self._fail("OBSERVATION_CLOSURE_FAILED:" + type(exc).__name__)
            if not isinstance(exc, Exception):
                raise
        finally:
            self.finished = True
            if self.directory_fd is not None:
                try:
                    os.close(self.directory_fd)
                except BaseException as exc:
                    self._fail("OBSERVATION_DIRECTORY_CLOSE_FAILED")
                    if not isinstance(exc, Exception):
                        raise
                self.directory_fd = None
        return self.attachment()


def _mark_secondary_failure(owner, reason):
    if type(owner) is _SecondaryObservation:
        try:
            owner._fail(reason)
        except Exception:
            owner.failure = reason


def _start_secondary_observation():
    """Allocate before fallible initialization; no descriptor or file I/O here."""
    try:
        return _SecondaryObservation()
    except Exception:
        return None


def _initialize_secondary_observation(owner, candidate, identities, directory, authority):
    if type(owner) is _SecondaryObservation:
        try:
            owner.initialize(candidate, identities, directory, authority)
        except BaseException as exc:
            _mark_secondary_failure(owner, "OBSERVATION_INITIALIZATION_UNAVAILABLE")
            if not isinstance(exc, Exception):
                raise


def _bind_secondary_observation(owner, source, candidate, identities):
    if type(owner) is _SecondaryObservation:
        try:
            owner.bind(source, candidate, identities)
            return owner
        except BaseException as exc:
            _mark_secondary_failure(owner, "OBSERVATION_SOURCE_BINDING_UNAVAILABLE")
            if not isinstance(exc, Exception):
                raise
    return None


def _check_secondary_observation_source(owner, source):
    """Confirm mandatory wrapper-to-factory plumbing, without changing numerics."""
    if type(owner) is _SecondaryObservation:
        try:
            if owner.source is not source or getattr(source, "_observation_owner", None) is not owner:
                raise ValueError("OBSERVATION_FACTORY_OWNER_LOST")
        except BaseException as exc:
            _mark_secondary_failure(owner, "OBSERVATION_FACTORY_OWNER_LOST_OR_REPLACED")
            if not isinstance(exc, Exception):
                raise


def _abandon_secondary_observation(owner):
    """Close the original owner's directory and retain only its known prefix."""
    try:
        if owner.directory_fd is not None:
            os.close(owner.directory_fd)
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_DIRECTORY_CLOSE_FAILED")
        if not isinstance(exc, Exception):
            raise
    finally:
        owner.directory_fd = None
        owner.finished = True
    return _secondary_observation_attachment(owner)


def _finish_secondary_observation(owner, outcome, stage):
    """Normal finalization never suppresses a fresh control-flow exception."""
    if type(owner) is not _SecondaryObservation:
        return _missing()
    try:
        return owner.finish(outcome, stage)
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_FINALIZATION_INTERRUPTED")
        if not isinstance(exc, Exception):
            raise
        return _abandon_secondary_observation(owner)


def _mark_secondary_failure_while_raising(owner, reason):
    # Used only by the two helpers called at already-in-flight exception sites.
    try:
        _mark_secondary_failure(owner, reason)
    except BaseException:
        try:
            if type(owner) is _SecondaryObservation:
                owner.failure = reason
        except BaseException:
            pass


def _finish_secondary_observation_while_raising(owner):
    """Only the wrapper's existing exception handler may use this isolation."""
    try:
        result = _finish_secondary_observation(owner, "RAISED", _secondary_observation_stage(owner))
        if type(owner) is _SecondaryObservation and owner.directory_fd is not None:
            _mark_secondary_failure(owner, "OBSERVATION_INTERRUPTED_DIRECTORY_CLEANUP")
            return _abandon_secondary_observation(owner)
        return result
    except BaseException:
        _mark_secondary_failure_while_raising(owner, "OBSERVATION_EXCEPTION_FINALIZATION_INTERRUPTED")
        try:
            return _abandon_secondary_observation(owner) if type(owner) is _SecondaryObservation else _missing()
        except BaseException:
            try:
                return _incomplete_secondary_owner_snapshot(owner, "OBSERVATION_FINALIZATION_OWNER_UNAVAILABLE")
            except BaseException:
                return _missing("OBSERVATION_FINALIZATION_OWNER_UNAVAILABLE")


def _secondary_observation_stage(owner):
    try:
        if type(owner) is _SecondaryObservation and owner.stage in {
                "FACTORY", "PRIMARY_PREREQUISITE", "CORE", "CORE_COMPLETE", "BANK", "COMPLETE"}:
            return owner.stage
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_STAGE_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise
    return "FACTORY"


def _incomplete_secondary_owner_snapshot(owner, failure):
    """Copy only this owner's known prefix; never read files or infer completion."""
    result = _missing(failure)
    if type(owner) is not _SecondaryObservation:
        return result
    # Use fixed binding fields, not arbitrary owner keys or live suffix counters.
    result.update({key: owner.binding[key] for key in BINDINGS if key in owner.binding})
    result["last_durable_boundary"] = None if owner.last is None else dict(owner.last)
    result["validated_prefix_counters"] = [] if owner.last_record is None else _copy_rows(owner.last_record["counters"])
    result["receipt_sha256"] = owner.receipt_sha
    result["terminal_sha256"] = owner.terminal_sha
    return result


def _secondary_observation_attachment(owner):
    try:
        return owner.attachment() if type(owner) is _SecondaryObservation else _missing()
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_ATTACHMENT_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise
        try:
            return _incomplete_secondary_owner_snapshot(owner, "OBSERVATION_ATTACHMENT_UNAVAILABLE")
        except Exception:
            # Corrupt/unavailable owner state is not a basis for reconstruction.
            return _missing("OBSERVATION_OWNER_PREFIX_UNAVAILABLE")


def _phase_secondary_observation(source, stage):
    owner = None
    try:
        owner = getattr(source, "_observation_owner", None)
        if type(owner) is _SecondaryObservation:
            owner.phase(stage)
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_PHASE_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise


def _read_intent(owner, source, record, identity, requested):
    try:
        return owner.intent(source, record, identity, requested) if type(owner) is _SecondaryObservation else None
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_READ_INTENT_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise
        return None


def _read_enter(owner, ticket):
    try:
        if type(owner) is _SecondaryObservation:
            owner.enter(ticket)
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_READ_ENTRY_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise


def _read_return(owner, ticket, returned):
    try:
        if type(owner) is _SecondaryObservation:
            owner.complete(ticket, returned)
    except BaseException as exc:
        _mark_secondary_failure(owner, "OBSERVATION_READ_RETURN_UNAVAILABLE")
        if not isinstance(exc, Exception):
            raise


def _read_error_while_raising(owner, ticket):
    """Only the existing os.pread exception handler may use this isolation."""
    try:
        if type(owner) is _SecondaryObservation:
            owner.complete(ticket)
    except BaseException:
        _mark_secondary_failure_while_raising(owner, "OBSERVATION_READ_ERROR_UNAVAILABLE")


def _transition(previous, record):
    _validate_rows(record["counters"])
    before = _rows() if previous is None else _copy_rows(previous["counters"])
    pending = None if previous is None else previous["pending"]
    boundary = record["boundary"]
    if previous is None:
        if boundary != "OWNER_STARTED" or record["pending"] is not None or record["counters"] != before:
            raise ValueError("OBSERVATION_INITIAL_RECORD")
        return
    if previous["boundary"] == "OWNER_FINISHED":
        raise ValueError("OBSERVATION_AFTER_FINISH")
    if boundary == "READ_INTENT":
        item = record["pending"]
        if (pending is not None or type(item) is not dict
                or set(item) != {"shard_ordinal", "purpose", "requested_bytes"}
                or type(item["shard_ordinal"]) is not int or item["shard_ordinal"] not in range(2, 7)
                or item["purpose"] not in PURPOSES or type(item["requested_bytes"]) is not int
                or item["requested_bytes"] < 0 or record["counters"] != before):
            raise ValueError("OBSERVATION_INTENT_TRANSITION")
    elif boundary in {"READ_RETURN", "READ_ERROR"}:
        if pending is None or record["pending"] is not None:
            raise ValueError("OBSERVATION_COMPLETION_WITHOUT_INTENT")
        index = (pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(pending["purpose"])
        row = before[index]; observed = record["counters"][index]
        row["attempts"] += 1; row["requested_bytes"] += pending["requested_bytes"]
        if boundary == "READ_ERROR":
            row["error_returns"] += 1
        else:
            returned = observed["returned_bytes"] - row["returned_bytes"]
            if not 0 <= returned <= pending["requested_bytes"]:
                raise ValueError("OBSERVATION_RETURN_DELTA")
            row["successful_returns"] += 1; row["returned_bytes"] += returned
            row["short_returns"] += int(returned < pending["requested_bytes"])
            row["zero_returns"] += int(returned == 0)
        if record["counters"] != before:
            raise ValueError("OBSERVATION_COUNTER_TRANSITION")
    elif boundary == "SOURCE_BOUND":
        if previous["boundary"] != "OWNER_STARTED" or record["counters"] != before or record["pending"] is not None:
            raise ValueError("OBSERVATION_SOURCE_BIND_TRANSITION")
    elif boundary in {"PHASE_PRIMARY_PREREQUISITE", "PHASE_CORE", "PHASE_CORE_COMPLETE", "PHASE_BANK", "OWNER_FINISHED"}:
        if record["counters"] != before or record["pending"] != pending:
            raise ValueError("OBSERVATION_PHASE_TRANSITION")
    else:
        raise ValueError("OBSERVATION_BOUNDARY")


def _read_closure(directory_fd, binding):
    receipt_raw = _read_record(directory_fd, RECEIPT); receipt = _parse(receipt_raw)
    terminal_raw = _read_record(directory_fd, TERMINAL); terminal = _parse(terminal_raw)
    receipt_keys = {"schema", *BINDINGS, "numerical_outcome", "diagnostic_stage", "completeness",
                    "unknown_suffix", "measurement_failure", "last_durable_boundary", "totals", "validated_prefix_counters"}
    terminal_keys = {"schema", *BINDINGS, "receipt_sha256", "last_durable_boundary", "completeness"}
    if (type(receipt) is not dict or set(receipt) != receipt_keys
            or type(terminal) is not dict or set(terminal) != terminal_keys
            or receipt["schema"] != "pulsarmlx.f017.secondary-read-observation-receipt/1.0.0"
            or terminal["schema"] != "pulsarmlx.f017.secondary-read-observation-terminal/1.0.0"
            or any(not _exact(receipt[key], binding[key]) or not _exact(terminal[key], binding[key]) for key in BINDINGS)
            or not _exact(receipt["last_durable_boundary"], terminal["last_durable_boundary"])
            or terminal["receipt_sha256"] != _sha(receipt_raw)
            or terminal["completeness"] != receipt["completeness"]
            or receipt["numerical_outcome"] not in {"RETURNED", "RAISED"}
            or receipt["diagnostic_stage"] not in {"FACTORY", "PRIMARY_PREREQUISITE", "CORE", "CORE_COMPLETE", "BANK", "COMPLETE"}):
        raise ValueError("OBSERVATION_RECEIPT_TERMINAL_BINDING")
    if receipt["completeness"] == "COMPLETE":
        if receipt["unknown_suffix"] is not False or receipt["measurement_failure"] is not None:
            raise ValueError("OBSERVATION_FALSE_COMPLETE")
    elif (receipt["completeness"] != "INCOMPLETE" or receipt["unknown_suffix"] is not True
          or receipt["totals"] is not None or type(receipt["measurement_failure"]) is not str
          or not receipt["measurement_failure"]):
        raise ValueError("OBSERVATION_INCOMPLETE_TOTALS")
    return receipt, _sha(receipt_raw), _sha(terminal_raw)


def _read_secondary_observation(directory, expected):
    """Validate a writer-confirmed prefix, not the physically present last file.

    A closure may anchor an earlier prefix than a fully written failed suffix.
    Without usable closure, a valid successor confirms its predecessor only:
    the writer cannot advance previous_sha256 before that predecessor's bank
    succeeds. The unconfirmed tail is never promoted to a durable boundary.

    COMPLETE here validates the closure bytes, not an unobservable final
    terminal fsync/readback outcome. Durability qualification also requires
    the original live owner attachment to be COMPLETE with identical binding,
    receipt, terminal, and prefix. Readback must not upgrade an INCOMPLETE owner.
    """
    result = _missing("OBSERVATION_CLOSURE_UNAVAILABLE")
    fd = None; last = None; previous = None; sequence = 1
    source_bound_count = 0
    confirmed_last = None; confirmed_record = None; anchored_record = None
    closure = None; closure_error = None; scan_error = None
    try:
        expected_keys = {"package_attempt_id", "consumer_event_id", "producer_measurement_sha256", "descriptor_set_sha256"}
        if (type(expected) is not dict or set(expected) != expected_keys
                or any(type(expected[key]) is not str for key in expected_keys)):
            raise ValueError("OBSERVATION_EXPECTED_CONTEXT_CENSUS")
        for key in ("producer_measurement_sha256", "descriptor_set_sha256"):
            if re.fullmatch(r"[0-9a-f]{64}", expected[key]) is None:
                raise ValueError("OBSERVATION_DIGEST")
        binding = {**expected, "role": "SECONDARY", "vocabulary_sha256": VOCABULARY_SHA256,
                   "measurement_implementation_sha256": _implementation_sha()}
        fd = os.open(Path(directory) / DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            closure = _read_closure(fd, binding)
        except BaseException as exc:
            if not isinstance(exc, Exception):
                raise
            closure_error = exc
        while True:
            try:
                raw = _read_record(fd, f"record-{sequence:08d}.json")
                record = _parse(raw)
                keys = {"schema", *BINDINGS, "sequence", "previous_sha256", "boundary", "counters", "pending"}
                if (type(record) is not dict or set(record) != keys
                        or record["schema"] != "pulsarmlx.f017.secondary-read-observation-record/1.0.0"
                        or type(record["sequence"]) is not int or record["sequence"] != sequence
                        or record["previous_sha256"] != (None if last is None else last["sha256"])):
                    raise ValueError("OBSERVATION_RECORD_CHAIN")
                if any(not _exact(record[key], binding[key]) for key in BINDINGS):
                    raise ValueError("OBSERVATION_EXPECTED_BINDING")
                _transition(previous, record)
                if record["boundary"] == "SOURCE_BOUND":
                    source_bound_count += 1
                if record["boundary"].startswith("READ_") and source_bound_count != 1:
                    raise ValueError("OBSERVATION_READ_WITHOUT_BOUND_SOURCE")
                confirmed_last, confirmed_record = last, previous
                previous = record
                last = {"sequence": sequence, "sha256": _sha(raw), "boundary": record["boundary"]}
                if closure is not None and _exact(closure[0]["last_durable_boundary"], last):
                    anchored_record = record
                result.update(binding)
                sequence += 1
            except FileNotFoundError:
                break
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    raise
                scan_error = exc
                break
        if confirmed_record is not None:
            result["last_durable_boundary"] = dict(confirmed_last)
            result["validated_prefix_counters"] = _copy_rows(confirmed_record["counters"])
        if closure is None:
            raise closure_error
        receipt, receipt_sha, terminal_sha = closure
        anchor = receipt["last_durable_boundary"]
        if anchor is None:
            if receipt["completeness"] != "INCOMPLETE" or not _exact(receipt["validated_prefix_counters"], []):
                raise ValueError("OBSERVATION_PREFIX_ABSENT")
            prefix = []
        else:
            if anchored_record is None or not _exact(receipt["validated_prefix_counters"], anchored_record["counters"]):
                raise ValueError("OBSERVATION_RECEIPT_PREFIX_ANCHOR")
            prefix = _copy_rows(anchored_record["counters"])
        complete = receipt["completeness"] == "COMPLETE"
        if complete and source_bound_count != 1:
            raise ValueError("OBSERVATION_SOURCE_BOUND_REQUIRED")
        if complete and (anchored_record is None or anchored_record["boundary"] != "OWNER_FINISHED"
                         or anchored_record["pending"] is not None or not _exact(anchor, last)
                         or not _exact(receipt["totals"], prefix)):
            raise ValueError("OBSERVATION_FALSE_COMPLETE")
        # Select the exact closure anchor before rejecting a torn/orphan suffix.
        # This may intentionally retreat from the raw scan's apparent frontier.
        result.update(binding, last_durable_boundary=None if anchor is None else dict(anchor),
                      validated_prefix_counters=prefix, receipt_sha256=receipt_sha,
                      terminal_sha256=terminal_sha)
        if scan_error is not None:
            raise scan_error
        expected_leaves = {f"record-{index:08d}.json" for index in range(1, sequence)} | {RECEIPT, TERMINAL}
        if set(os.listdir(fd)) != expected_leaves:
            raise ValueError("OBSERVATION_LEAF_CENSUS_OR_ORPHAN")
        result.update(completeness=receipt["completeness"], unknown_suffix=not complete,
                      measurement_failure=receipt["measurement_failure"],
                      totals=_copy_rows(prefix) if complete else None)
    except BaseException as exc:
        result.update(completeness="INCOMPLETE", unknown_suffix=True, totals=None,
                      measurement_failure="OBSERVATION_READBACK_FAILED:" + type(exc).__name__)
        if not isinstance(exc, Exception):
            raise
    finally:
        if fd is not None:
            os.close(fd)
    return result
