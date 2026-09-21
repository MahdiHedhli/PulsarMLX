"""Fixed secondary observation source census, not a live registry or package.

The caller cannot select implementations or supply their digest. Numerical
and result authorities are unchanged; this binds only the observation path.
"""
from pathlib import Path
import hashlib
import json
import os
import stat

MEASUREMENT_FILES = (
    "f017_secondary_descriptor_source_v1.py",
    "f017_secondary_read_observation_factory_v1.py",
    "f017_secondary_read_observation_v1.py",
    "f017_secondary_read_observation_prefix_v1.py",
    "f017_secondary_read_observation_inputs_v1.py",
    "f017_corrected_oracle_secondary_wrapper_v11.py",
    "f017_primary_read_observation_v1.py",
    "f017_descriptor_lease_manager_v10.py",
    "f017_bounded_artifact_decode_v1.py",
    "f017_accounting_root_continuity_v1.py",
    "f017_canonical_serialization_v10.py",
)


def measurement_census():
    parent = Path(__file__).resolve().parent
    records = {}
    for name in MEASUREMENT_FILES:
        fd = os.open(parent / name, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 1048576:
                raise ValueError("SECONDARY_MEASUREMENT_REGULAR_BOUND")
            chunks = []
            remaining = before.st_size
            while remaining:
                raw = os.read(fd, min(32768, remaining))
                if not raw:
                    raise ValueError("SECONDARY_MEASUREMENT_SHORT_READ")
                chunks.append(raw)
                remaining -= len(raw)
            if os.read(fd, 1):
                raise ValueError("SECONDARY_MEASUREMENT_EXCESS_READ")
            after = os.fstat(fd)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, key) != getattr(after, key) for key in fields):
                raise ValueError("SECONDARY_MEASUREMENT_CHANGED")
            records[name] = hashlib.sha256(b"".join(chunks)).hexdigest()
        finally:
            os.close(fd)
    return records


def measurement_digest():
    raw = (json.dumps(measurement_census(), sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()
