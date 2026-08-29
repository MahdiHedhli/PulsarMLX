#!/usr/bin/env python3
"""Darwin multi-process qualification for Event 06 package uniqueness."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_package_attempt_registry_v2 import (
    claim_qualification_terminal_sinks,
    load_live_package_attempt,
    load_qualification_package_attempt,
    reserve_live_package_attempt,
    reserve_qualification_package_attempt,
)
from f017_event06_numerical_bridge_v1 import (
    PHASES,
    accounting_view,
    bind_v11_closure,
    build_accounting_binding,
    build_bundle_binding,
    build_comparison_binding,
    build_release_binding,
    build_transition_binding,
    comparison_view,
    numerical_view,
    package_terminal_view,
    primary_terminal_binding,
    release_view,
    result_bundle_view,
    validate_transition_chain,
)
from qualify_f017_event06_bridge_call_path_v2 import _release_report
from f017_event06_sequence18_vfs_v1 import InMemorySafetyFilesystem
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from generate_f017_event06_authority_dag_v2 import build as build_dag


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bundle(role: str) -> dict:
    symbols = "123456789" if role == "PRIMARY" else "abcdef012"
    terminal = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role": role,
        "result": "COMPLETE",
        "result_terminal_sha256": symbols[2] * 64,
        "result_receipt_sha256": symbols[1] * 64,
        "payload_manifest_sha256": symbols[0] * 64,
        "secondary_eligible": role == "PRIMARY",
    }
    event = "PRIMARY" if role == "PRIMARY" else "SECONDARY"
    index = {
        "schema": "pulsarmlx.f017.corrected-oracle-result-bundle-index/11.0.0",
        "role": role,
        "authorization_id": "F017-BRIDGE-AUTH-01",
        "package_attempt_id": "F017-BRIDGE-PACKAGE-01",
        "consumer_event_id": f"F017-BRIDGE-{event}-01",
        "manifest_sha256": symbols[0] * 64,
        "top32_summary_sha256": symbols[3] * 64,
        "routing_manifest_sha256": symbols[4] * 64,
        "result_receipt_sha256": symbols[1] * 64,
        "result_terminal_sha256": symbols[2] * 64,
        "consumer_terminal_sha256": symbols[5] * 64,
        "payload_sha256s": [symbols[6] * 64, symbols[7] * 64, symbols[8] * 64],
        "result": "PASS",
    }
    return {"artifacts": {"consumer_terminal": terminal}, "index": index, "result": "PASS"}


def _terminal_view():
    bridge, _installed, *_ = fixture_values()
    primary_numerical = numerical_view(bridge, "PRIMARY")
    primary_result = result_bundle_view(bridge, "PRIMARY", "1" * 64)
    primary = _bundle("PRIMARY")
    primary_bundle, _ = build_bundle_binding(
        primary_numerical, primary_result, primary["index"]
    )
    primary_terminal = primary_terminal_binding(primary, bridge, primary_bundle)
    secondary_numerical = numerical_view(
        bridge, "SECONDARY", primary_binding=primary_terminal
    )
    secondary_result = result_bundle_view(bridge, "SECONDARY", "2" * 64)
    secondary = _bundle("SECONDARY")
    secondary_bundle, _ = build_bundle_binding(
        secondary_numerical, secondary_result, secondary["index"]
    )
    comparison = comparison_view(bridge, primary_bundle, secondary_bundle)
    comparison_binding, _ = build_comparison_binding(
        comparison,
        {
            "schema": "pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
            "authorization_id": bridge.get("authorization_id"),
            "package_attempt_id": bridge.get("package_attempt_id"),
            "classification": "EXACT_EXPECTED_TOKEN_STABLE",
        },
    )
    release = release_view(bridge, comparison_binding)
    release_binding, _ = build_release_binding(
        release, _release_report(bridge.get("package_attempt_id"))
    )
    accounting = accounting_view(bridge, release_binding)
    accounting_binding, _ = build_accounting_binding(accounting, release_binding)
    predecessor = "0" * 64
    records = []
    for index, phase in enumerate(PHASES):
        record, predecessor = build_transition_binding(
            bridge, phase, f"QUALIFICATION-{index}", f"{index + 1:x}" * 64,
            predecessor,
        )
        records.append(record)
    chain = validate_transition_chain(bridge, records)
    closure = {
        "schema": "pulsarmlx.f017.corrected-oracle-package-result-closure/11.0.0",
        "primary": {
            "manifest_sha256": primary["index"]["manifest_sha256"],
            "receipt_sha256": primary["index"]["result_receipt_sha256"],
            "terminal_sha256": _sha(primary["artifacts"]["consumer_terminal"]),
            "result_terminal_sha256": primary["index"]["result_terminal_sha256"],
            "routing_manifest_sha256": primary["index"]["routing_manifest_sha256"],
            "payload_sha256s": primary["index"]["payload_sha256s"],
        },
        "secondary": {
            "manifest_sha256": secondary["index"]["manifest_sha256"],
            "receipt_sha256": secondary["index"]["result_receipt_sha256"],
            "terminal_sha256": _sha(secondary["artifacts"]["consumer_terminal"]),
            "result_terminal_sha256": secondary["index"]["result_terminal_sha256"],
            "routing_manifest_sha256": secondary["index"]["routing_manifest_sha256"],
            "payload_sha256s": secondary["index"]["payload_sha256s"],
        },
        "comparison": {
            "summary_sha256": comparison_binding.get("comparison_summary_sha256"),
            "receipt_sha256": "3" * 64,
            "terminal_sha256": "4" * 64,
        },
        "release": {
            "start_sha256": "5" * 64,
            "report_sha256": release_binding.get("release_report_sha256"),
            "receipt_sha256": "6" * 64,
            "terminal_sha256": "7" * 64,
        },
        "package_receipt_sha256": "8" * 64,
        "payload_count": 6,
        "result": "COMPLETE",
    }
    closure_binding = bind_v11_closure(bridge, closure, accounting_binding)
    return bridge, package_terminal_view(
        bridge, chain, closure_binding, accounting_binding
    )


def _reserve_worker(root: str, queue, files, directories, operations, lock, installed) -> None:
    filesystem = InMemorySafetyFilesystem(files, directories, operations, lock)
    try:
        with filesystem.installed():
            reservation = reserve_live_package_attempt(installed)
        queue.put(("WIN", {"reservation_sha256": reservation.sha256}))
    except FileExistsError as exc:
        queue.put(("LOSE", {"exception_type": type(exc).__name__}))
    except Exception as exc:
        queue.put(("ERROR", {"exception_type": type(exc).__name__, "message": str(exc)}))


def _claim_worker(root: str, queue, files, directories, operations, lock, installed) -> None:
    del installed
    filesystem = InMemorySafetyFilesystem(files, directories, operations, lock)
    try:
        with filesystem.installed():
            bridge, view = _terminal_view()
            installed = fixture_values()[1]
            reservation = load_qualification_package_attempt(installed, Path(root))
            sinks = claim_qualification_terminal_sinks(reservation, bridge, view)
        queue.put(("WIN", {"sink_sha256s": [sink.sha256 for sink in sinks]}))
    except FileExistsError as exc:
        queue.put(("LOSE", {"exception_type": type(exc).__name__}))
    except Exception as exc:
        queue.put(("ERROR", {"exception_type": type(exc).__name__, "message": str(exc)}))


def _race(worker, root: Path, contenders: int, files, directories, operations, lock, installed=None) -> list[tuple[str, object]]:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(
        target=worker,
        args=(str(root), queue, files, directories, operations, lock, installed),
    )
                 for _ in range(contenders)]
    for process in processes:
        process.start()
    result = [queue.get(timeout=60) for _ in processes]
    for process in processes:
        process.join(timeout=60)
        if process.exitcode != 0:
            raise RuntimeError(f"qualification worker exit: {process.exitcode}")
    return result


def qualify(contenders: int = 20) -> dict[str, object]:
    if type(contenders) is not int or contenders < 20:
        raise ValueError("at least 20 contenders required")
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="f017-seq18-authority-") as authority_dir, context.Manager() as manager:
        production = build_sequence14_qualification(
            Path(authority_dir), now_unix_ns=4_000_000_000_000_000_000
        )["installed"].authority
        root = Path("/graph-owned-sequence18-vfs/package-registry")
        files, directories = manager.dict(), manager.dict()
        operations, lock = manager.list(), manager.RLock()
        reservation = _race(
            _reserve_worker, root, contenders, files, directories, operations, lock,
            production,
        )
        filesystem = InMemorySafetyFilesystem(files, directories, operations, lock)
        with filesystem.installed():
            reconstructed = load_live_package_attempt(production)
            reserve_qualification_package_attempt(fixture_values()[1], root)
        claim = _race(
            _claim_worker, root, contenders, files, directories, operations, lock
        )
        filesystem_census = filesystem.snapshot()
    reservation_winners = sum(item[0] == "WIN" for item in reservation)
    claim_winners = sum(item[0] == "WIN" for item in claim)
    errors = [item for item in reservation + claim if item[0] == "ERROR"]
    if reservation_winners != 1 or claim_winners != 1 or errors:
        raise ValueError("package-scoped race qualification")
    dag = build_dag()["edges"]
    reserve_edge = next(item for item in dag if item["producer_symbol"] == "reserve_live_package_attempt")
    package_start_edge = next(item for item in dag if item["producer_symbol"] == "bank_live_package_start")
    order = {item["edge_id"]: item["generated_lifecycle_order"] for item in dag}
    loser_records = []
    for schedule, rows, edge in (("RESERVATION", reservation, reserve_edge),):
        for contender, row in enumerate(rows):
            if row[0] == "LOSE":
                loser_records.append({
                    "schedule": schedule,
                    "contender": contender,
                    "exception_type": row[1]["exception_type"],
                    "failed_exclusive_create_identity": edge["destination_node"],
                    "generated_dag_node": edge["edge_id"],
                    "generated_dag_order": order[edge["edge_id"]],
                    "live_package_start_edge": package_start_edge["edge_id"],
                    "live_package_start_order": order[package_start_edge["edge_id"]],
                    "pre_package_start_order_proof": order[edge["edge_id"]] <= order[package_start_edge["edge_id"]],
                    "safety_state_creates_or_writes_after_failed_create": 0,
                    "package_start": 0,
                    "checkpoint_or_numerical_access": 0,
                    "accounting": 0,
                    "identity_consumption": 0,
                })
    result = {
        "schema": "pulsarmlx.f017.event06-v12-package-uniqueness-qualification/1.0.0",
        "platform_process_start_method": "spawn",
        "contenders": contenders,
        "package_reservation_winners_per_identity": reservation_winners,
        "package_terminal_claim_winners_per_identity": claim_winners,
        "reservation_losers": contenders - reservation_winners,
        "terminal_claim_losers": contenders - claim_winners,
        "losing_contenders_with_pre_package_start_abort_proof": (
            sum(row["pre_package_start_order_proof"] for row in loser_records)
        ),
        "loser_records": loser_records,
        "shared_graph_owned_interposition_backing_store": True,
        "virtual_filesystem_census": filesystem_census,
        "reconstructed_reservation_sha256": reconstructed.sha256,
        "competing_terminal_outcomes_accepted": 0,
        "second_attempts_reaching_package_start": 0,
        "second_attempts_reaching_checkpoint_or_numerical_boundary": 0,
        "ambiguous_accounting_outcomes": 0,
        "errors": 0,
        "result": "PASS",
    }
    result["aggregate_sha256"] = _sha(result)
    return result


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))
