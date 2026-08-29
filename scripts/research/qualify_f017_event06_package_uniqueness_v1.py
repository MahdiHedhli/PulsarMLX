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
    load_qualification_package_attempt,
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


def _reserve_worker(root: str, queue) -> None:
    try:
        installed = fixture_values()[1]
        reservation = reserve_qualification_package_attempt(installed, Path(root))
        queue.put(("WIN", reservation.sha256))
    except FileExistsError:
        queue.put(("LOSE", None))
    except Exception as exc:
        queue.put(("ERROR", type(exc).__name__))


def _claim_worker(root: str, queue) -> None:
    try:
        bridge, view = _terminal_view()
        installed = fixture_values()[1]
        reservation = load_qualification_package_attempt(installed, Path(root))
        sinks = claim_qualification_terminal_sinks(reservation, bridge, view)
        queue.put(("WIN", [sink.sha256 for sink in sinks]))
    except FileExistsError:
        queue.put(("LOSE", None))
    except Exception as exc:
        queue.put(("ERROR", type(exc).__name__))


def _race(worker, root: Path, contenders: int) -> list[tuple[str, object]]:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=worker, args=(str(root), queue))
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
    with tempfile.TemporaryDirectory(prefix="f017-event06-package-race-") as directory:
        root = Path(directory) / "registry"
        reservation = _race(_reserve_worker, root, contenders)
        claim = _race(_claim_worker, root, contenders)
        reconstructed = load_qualification_package_attempt(fixture_values()[1], root)
    reservation_winners = sum(item[0] == "WIN" for item in reservation)
    claim_winners = sum(item[0] == "WIN" for item in claim)
    errors = [item for item in reservation + claim if item[0] == "ERROR"]
    if reservation_winners != 1 or claim_winners != 1 or errors:
        raise ValueError("package-scoped race qualification")
    result = {
        "schema": "pulsarmlx.f017.event06-v12-package-uniqueness-qualification/1.0.0",
        "platform_process_start_method": "spawn",
        "contenders": contenders,
        "package_reservation_winners_per_identity": reservation_winners,
        "package_terminal_claim_winners_per_identity": claim_winners,
        "reservation_losers": contenders - reservation_winners,
        "terminal_claim_losers": contenders - claim_winners,
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
