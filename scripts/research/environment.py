#!/usr/bin/env python3
"""Collect a bounded, public-safe Feature 002 environment snapshot.

The collector never opens a checkpoint and never enumerates the process
environment or process command lines.  Conditional host facts are represented
as explicit ``observed`` or ``unavailable`` objects so publication cannot turn
a failed probe into an inferred value.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence


SNAPSHOT_SCHEMA = "pulsarmlx.research.environment"
SNAPSHOT_VERSION = "1.0.0"
GIB = 1_073_741_824
MINIMUM_TOTAL_MEMORY_BYTES = 42_949_672_960
MINIMUM_AVAILABLE_STORAGE_BYTES = 134_761_081_856
MAXIMUM_LOAD_PER_LOGICAL_CPU = 0.75
INTERFERENCE_REASON_CODES = {
    "memory_pressure_not_normal",
    "load_average_1m_admission_failed",
    "load_average_5m_admission_failed",
    "low_power_mode_active",
    "thermal_state_not_nominal",
    "material_concurrent_workload_declared",
}

SAFE_ENVIRONMENT_ALLOWLIST = (
    "PULSARMLX_MODEL_GGUF",
    "PULSARMLX_MODEL_STORAGE_ROOT",
    "PULSARMLX_ENVIRONMENT_EVIDENCE",
    "PULSARMLX_ROUTER_INSPECTION",
    "PULSARMLX_ORACLE_WORK",
    "PULSARMLX_ORACLE_OUTPUT",
    "PULSARMLX_ROUTER_ORACLE",
    "PULSARMLX_ROUTER_EVIDENCE",
    "PULSARMLX_ROUTER_FIXTURE_EVIDENCE",
)
SECRET_KEY_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "AUTH", "COOKIE", "KEY")
FORBIDDEN_FIELD_NAMES = {
    "account",
    "account_id",
    "account_identifier",
    "email",
    "email_address",
    "username",
    "user_name",
    "hostname",
    "host_name",
    "serial",
    "serial_number",
    "hardware_uuid",
    "volume_uuid",
    "mac_address",
    "ip_address",
    "home",
    "home_directory",
    "command_line",
    "process_command_line",
}
ENVIRONMENT_OBSERVATION_FIELDS = {
    "repository_commit", "worktree_dirty", "captured_at_utc",
    "python_version", "mlx_version", "rust_version", "cargo_version",
    "worker_protocol_version", "pulsarmlx_version", "macos_product_version",
    "macos_build", "shell_architecture", "chip_model", "unified_memory_bytes",
    "physical_cpu_count", "logical_cpu_count", "filesystem_type",
    "available_storage_bytes", "storage_rounding_bytes", "memory_pressure",
    "power_mode", "thermal_state", "collector_process_resident_bytes",
    "collector_peak_resident_bytes", "collector_process_cpu_time_seconds",
    "collector_process_bytes_read", "load_average_1m", "load_average_5m",
    "load_average_15m", "workload_category", "material_concurrent_workload",
    "benchmark_concurrency", "capture_wall_time_ns",
}
ENVIRONMENT_SNAPSHOT_FIELDS = {
    "snapshot_schema", "snapshot_schema_version", "capture_phase", "platform",
    "requested_backend", "requested_device", "storage_role", "storage_locator",
    "safe_environment", "interference_admission", "admission_reasons",
    "observations",
}
STORAGE_ROLE_LOCATORS = {
    "repository_storage": "$PULSARMLX_REPOSITORY_ROOT",
    "model_storage": "$PULSARMLX_MODEL_STORAGE_ROOT",
    "oracle_work_storage": "$PULSARMLX_ORACLE_WORK",
    "candidate_evidence_storage": "$PULSARMLX_ROUTER_EVIDENCE",
}
STORAGE_ROLE_ENVIRONMENT_KEYS = {
    "model_storage": "PULSARMLX_MODEL_STORAGE_ROOT",
    "oracle_work_storage": "PULSARMLX_ORACLE_WORK",
    "candidate_evidence_storage": "PULSARMLX_ROUTER_EVIDENCE",
}
PRIVATE_PATH_RE = re.compile(
    r"(?:/"
    r"Users/|/"
    r"home/|/"
    r"Volumes/|/private/var/|/var/folders/|"
    r"[A-Za-z]:\\Users\\)"
)
SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE "
    r"KEY-----|"
    r"A"
    r"KIA[0-9A-Z]{16}|"
    r"g"
    r"h[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_"
    r"pat_[A-Za-z0-9_]{20,}|"
    r"h"
    r"f_[A-Za-z0-9]{20,})"
)
UUID_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
IPV4_RE = re.compile(
    r"(?<![0-9])(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})"
    r"(?:\.(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}(?![0-9])"
)
HOSTNAME_RE = re.compile(r"(?i)\b[a-z0-9][a-z0-9-]{0,62}(?:\.[a-z0-9-]{1,63})*\.local\b")
EMAIL_RE = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@"
    r"[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![a-z0-9.-])"
)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

CommandRunner = Callable[[Sequence[str]], tuple[int, str]]


class EnvironmentCollectionError(ValueError):
    """A bounded environment collection or privacy error."""


def observed(value: Any, source: str) -> dict[str, Any]:
    """Create an observed-value envelope after checking public bounds."""

    if not source or len(source.encode("utf-8")) > 128:
        raise EnvironmentCollectionError("observation source is invalid")
    if isinstance(value, bool) or type(value) is int:
        pass
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise EnvironmentCollectionError("observation value is not finite")
    elif isinstance(value, str):
        if not value or len(value.encode("utf-8")) > 256:
            raise EnvironmentCollectionError("observation string is invalid")
    else:
        raise EnvironmentCollectionError("observation value is not a public scalar")
    return {"status": "observed", "value": value, "source": source}


def unavailable(reason: str, attempted_method: str) -> dict[str, str]:
    """Create a bounded unavailable-value envelope."""

    for label, value in (("reason", reason), ("attempted method", attempted_method)):
        if not value or len(value.encode("utf-8")) > 256:
            raise EnvironmentCollectionError(f"{label} is invalid")
    return {
        "status": "unavailable",
        "reason": reason,
        "attempted_method": attempted_method,
    }


def _default_runner(argv: Sequence[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            tuple(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                "PATH": os.environ.get(
                    "PATH", "/usr/bin:/bin:/usr/sbin:/sbin"
                ),
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    output = completed.stdout[:16_384]
    return completed.returncode, output


def _command_text(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    source: str,
) -> dict[str, Any]:
    code, output = runner(argv)
    value = output.strip()
    if code == 0 and value and "\n" not in value and len(value.encode("utf-8")) <= 256:
        return observed(value, source)
    return unavailable("the bounded command did not return one usable value", source)


def _command_version(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    source: str,
) -> dict[str, Any]:
    code, output = runner(argv)
    if code == 0:
        first_line = output.strip().splitlines()[0] if output.strip() else ""
        if first_line and len(first_line.encode("utf-8")) <= 256:
            return observed(first_line, source)
    return unavailable("the version command was unavailable", source)


def _sysctl_integer(
    runner: CommandRunner,
    name: str,
    *,
    source: str,
) -> dict[str, Any]:
    result = _command_text(runner, ("/usr/sbin/sysctl", "-n", name), source=source)
    if result["status"] != "observed":
        return result
    try:
        value = int(result["value"])
    except (TypeError, ValueError):
        return unavailable("sysctl returned a non-integer value", source)
    if value <= 0:
        return unavailable("sysctl returned a non-positive value", source)
    return observed(value, source)


def _git_observations(repository_root: Path, runner: CommandRunner) -> dict[str, Any]:
    commit_code, commit_output = runner(("git", "-C", str(repository_root), "rev-parse", "HEAD"))
    commit = commit_output.strip()
    commit_observation = (
        observed(commit, "git_rev_parse_head")
        if commit_code == 0 and COMMIT_RE.fullmatch(commit)
        else unavailable("the repository commit was unavailable", "git_rev_parse_head")
    )
    status_code, status_output = runner(
        ("git", "-C", str(repository_root), "status", "--porcelain=v1", "--untracked-files=all")
    )
    dirty_observation = (
        observed(bool(status_output), "git_status_porcelain")
        if status_code == 0 and len(status_output.encode("utf-8")) <= 1_048_576
        else unavailable("the worktree state was unavailable", "git_status_porcelain")
    )
    return {"repository_commit": commit_observation, "worktree_dirty": dirty_observation}


def _storage_observations(
    storage_root: Path,
    runner: CommandRunner,
    statvfs: Callable[[os.PathLike[str] | str], os.statvfs_result],
) -> dict[str, Any]:
    try:
        stats = statvfs(storage_root)
        available = int(stats.f_bavail) * int(stats.f_frsize)
        if available < 0:
            raise ValueError
        rounded_available = available - (available % GIB)
        available_observation = observed(rounded_available, "statvfs_available_bytes_rounded_down")
    except (OSError, TypeError, ValueError, OverflowError):
        available_observation = unavailable(
            "available storage could not be measured",
            "statvfs_available_bytes_rounded_down",
        )

    filesystem_observation = _filesystem_type(storage_root, runner)
    return {
        "filesystem_type": filesystem_observation,
        "available_storage_bytes": available_observation,
        "storage_rounding_bytes": observed(GIB, "frozen_public_rounding_policy"),
    }


def _filesystem_type(storage_root: Path, runner: CommandRunner) -> dict[str, Any]:
    """Return only the filesystem type, never a device, mount, UUID, or path."""

    code, output = runner(("/bin/df", "-P", str(storage_root)))
    lines = output.splitlines()
    if code != 0 or len(lines) != 2:
        return unavailable(
            "the storage device could not be resolved safely",
            "df_device_then_diskutil_filesystem_type",
        )
    fields = lines[1].split()
    device = fields[0] if fields else ""
    if not re.fullmatch(r"/dev/[A-Za-z0-9._-]{1,128}", device):
        return unavailable(
            "the storage device was not a bounded local device",
            "df_device_then_diskutil_filesystem_type",
        )
    code, disk_information = runner(("/usr/sbin/diskutil", "info", device))
    match = (
        re.search(
            r"(?m)^\s*File System Personality:\s*([A-Za-z0-9._+-]{1,64})\s*$",
            disk_information,
        )
        if code == 0
        else None
    )
    filesystem = match.group(1) if match is not None else None
    if isinstance(filesystem, str) and re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", filesystem):
        return observed(filesystem.lower(), "diskutil_filesystem_personality")
    return unavailable(
        "filesystem type could not be observed safely",
        "df_device_then_diskutil_filesystem_type",
    )


def _memory_pressure(runner: CommandRunner) -> dict[str, Any]:
    code, output = runner(
        ("/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level")
    )
    if code == 0:
        try:
            level = int(output.strip())
        except ValueError:
            level = -1
        category = {1: "normal", 2: "warning", 4: "critical"}.get(level)
        if category is not None:
            return observed(category, "sysctl_kern_memorystatus_vm_pressure_level")
    return unavailable(
        "the kernel memory-pressure category was unavailable",
        "sysctl_kern_memorystatus_vm_pressure_level",
    )


def _power_mode(runner: CommandRunner) -> dict[str, Any]:
    code, output = runner(("/usr/bin/pmset", "-g", "live"))
    if code == 0:
        values = set(re.findall(r"(?m)^\s*lowpowermode\s+([01])\s*$", output[:4096]))
        if values == {"0"}:
            return observed("automatic", "pmset_live_lowpowermode")
        if values == {"1"}:
            return observed("low_power", "pmset_live_lowpowermode")
    return unavailable(
        "the active power mode was not exposed by pmset",
        "pmset_live_lowpowermode",
    )


def _thermal_state(runner: CommandRunner) -> dict[str, Any]:
    code, output = runner(("/usr/bin/pmset", "-g", "therm"))
    bounded = output[:4096].lower()
    if code == 0 and "no thermal warning" in bounded:
        return observed("nominal", "pmset_thermal_status")
    for marker, category in (
        ("critical", "critical"),
        ("serious", "serious"),
        ("warning", "warning"),
    ):
        if code == 0 and marker in bounded:
            return observed(category, "pmset_thermal_status")
    return unavailable(
        "macOS did not expose a coarse thermal category without privilege",
        "pmset_thermal_status",
    )


def _process_resources(runner: CommandRunner) -> dict[str, Any]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak_bytes = int(usage.ru_maxrss)
        if sys.platform != "darwin":
            peak_bytes *= 1024
        peak = observed(peak_bytes, "getrusage_ru_maxrss") if peak_bytes >= 0 else None
        cpu_seconds = float(usage.ru_utime) + float(usage.ru_stime)
        cpu = observed(cpu_seconds, "getrusage_user_plus_system_cpu_seconds")
    except (OSError, TypeError, ValueError, OverflowError):
        peak = None
        cpu = None

    code, output = runner(("/bin/ps", "-o", "rss=", "-p", str(os.getpid())))
    try:
        resident_bytes = int(output.strip()) * 1024
    except (TypeError, ValueError, OverflowError):
        resident_bytes = -1
    resident = (
        observed(resident_bytes, "ps_resident_kibibytes")
        if code == 0 and resident_bytes >= 0
        else unavailable("resident memory was unavailable", "ps_resident_kibibytes")
    )
    if (
        peak is not None
        and resident["status"] == "observed"
        and peak["value"] < resident["value"]
    ):
        # The two gauges are sampled sequentially. On macOS, the resident-set
        # probe can therefore observe a small allocation made after
        # getrusage(2). A process peak cannot be lower than its current RSS, so
        # retain the conservative maximum and name both contributing probes.
        peak = observed(
            resident["value"],
            "max_getrusage_ru_maxrss_and_ps_resident",
        )
    return {
        "collector_process_resident_bytes": resident,
        "collector_peak_resident_bytes": peak
        or unavailable("peak resident memory was unavailable", "getrusage_ru_maxrss"),
        "collector_process_cpu_time_seconds": cpu
        or unavailable("process CPU time was unavailable", "getrusage_user_plus_system_cpu_seconds"),
        "collector_process_bytes_read": unavailable(
            "macOS exposes block operations but not reliable process bytes read here",
            "getrusage_ru_inblock_review",
        ),
    }


def sanitize_execution_environment(values: Mapping[str, str | None]) -> dict[str, str]:
    """Return only symbolic values for explicitly allowlisted variables."""

    safe: dict[str, str] = {}
    allowlist = set(SAFE_ENVIRONMENT_ALLOWLIST)
    for key in values:
        upper = key.upper()
        if any(marker in upper for marker in SECRET_KEY_MARKERS):
            raise EnvironmentCollectionError("secret-shaped environment key is forbidden")
        if key not in allowlist:
            raise EnvironmentCollectionError("execution environment key is not allowlisted")
        safe[key] = f"${key}"
    if "PULSARMLX_MODEL_GGUF" not in safe:
        safe["PULSARMLX_MODEL_GGUF"] = "$PULSARMLX_MODEL_GGUF"
    return {key: safe[key] for key in sorted(safe)}


def normalize_public_path(
    value: os.PathLike[str] | str,
    *,
    repository_root: Path,
    external_symbol: str,
) -> str:
    """Normalize a local path to a repository-relative or symbolic value."""

    if not re.fullmatch(r"\$[A-Z][A-Z0-9_]{0,127}", external_symbol):
        raise EnvironmentCollectionError("external path symbol is invalid")
    try:
        root = repository_root.resolve(strict=True)
        candidate = Path(value).resolve(strict=False)
        relative = candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return external_symbol
    normalized = PurePosixPath(*relative.parts).as_posix()
    if normalized in {"", "."}:
        return "repository_root"
    if relative.parts and relative.parts[0] in {
        ".git", ".venv", "target", "node_modules", "models", "checkpoints"
    }:
        raise EnvironmentCollectionError("repository-relative path is not publishable")
    return normalized


def assert_public_safe(value: Any) -> None:
    """Recursively reject private identifiers, paths, secrets, and non-finite data."""

    pending = [value]
    visited = 0
    while pending:
        current = pending.pop()
        visited += 1
        if visited > 20_000:
            raise EnvironmentCollectionError("environment snapshot is too large")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise EnvironmentCollectionError("environment field name is invalid")
                lowered = key.lower()
                if lowered in FORBIDDEN_FIELD_NAMES or any(
                    marker in key.upper()
                    for marker in ("TOKEN", "SECRET", "PASSWORD", "AUTH", "COOKIE", "KEY")
                ):
                    raise EnvironmentCollectionError("environment contains a forbidden field")
                pending.append(child)
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise EnvironmentCollectionError("environment contains a non-finite number")
        elif isinstance(current, str):
            if (
                PRIVATE_PATH_RE.search(current)
                or SECRET_VALUE_RE.search(current)
                or UUID_RE.search(current)
                or MAC_RE.search(current)
                or IPV4_RE.search(current)
                or HOSTNAME_RE.search(current)
                or EMAIL_RE.search(current)
                or current.startswith("~/")
                or any(
                    ord(character) < 32 and character not in "\t\n\r"
                    for character in current
                )
            ):
                raise EnvironmentCollectionError("environment contains a forbidden private value")


def snapshot_admission(
    observations: Mapping[str, dict[str, Any]],
    *,
    workload_category: str,
    capture_phase: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    def value(name: str) -> Any | None:
        item = observations[name]
        return item.get("value") if item.get("status") == "observed" else None

    total_memory = value("unified_memory_bytes")
    storage = value("available_storage_bytes")
    pressure = value("memory_pressure")
    power = value("power_mode")
    thermal = value("thermal_state")
    logical_cpus = value("logical_cpu_count")
    load_1m = value("load_average_1m")
    load_5m = value("load_average_5m")
    commit = value("repository_commit")
    physical_cpus = value("physical_cpu_count")
    resident = value("collector_process_resident_bytes")
    peak_resident = value("collector_peak_resident_bytes")
    cpu_time = value("collector_process_cpu_time_seconds")
    if (
        not isinstance(commit, str)
        or COMMIT_RE.fullmatch(commit) is None
        or value("pulsarmlx_version") != commit
        or value("worktree_dirty") is not False
    ):
        reasons.append("source_worktree_admission_failed")
    if (
        any(
            not isinstance(value(name), str) or not value(name)
            for name in ("macos_product_version", "macos_build", "chip_model")
        )
        or value("shell_architecture") != "arm64"
        or type(physical_cpus) is not int
        or physical_cpus <= 0
        or type(logical_cpus) is not int
        or logical_cpus < physical_cpus
    ):
        reasons.append("system_identity_admission_failed")
    if any(
        not isinstance(value(name), str) or not value(name)
        for name in (
            "python_version",
            "mlx_version",
            "rust_version",
            "cargo_version",
            "worker_protocol_version",
            "pulsarmlx_version",
        )
    ):
        reasons.append("runtime_identity_admission_failed")
    load_values = tuple(value(name) for name in (
        "load_average_1m", "load_average_5m", "load_average_15m"
    ))
    if (
        not isinstance(value("filesystem_type"), str)
        or not value("filesystem_type")
        or type(resident) is not int
        or resident <= 0
        or type(peak_resident) is not int
        or peak_resident < resident
        or not isinstance(cpu_time, (int, float))
        or isinstance(cpu_time, bool)
        or not math.isfinite(float(cpu_time))
        or cpu_time < 0
        or any(
            not isinstance(load, (int, float))
            or isinstance(load, bool)
            or not math.isfinite(float(load))
            or load < 0
            for load in load_values
        )
        or type(value("capture_wall_time_ns")) is not int
        or value("capture_wall_time_ns") <= 0
        or value("storage_rounding_bytes") != GIB
    ):
        reasons.append("resource_observation_admission_failed")
    if type(total_memory) is not int or total_memory < MINIMUM_TOTAL_MEMORY_BYTES:
        reasons.append("unified_memory_admission_failed")
    if type(storage) is not int or storage < MINIMUM_AVAILABLE_STORAGE_BYTES:
        reasons.append("storage_admission_failed")
    if pressure != "normal":
        reasons.append("memory_pressure_not_normal")
    if type(logical_cpus) is not int or logical_cpus <= 0:
        reasons.append("logical_cpu_admission_failed")
    else:
        maximum_load = logical_cpus * MAXIMUM_LOAD_PER_LOGICAL_CPU
        if not isinstance(load_1m, (int, float)) or isinstance(load_1m, bool) or load_1m > maximum_load:
            reasons.append("load_average_1m_admission_failed")
        if not isinstance(load_5m, (int, float)) or isinstance(load_5m, bool) or load_5m > maximum_load:
            reasons.append("load_average_5m_admission_failed")
    if power == "low_power":
        reasons.append("low_power_mode_active")
    if thermal in {"warning", "serious", "critical"}:
        reasons.append("thermal_state_not_nominal")
    if (
        value("workload_category") != workload_category
        or value("material_concurrent_workload") != (workload_category != "none")
        or type(value("benchmark_concurrency")) is not int
        or value("benchmark_concurrency") <= 0
    ):
        reasons.append("benchmark_configuration_admission_failed")
    if workload_category != "none":
        reasons.append("material_concurrent_workload_declared")
    if not reasons:
        return "admitted", reasons
    if capture_phase == "after" and INTERFERENCE_REASON_CODES.intersection(reasons):
        return "observed_interference", reasons
    return "postponed", reasons


def validate_environment_snapshot(
    snapshot: Mapping[str, Any], *, capture_phase: str
) -> None:
    """Validate one collector snapshot before it can influence a handoff."""

    if set(snapshot) != ENVIRONMENT_SNAPSHOT_FIELDS:
        raise EnvironmentCollectionError("environment snapshot fields are incomplete")
    if (
        snapshot.get("snapshot_schema") != SNAPSHOT_SCHEMA
        or snapshot.get("snapshot_schema_version") != SNAPSHOT_VERSION
        or snapshot.get("capture_phase") != capture_phase
        or snapshot.get("platform") != "macos-arm64"
        or snapshot.get("requested_backend") != "apple-mlx"
        or snapshot.get("requested_device") != "gpu"
        or STORAGE_ROLE_LOCATORS.get(snapshot.get("storage_role"))
        != snapshot.get("storage_locator")
    ):
        raise EnvironmentCollectionError("environment snapshot identity is invalid")

    safe_environment = snapshot.get("safe_environment")
    if (
        not isinstance(safe_environment, Mapping)
        or safe_environment.get("PULSARMLX_MODEL_GGUF") != "$PULSARMLX_MODEL_GGUF"
        or any(
            key not in SAFE_ENVIRONMENT_ALLOWLIST or value != f"${key}"
            for key, value in safe_environment.items()
        )
    ):
        raise EnvironmentCollectionError("environment snapshot allowlist is invalid")

    observations = snapshot.get("observations")
    if not isinstance(observations, Mapping) or set(observations) != ENVIRONMENT_OBSERVATION_FIELDS:
        raise EnvironmentCollectionError("environment snapshot observations are incomplete")
    for observation in observations.values():
        if not isinstance(observation, Mapping):
            raise EnvironmentCollectionError("environment observation is invalid")
        status = observation.get("status")
        if status == "observed":
            if set(observation) != {"status", "value", "source"}:
                raise EnvironmentCollectionError("observed environment value is invalid")
            if not isinstance(observation["source"], str):
                raise EnvironmentCollectionError("observed environment source is invalid")
            observed(observation["value"], observation["source"])
        elif status == "unavailable":
            if set(observation) != {"status", "reason", "attempted_method"}:
                raise EnvironmentCollectionError("unavailable environment value is invalid")
            if not isinstance(observation["reason"], str) or not isinstance(
                observation["attempted_method"], str
            ):
                raise EnvironmentCollectionError("unavailable environment reason is invalid")
            unavailable(observation["reason"], observation["attempted_method"])
        else:
            raise EnvironmentCollectionError("environment observation status is invalid")

    def value(name: str) -> Any | None:
        observation = observations[name]
        return observation.get("value") if observation.get("status") == "observed" else None

    commit = value("repository_commit")
    captured_at = value("captured_at_utc")
    physical_cpus = value("physical_cpu_count")
    logical_cpus = value("logical_cpu_count")
    resident_bytes = value("collector_process_resident_bytes")
    peak_resident_bytes = value("collector_peak_resident_bytes")
    if (
        not isinstance(commit, str)
        or COMMIT_RE.fullmatch(commit) is None
        or value("pulsarmlx_version") != commit
        or type(value("worktree_dirty")) is not bool
        or value("shell_architecture") != "arm64"
    ):
        raise EnvironmentCollectionError("environment snapshot source identity is invalid")
    if not isinstance(captured_at, str) or not captured_at.endswith("Z"):
        raise EnvironmentCollectionError("environment capture timestamp is invalid")
    try:
        parsed_timestamp = datetime.fromisoformat(captured_at[:-1] + "+00:00")
    except (OverflowError, ValueError):
        raise EnvironmentCollectionError("environment capture timestamp is invalid") from None
    if parsed_timestamp.utcoffset() != timezone.utc.utcoffset(parsed_timestamp):
        raise EnvironmentCollectionError("environment capture timestamp is invalid")

    for name in (
        "python_version",
        "mlx_version",
        "rust_version",
        "cargo_version",
        "worker_protocol_version",
        "macos_product_version",
        "macos_build",
        "chip_model",
        "filesystem_type",
    ):
        observed_value = value(name)
        if not isinstance(observed_value, str) or not observed_value:
            raise EnvironmentCollectionError("environment string observation is invalid")
    if value("worker_protocol_version") != "1":
        raise EnvironmentCollectionError("environment worker protocol is invalid")

    for name in (
        "unified_memory_bytes",
        "physical_cpu_count",
        "logical_cpu_count",
        "available_storage_bytes",
        "storage_rounding_bytes",
        "collector_process_resident_bytes",
        "collector_peak_resident_bytes",
        "benchmark_concurrency",
        "capture_wall_time_ns",
    ):
        observed_value = value(name)
        if observed_value is not None and (
            type(observed_value) is not int or observed_value <= 0
        ):
            raise EnvironmentCollectionError("environment integer observation is invalid")
    if (
        isinstance(physical_cpus, int)
        and isinstance(logical_cpus, int)
        and logical_cpus < physical_cpus
    ):
        raise EnvironmentCollectionError("environment CPU counts are inconsistent")
    if (
        isinstance(resident_bytes, int)
        and isinstance(peak_resident_bytes, int)
        and peak_resident_bytes < resident_bytes
    ):
        raise EnvironmentCollectionError("environment memory gauges are inconsistent")

    for name in (
        "collector_process_cpu_time_seconds",
        "load_average_1m",
        "load_average_5m",
        "load_average_15m",
    ):
        observed_value = value(name)
        if observed_value is not None and (
            not isinstance(observed_value, (int, float))
            or isinstance(observed_value, bool)
            or not math.isfinite(float(observed_value))
            or observed_value < 0
        ):
            raise EnvironmentCollectionError("environment numeric observation is invalid")
    bytes_read = value("collector_process_bytes_read")
    if bytes_read is not None and (type(bytes_read) is not int or bytes_read < 0):
        raise EnvironmentCollectionError("environment bytes-read observation is invalid")
    if value("storage_rounding_bytes") not in {None, GIB}:
        raise EnvironmentCollectionError("environment storage rounding is invalid")

    pressure = value("memory_pressure")
    power = value("power_mode")
    thermal = value("thermal_state")
    workload = value("workload_category")
    material_workload = value("material_concurrent_workload")
    if pressure is not None and pressure not in {"normal", "warning", "critical"}:
        raise EnvironmentCollectionError("environment memory pressure is invalid")
    if power is not None and power not in {"automatic", "low_power"}:
        raise EnvironmentCollectionError("environment power mode is invalid")
    if thermal is not None and thermal not in {
        "nominal",
        "warning",
        "serious",
        "critical",
    }:
        raise EnvironmentCollectionError("environment thermal state is invalid")
    if workload not in {
        "none",
        "local_inference",
        "accelerator_benchmark",
        "large_build",
        "memory_pressure",
        "compute_storage_workload",
        "other_material",
    } or type(material_workload) is not bool:
        raise EnvironmentCollectionError("environment workload observation is invalid")
    if material_workload != (workload != "none"):
        raise EnvironmentCollectionError("environment workload facts are inconsistent")

    workload = observations["workload_category"]
    if workload.get("status") != "observed" or not isinstance(workload.get("value"), str):
        raise EnvironmentCollectionError("environment workload category is unavailable")
    expected_status, expected_reasons = snapshot_admission(
        observations,
        workload_category=workload["value"],
        capture_phase=capture_phase,
    )
    reasons = snapshot.get("admission_reasons")
    if (
        not isinstance(reasons, list)
        or len(reasons) != len(set(map(str, reasons)))
        or any(not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", reason) for reason in reasons)
        or snapshot.get("interference_admission") != expected_status
        or reasons != expected_reasons
    ):
        raise EnvironmentCollectionError("environment snapshot admission is inconsistent")
    assert_public_safe(snapshot)


def _observation_value(snapshot: Mapping[str, Any], name: str) -> Any | None:
    observations = snapshot.get("observations")
    if not isinstance(observations, Mapping):
        return None
    observation = observations.get(name)
    if not isinstance(observation, Mapping) or observation.get("status") != "observed":
        return None
    return observation.get("value")


def combine_environment_evidence(
    *,
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any] | None,
    after_unavailable_reason: str | None,
    benchmark_resources: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind two snapshots and worker resource gauges into one evidence object."""

    validate_environment_snapshot(before_snapshot, capture_phase="before")
    if after_snapshot is None:
        if not after_unavailable_reason or len(after_unavailable_reason.encode("utf-8")) > 256:
            raise EnvironmentCollectionError("after snapshot unavailable reason is invalid")
        after: dict[str, Any] = unavailable(
            after_unavailable_reason,
            "post_run_environment_capture",
        )
    else:
        if after_unavailable_reason is not None or after_snapshot.get("capture_phase") != "after":
            raise EnvironmentCollectionError("after snapshot phase is invalid")
        validate_environment_snapshot(after_snapshot, capture_phase="after")
        after = dict(after_snapshot)

    required_resource_fields = {
        "process_footprint_bytes",
        "mlx_active_memory_bytes",
        "mlx_cache_memory_bytes",
        "mlx_peak_memory_bytes",
        "process_cpu_time_seconds",
        "process_bytes_read",
        "worker_backend",
        "worker_requested_device",
        "worker_selected_device",
        "worker_fallback_used",
        "worker_evaluated",
        "worker_synchronized",
    }
    if set(benchmark_resources) != required_resource_fields:
        raise EnvironmentCollectionError("benchmark resource payload is incomplete")
    for value in benchmark_resources.values():
        if not isinstance(value, Mapping) or value.get("status") not in {
            "observed",
            "unavailable",
        }:
            raise EnvironmentCollectionError("benchmark resource observation is invalid")
    worker_facts = {
        name: value.get("value")
        for name, value in benchmark_resources.items()
        if name.startswith("worker_") and value.get("status") == "observed"
    }
    if worker_facts != {
        "worker_backend": "apple-mlx",
        "worker_requested_device": "gpu",
        "worker_selected_device": "gpu",
        "worker_fallback_used": False,
        "worker_evaluated": True,
        "worker_synchronized": True,
    }:
        raise EnvironmentCollectionError("worker execution identity is not an evaluated MLX GPU result")

    identity_fields = (
        "snapshot_schema",
        "snapshot_schema_version",
        "platform",
        "requested_backend",
        "requested_device",
        "storage_role",
        "storage_locator",
        "safe_environment",
    )
    if after_snapshot is not None and any(
        before_snapshot.get(field) != after_snapshot.get(field)
        for field in identity_fields
    ):
        raise EnvironmentCollectionError("environment snapshot identities differ")
    if after_snapshot is not None and any(
        _observation_value(before_snapshot, field)
        != _observation_value(after_snapshot, field)
        for field in (
            "repository_commit",
            "pulsarmlx_version",
            "shell_architecture",
            "chip_model",
            "unified_memory_bytes",
            "physical_cpu_count",
            "logical_cpu_count",
            "filesystem_type",
            "storage_rounding_bytes",
            "benchmark_concurrency",
        )
    ):
        raise EnvironmentCollectionError("environment snapshot immutable facts differ")

    reasons = list(before_snapshot.get("admission_reasons", []))
    before_status = before_snapshot.get("interference_admission")
    if before_status not in {"admitted", "postponed"}:
        raise EnvironmentCollectionError("before snapshot admission is invalid")
    if after_snapshot is None:
        status = "postponed"
        reasons.append("after_snapshot_unavailable")
    else:
        after_status = after_snapshot.get("interference_admission")
        if after_status not in {"admitted", "postponed", "observed_interference"}:
            raise EnvironmentCollectionError("after snapshot admission is invalid")
        reasons.extend(after_snapshot.get("admission_reasons", []))
        for field, reason in (
            ("memory_pressure", "memory_pressure_changed_during_batch"),
            ("power_mode", "power_mode_changed_during_batch"),
            ("thermal_state", "thermal_state_changed_during_batch"),
            ("workload_category", "workload_changed_during_batch"),
            ("material_concurrent_workload", "workload_changed_during_batch"),
        ):
            before_value = _observation_value(before_snapshot, field)
            after_value = _observation_value(after_snapshot, field)
            if before_value is not None and after_value is not None and before_value != after_value:
                reasons.append(reason)
        if before_status != "admitted":
            status = "postponed"
        elif after_status == "observed_interference" or any(
            reason.endswith("_changed_during_batch") for reason in reasons
        ):
            status = "observed_interference"
        elif after_status == "admitted":
            status = "admitted"
        else:
            status = "postponed"

    reasons = list(dict.fromkeys(reasons))
    environment = {
        "platform": "macos-arm64",
        "selected_backend": worker_facts["worker_backend"],
        "selected_device": worker_facts["worker_selected_device"],
        "safe_environment": dict(before_snapshot.get("safe_environment", {})),
        "interference_admission": status,
        "interference_reasons": reasons,
        "before_snapshot": dict(before_snapshot),
        "after_snapshot": after,
        "benchmark_resources": dict(benchmark_resources),
    }
    assert_public_safe(environment)
    return environment


def extract_benchmark_resources(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate bounded worker memory gauges without retaining process identity."""

    gauge_records: list[Mapping[str, Any]] = []
    pending: list[Any] = [candidate]
    visited = 0
    while pending:
        current = pending.pop()
        visited += 1
        if visited > 20_000:
            raise EnvironmentCollectionError("benchmark candidate is too large")
        if isinstance(current, Mapping):
            memory = current.get("memory_gauges")
            if isinstance(memory, Mapping):
                gauge_records.append(current)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    if not gauge_records:
        raise EnvironmentCollectionError("benchmark candidate has no worker memory gauges")

    expected_execution = {
        "backend": "apple-mlx",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
    }
    if any(
        any(record.get(name) != expected for name, expected in expected_execution.items())
        for record in gauge_records
    ):
        raise EnvironmentCollectionError(
            "benchmark candidate memory gauges are not bound to evaluated MLX GPU results"
        )
    gauges = [record["memory_gauges"] for record in gauge_records]

    field_map = {
        "process_footprint_bytes": "process_footprint_bytes",
        "mlx_active_memory_bytes": "mlx_active_bytes",
        "mlx_cache_memory_bytes": "mlx_cache_bytes",
        "mlx_peak_memory_bytes": "mlx_peak_bytes",
    }
    resources: dict[str, Any] = {}
    for public_name, worker_name in field_map.items():
        values = [gauge.get(worker_name) for gauge in gauges]
        if all(type(value) is int and value >= 0 for value in values):
            maximum = max(values)
            if public_name == "process_footprint_bytes" and maximum <= 0:
                raise EnvironmentCollectionError("benchmark process footprint is invalid")
            resources[public_name] = observed(maximum, "worker_memory_gauge_maximum")
        else:
            resources[public_name] = unavailable(
                "the worker did not expose this gauge for every retained result",
                "worker_memory_gauge_maximum",
            )
    resources["process_cpu_time_seconds"] = unavailable(
        "the bounded worker protocol does not expose process CPU time",
        "worker_process_cpu_time",
    )
    resources["process_bytes_read"] = unavailable(
        "macOS does not expose reliable process bytes read through this worker protocol",
        "worker_process_bytes_read",
    )
    for name, value in (
        ("worker_backend", gauge_records[0]["backend"]),
        ("worker_requested_device", "gpu"),
        ("worker_selected_device", "gpu"),
        ("worker_fallback_used", False),
        ("worker_evaluated", True),
        ("worker_synchronized", True),
    ):
        resources[name] = observed(value, "validated_worker_result")
    assert_public_safe(resources)
    return resources


def collect_environment(
    *,
    repository_root: Path,
    storage_root: Path,
    storage_role: str,
    storage_locator: str,
    capture_phase: str,
    workload_category: str,
    benchmark_concurrency: int,
    execution_environment: Mapping[str, str | None],
    runner: CommandRunner = _default_runner,
    statvfs: Callable[[os.PathLike[str] | str], os.statvfs_result] = os.statvfs,
    load_average: Callable[[], tuple[float, float, float]] = os.getloadavg,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    """Collect one public-safe before/after environment snapshot."""

    if capture_phase not in {"before", "after"}:
        raise EnvironmentCollectionError("capture phase is invalid")
    if storage_role not in {
        "repository_storage",
        "model_storage",
        "oracle_work_storage",
        "candidate_evidence_storage",
    }:
        raise EnvironmentCollectionError("storage role is invalid")
    if not re.fullmatch(r"\$[A-Z][A-Z0-9_]{0,127}", storage_locator):
        raise EnvironmentCollectionError("storage locator is invalid")
    expected_locator = {
        "repository_storage": "$PULSARMLX_REPOSITORY_ROOT",
        "model_storage": "$PULSARMLX_MODEL_STORAGE_ROOT",
        "oracle_work_storage": "$PULSARMLX_ORACLE_WORK",
        "candidate_evidence_storage": "$PULSARMLX_ROUTER_EVIDENCE",
    }[storage_role]
    if storage_locator != expected_locator:
        raise EnvironmentCollectionError("storage role and symbolic locator differ")
    if workload_category not in {
        "none",
        "local_inference",
        "accelerator_benchmark",
        "large_build",
        "memory_pressure",
        "compute_storage_workload",
        "other_material",
    }:
        raise EnvironmentCollectionError("workload category is invalid")
    if type(benchmark_concurrency) is not int or not 1 <= benchmark_concurrency <= 64:
        raise EnvironmentCollectionError("benchmark concurrency is invalid")

    storage_environment_key = STORAGE_ROLE_ENVIRONMENT_KEYS.get(storage_role)
    if storage_environment_key is not None:
        declared_storage = execution_environment.get(storage_environment_key)
        if not isinstance(declared_storage, str) or not declared_storage:
            raise EnvironmentCollectionError("symbolic storage root is not bound")
        try:
            measured_storage = storage_root.resolve(strict=False)
            declared_storage_path = Path(declared_storage).resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            raise EnvironmentCollectionError("symbolic storage root is invalid") from None
        if measured_storage != declared_storage_path:
            raise EnvironmentCollectionError("symbolic storage root does not match measured storage")

    started_ns = monotonic_ns()
    timestamp = now()
    if timestamp.tzinfo is None:
        raise EnvironmentCollectionError("UTC timestamp must be timezone-aware")

    git = _git_observations(repository_root, runner)
    storage = _storage_observations(storage_root, runner, statvfs)
    resources = _process_resources(runner)
    macos_version = _command_text(
        runner, ("/usr/bin/sw_vers", "-productVersion"), source="sw_vers_product_version"
    )
    macos_build = _command_text(
        runner, ("/usr/bin/sw_vers", "-buildVersion"), source="sw_vers_build_version"
    )
    architecture = _command_text(runner, ("/usr/bin/uname", "-m"), source="uname_machine")
    chip = _command_text(
        runner,
        ("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"),
        source="sysctl_machdep_cpu_brand_string",
    )
    total_memory = _sysctl_integer(
        runner, "hw.memsize", source="sysctl_hw_memsize"
    )
    physical_cpus = _sysctl_integer(
        runner, "hw.physicalcpu", source="sysctl_hw_physicalcpu"
    )
    logical_cpus = _sysctl_integer(
        runner, "hw.logicalcpu", source="sysctl_hw_logicalcpu"
    )

    try:
        loads = load_average()
        if len(loads) != 3 or any(not math.isfinite(float(value)) or value < 0 for value in loads):
            raise ValueError
        load_observations = {
            "load_average_1m": observed(float(loads[0]), "getloadavg"),
            "load_average_5m": observed(float(loads[1]), "getloadavg"),
            "load_average_15m": observed(float(loads[2]), "getloadavg"),
        }
    except (OSError, TypeError, ValueError, OverflowError):
        load_observations = {
            key: unavailable("system load average was unavailable", "getloadavg")
            for key in ("load_average_1m", "load_average_5m", "load_average_15m")
        }

    try:
        mlx_version: dict[str, Any] = observed(
            importlib.metadata.version("mlx"), "python_package_metadata_mlx"
        )
    except importlib.metadata.PackageNotFoundError:
        mlx_version = unavailable("the MLX package was not installed", "python_package_metadata_mlx")

    observations: dict[str, dict[str, Any]] = {
        **git,
        "captured_at_utc": observed(
            timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "utc_clock",
        ),
        "python_version": observed(platform.python_version(), "python_platform_version"),
        "mlx_version": mlx_version,
        "rust_version": _command_version(runner, ("rustc", "--version"), source="rustc_version"),
        "cargo_version": _command_version(runner, ("cargo", "--version"), source="cargo_version"),
        "worker_protocol_version": observed("1", "pulsar_mlx_worker_protocol_constant"),
        "pulsarmlx_version": dict(git["repository_commit"]),
        "macos_product_version": macos_version,
        "macos_build": macos_build,
        "shell_architecture": architecture,
        "chip_model": chip,
        "unified_memory_bytes": total_memory,
        "physical_cpu_count": physical_cpus,
        "logical_cpu_count": logical_cpus,
        **storage,
        "memory_pressure": _memory_pressure(runner),
        "power_mode": _power_mode(runner),
        "thermal_state": _thermal_state(runner),
        **resources,
        **load_observations,
        "workload_category": observed(workload_category, "operator_declared_workload_category"),
        "material_concurrent_workload": observed(
            workload_category != "none", "operator_declared_workload_category"
        ),
        "benchmark_concurrency": observed(
            benchmark_concurrency, "benchmark_configuration"
        ),
    }
    finished_ns = monotonic_ns()
    if type(started_ns) is not int or type(finished_ns) is not int or finished_ns <= started_ns:
        raise EnvironmentCollectionError("monotonic capture clock is invalid")
    observations["capture_wall_time_ns"] = observed(
        finished_ns - started_ns, "perf_counter_ns"
    )

    admission, reasons = snapshot_admission(
        observations,
        workload_category=workload_category,
        capture_phase=capture_phase,
    )
    snapshot = {
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "snapshot_schema_version": SNAPSHOT_VERSION,
        "capture_phase": capture_phase,
        "platform": "macos-arm64",
        "requested_backend": "apple-mlx",
        "requested_device": "gpu",
        "storage_role": storage_role,
        "storage_locator": storage_locator,
        "safe_environment": sanitize_execution_environment(execution_environment),
        "interference_admission": admission,
        "admission_reasons": reasons,
        "observations": observations,
    }
    assert_public_safe(snapshot)
    return snapshot


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    capture = subparsers.add_parser("capture", help="capture one before/after snapshot")
    capture.add_argument("--repository-root", type=Path, default=Path.cwd())
    capture.add_argument("--storage-root", type=Path, required=True)
    capture.add_argument(
        "--storage-role",
        choices=(
            "repository_storage",
            "model_storage",
            "oracle_work_storage",
            "candidate_evidence_storage",
        ),
        required=True,
    )
    capture.add_argument("--storage-locator", required=True)
    capture.add_argument("--capture-phase", choices=("before", "after"), required=True)
    capture.add_argument(
        "--workload-category",
        choices=(
            "none",
            "local_inference",
            "accelerator_benchmark",
            "large_build",
            "memory_pressure",
            "compute_storage_workload",
            "other_material",
        ),
        required=True,
    )
    capture.add_argument("--benchmark-concurrency", type=int, default=1)
    capture.add_argument("--output", type=Path)

    combine = subparsers.add_parser("combine", help="bind snapshots to worker resources")
    combine.add_argument("--before", type=Path, required=True)
    after_group = combine.add_mutually_exclusive_group(required=True)
    after_group.add_argument("--after", type=Path)
    after_group.add_argument("--after-unavailable-reason")
    combine.add_argument("--benchmark-resources", type=Path, required=True)
    combine.add_argument("--output", type=Path)

    extract = subparsers.add_parser(
        "extract-resources", help="extract public worker gauges from a candidate"
    )
    extract.add_argument("--candidate", type=Path, required=True)
    extract.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _read_bounded_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
        raise EnvironmentCollectionError("environment input is unsafe or oversized")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise EnvironmentCollectionError("environment input is invalid JSON") from error
    if not isinstance(document, dict):
        raise EnvironmentCollectionError("environment input must be an object")
    assert_public_safe(document)
    return document


def _validate_storage_root(
    storage_root: Path,
    *,
    storage_role: str,
    repository_root: Path,
) -> None:
    """Validate a directory role without resolving a checkpoint path."""

    if storage_root.suffix.lower() in {".gguf", ".safetensors", ".bin"}:
        raise EnvironmentCollectionError("storage root must be a directory, not a model file")
    if storage_root.is_symlink() or not storage_root.is_dir():
        raise EnvironmentCollectionError("storage root must be an existing real directory")
    resolved = storage_root.resolve(strict=True)
    repository = repository_root.resolve(strict=True)
    inside_repository = False
    try:
        resolved.relative_to(repository)
        inside_repository = True
    except ValueError:
        pass
    if storage_role == "repository_storage" and not inside_repository:
        raise EnvironmentCollectionError("repository storage role must name the repository")
    if storage_role != "repository_storage" and inside_repository:
        raise EnvironmentCollectionError("external storage roles must remain outside Git")


def write_json_exclusive_atomic(output: Path, payload: str) -> None:
    """Install one complete JSON file atomically without replacing a destination."""

    parent = output.parent
    current = parent.absolute()
    while True:
        root_alias = current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        if current.is_symlink() and not root_alias:
            raise EnvironmentCollectionError("environment output path is unsafe")
        if current.parent == current:
            break
        current = current.parent
    if parent.is_symlink() or not parent.is_dir() or output.is_symlink():
        raise EnvironmentCollectionError("environment output path is unsafe")
    descriptor = -1
    temporary: Path | None = None
    installed = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, output, follow_symlinks=False)
        installed = True
        directory_descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            try:
                os.fsync(directory_descriptor)
            except OSError:
                try:
                    output.unlink()
                    installed = False
                except OSError:
                    # The installed file is the already-fsynced inode. If it
                    # cannot be rolled back, reconcile the operation as a
                    # successful complete installation rather than reporting
                    # failure while leaving an unknown destination behind.
                    if (
                        output.is_symlink()
                        or not output.is_file()
                        or output.read_text(encoding="utf-8") != payload
                        or output.stat().st_mode & 0o777 != 0o600
                    ):
                        raise EnvironmentCollectionError(
                            "environment installation could not be reconciled"
                        )
                else:
                    try:
                        os.fsync(directory_descriptor)
                    except OSError:
                        pass
                    raise
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        if not installed and output.exists() and output.is_symlink():
            raise EnvironmentCollectionError("environment output path is unsafe")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    exit_status = 0
    try:
        if args.operation == "capture":
            execution_environment = {
                key: (
                    None
                    if key == "PULSARMLX_MODEL_GGUF"
                    else os.environ.get(key)
                )
                for key in SAFE_ENVIRONMENT_ALLOWLIST
                if key in os.environ or key == "PULSARMLX_MODEL_GGUF"
            }
            _validate_storage_root(
                args.storage_root,
                storage_role=args.storage_role,
                repository_root=args.repository_root,
            )
            document = collect_environment(
                repository_root=args.repository_root,
                storage_root=args.storage_root,
                storage_role=args.storage_role,
                storage_locator=args.storage_locator,
                capture_phase=args.capture_phase,
                workload_category=args.workload_category,
                benchmark_concurrency=args.benchmark_concurrency,
                execution_environment=execution_environment,
            )
            if document["interference_admission"] != "admitted":
                exit_status = 2
        elif args.operation == "combine":
            before = _read_bounded_json(args.before)
            after = _read_bounded_json(args.after) if args.after is not None else None
            resources = _read_bounded_json(args.benchmark_resources)
            document = combine_environment_evidence(
                before_snapshot=before,
                after_snapshot=after,
                after_unavailable_reason=args.after_unavailable_reason,
                benchmark_resources=resources,
            )
        else:
            candidate = _read_bounded_json(args.candidate)
            document = extract_benchmark_resources(candidate)
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            write_json_exclusive_atomic(args.output, payload)
    except (EnvironmentCollectionError, OSError, ValueError):
        print("environment collection failed: public_safe_environment", file=sys.stderr)
        return 1
    if exit_status:
        print("environment admission postponed: inspect the retained snapshot", file=sys.stderr)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
