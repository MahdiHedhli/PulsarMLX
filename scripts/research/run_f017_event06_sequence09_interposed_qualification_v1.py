#!/usr/bin/env python3
"""Run Sequence 9 qualification with guards installed before runtime imports."""

from __future__ import annotations

import builtins
import hashlib
import json
import mmap
import os
from pathlib import Path
from typing import Any


def _checkpoint_name(value: object) -> bool:
    text = os.fspath(value) if isinstance(value, os.PathLike) else str(value)
    lowered = text.lower()
    return "glm-5.2" in lowered or "original-checkpoint" in lowered


def run() -> dict[str, object]:
    census = {
        "hash_stream": 0,
        "id_consumption": 0,
        "lease_creation": 0,
        "live_commit": 0,
        "mmap": 0,
        "numerical_execute": 0,
        "open": 0,
        "package_start": 0,
        "path_stat": 0,
        "pread": 0,
        "root_resolve": 0,
        "tensor_source": 0,
    }
    real_os_open = os.open
    real_builtin_open = builtins.open
    real_stat = Path.stat
    real_resolve = Path.resolve
    real_file_digest = hashlib.file_digest

    def guarded_os_open(path: object, *args: Any, **kwargs: Any) -> int:
        if _checkpoint_name(path):
            census["open"] += 1
            raise AssertionError("original checkpoint open")
        return real_os_open(path, *args, **kwargs)

    def guarded_builtin_open(path: object, *args: Any, **kwargs: Any) -> Any:
        if _checkpoint_name(path):
            census["open"] += 1
            raise AssertionError("original checkpoint open")
        return real_builtin_open(path, *args, **kwargs)

    def guarded_pread(descriptor: int, length: int, offset: int) -> bytes:
        census["pread"] += 1
        raise AssertionError("pread is outside Sequence 9 qualification authority")

    def guarded_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if _checkpoint_name(path):
            census["path_stat"] += 1
            raise AssertionError("original checkpoint stat")
        return real_stat(path, *args, **kwargs)

    def guarded_resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        if _checkpoint_name(path):
            census["root_resolve"] += 1
            raise AssertionError("original checkpoint resolve")
        return real_resolve(path, *args, **kwargs)

    def guarded_mmap(*args: Any, **kwargs: Any) -> mmap.mmap:
        census["mmap"] += 1
        raise AssertionError("mmap is outside Sequence 9 qualification authority")

    def guarded_file_digest(fileobj: Any, digest: Any, /, *, _bufsize: int = 2**18) -> Any:
        if _checkpoint_name(getattr(fileobj, "name", "")):
            census["hash_stream"] += 1
            raise AssertionError("original checkpoint hash stream")
        return real_file_digest(fileobj, digest, _bufsize=_bufsize)

    os.open = guarded_os_open  # type: ignore[assignment]
    builtins.open = guarded_builtin_open  # type: ignore[assignment]
    os.pread = guarded_pread  # type: ignore[assignment]
    Path.stat = guarded_stat  # type: ignore[assignment]
    Path.resolve = guarded_resolve  # type: ignore[assignment]
    mmap.mmap = guarded_mmap  # type: ignore[assignment,misc]
    hashlib.file_digest = guarded_file_digest  # type: ignore[assignment]

    # Import the future live execution modules only after the filesystem guards
    # above are active, then interpose their actual entry points before loading
    # the qualification driver.  These counters are observations, not declared
    # zeros: any attempted live transition aborts the no-access process.
    import execute_f017_corrected_oracle_event_v12_bridge as coordinator
    import f017_corrected_oracle_primary_numerics_v3 as primary_numerics
    import f017_corrected_oracle_primary_target_source_v11 as primary_source
    import f017_corrected_oracle_primary_wrapper_v12 as primary_wrapper
    import f017_corrected_oracle_secondary_numerics_v3 as secondary_numerics
    import f017_corrected_oracle_secondary_target_source_v11 as secondary_source
    import f017_corrected_oracle_secondary_wrapper_v12 as secondary_wrapper

    def forbid(counter: str, transition: str) -> Any:
        def guarded(*args: object, **kwargs: object) -> object:
            del args, kwargs
            census[counter] += 1
            raise AssertionError(f"{transition} is outside Sequence 9 qualification authority")

        return guarded

    primary_numerics.execute_outputs = forbid(  # type: ignore[assignment]
        "numerical_execute", "primary numerical execution"
    )
    secondary_numerics.execute_outputs = forbid(  # type: ignore[assignment]
        "numerical_execute", "secondary numerical execution"
    )
    primary_wrapper.execute_bridge_and_bank = forbid(  # type: ignore[assignment]
        "numerical_execute", "primary bridge execution"
    )
    secondary_wrapper.execute_bridge_and_bank = forbid(  # type: ignore[assignment]
        "numerical_execute", "secondary bridge execution"
    )
    coordinator.execute_primary = primary_wrapper.execute_bridge_and_bank
    coordinator.execute_secondary = secondary_wrapper.execute_bridge_and_bank

    coordinator.bank_package_start = forbid(  # type: ignore[assignment]
        "package_start", "package durable start"
    )
    coordinator.execute_event06_bridge = forbid(  # type: ignore[assignment]
        "package_start", "Event 06 coordinator execution"
    )

    primary_source.source_from_inherited_descriptors = forbid(  # type: ignore[assignment]
        "tensor_source", "primary tensor-source construction"
    )
    secondary_source.source_from_inherited_descriptors = forbid(  # type: ignore[assignment]
        "tensor_source", "secondary tensor-source construction"
    )
    primary_wrapper.source_from_inherited_descriptors = (  # type: ignore[assignment]
        primary_source.source_from_inherited_descriptors
    )
    secondary_wrapper.source_from_inherited_descriptors = (  # type: ignore[assignment]
        secondary_source.source_from_inherited_descriptors
    )

    import f017_event06_production_installation_v2 as production

    real_produce = production.produce_future_go_capability
    real_production_commit = production.commit_production_installation_v2
    real_commit = production._commit_bound_production_transaction

    def observed_produce(*args: object, **kwargs: object) -> object:
        result = real_produce(*args, **kwargs)  # type: ignore[operator]
        census["lease_creation"] += 1
        return result

    def observed_commit(*args: object, **kwargs: object) -> object:
        census["live_commit"] += 1
        return real_commit(*args, **kwargs)

    def observed_production_commit(*args: object, **kwargs: object) -> object:
        issued_before = len(production._ISSUED_CAPABILITIES)
        result = real_production_commit(*args, **kwargs)  # type: ignore[operator]
        consumed = issued_before - len(production._ISSUED_CAPABILITIES)
        census["id_consumption"] += consumed
        return result

    production.produce_future_go_capability = observed_produce  # type: ignore[assignment]
    production.commit_production_installation_v2 = observed_production_commit  # type: ignore[assignment]
    production._commit_bound_production_transaction = observed_commit

    import qualify_f017_event06_sequence09_no_access_v1 as qualification

    result = qualification.qualify()
    if any(census.values()):
        raise AssertionError(f"forbidden side effect census: {census}")
    result = dict(result)
    result["interposition_installed_before_execution_facing_imports"] = True
    result["interposition_census"] = census
    result["interposition_result"] = "PASS"
    return result


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
