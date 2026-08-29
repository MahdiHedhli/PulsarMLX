#!/usr/bin/env python3
"""Complete no-access Sequence 18 transaction qualification."""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import os
import pickle
import tempfile
from pathlib import Path
from unittest.mock import patch

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_dag_derived_control_path_v1 import run_full_call_path
from execute_f017_corrected_oracle_event_v12_bridge import _freeze, _thaw
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
import f017_event06_package_attempt_registry_v1 as historical
import f017_event06_package_attempt_registry_v2 as registry
from generate_f017_event06_authority_dag_v2 import build as build_dag
from qualify_f017_event06_package_uniqueness_v1 import qualify as qualify_uniqueness
from validate_f017_event06_authority_dag_v2 import (
    validate as validate_dag, validate_document as validate_dag_document,
)


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def qualify() -> dict[str, object]:
    passed = 0
    total = 0

    def rejected(operation, exceptions=(Exception,)):
        nonlocal passed, total
        total += 1
        try:
            operation()
        except exceptions:
            passed += 1
        else:
            raise AssertionError("unexpected mutation pass")

    signature = inspect.signature(registry.reserve_live_package_attempt)
    public_root_inputs = sum(
        any(token in name for token in ("root", "path", "directory", "registry", "config"))
        for name in signature.parameters
    )
    generic_keywords = sum(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    with tempfile.TemporaryDirectory(prefix="f017-sequence18-qualification-") as directory:
        root = Path(directory)
        package = build_sequence14_qualification(
            root / "authority", now_unix_ns=4_000_000_000_000_000_000
        )
        production = package["installed"].authority
        qualification = package["installed"]
        synthetic = fixture_values()[1]

        observed_roots = []
        with patch.object(
            registry, "_secure_directory",
            lambda path: observed_roots.append(path)
            or (_ for _ in ()).throw(RuntimeError("INTERPOSED_BEFORE_CREATE")),
        ):
            rejected(
                lambda: registry.reserve_live_package_attempt(production),
                (RuntimeError,),
            )
        if observed_roots != [registry.LIVE_REGISTRY_ROOT]:
            raise AssertionError("fixed live registry derivation")

        for name in (
            "root", "path", "directory", "registry", "configuration",
            "provider", "resolver", "callback", "options",
        ):
            rejected(
                lambda name=name: registry.reserve_live_package_attempt(
                    production, **{name: root / name}
                ),
                (TypeError,),
            )
        rejected(lambda: registry.reserve_live_package_attempt(qualification), (TypeError,))
        observations = []
        with patch.object(
            registry, "_prepare_qualification_registry",
            lambda value: observations.append(value),
        ):
            rejected(
                lambda: registry.reserve_qualification_package_attempt(
                    production, root / "must-not-observe"
                ),
                (ValueError,),
            )
        if observations:
            raise AssertionError("production authority reached qualification root")

        for candidate in (
            registry.LIVE_REGISTRY_ROOT,
            Path("/var/tmp/pulsarmlx-f017-event06-v12-package-registry"),
            registry.LIVE_REGISTRY_ROOT / "child",
            registry.LIVE_REGISTRY_ROOT.parent,
        ):
            rejected(
                lambda candidate=candidate: registry.reserve_qualification_package_attempt(
                    synthetic, candidate
                ),
                (ValueError,),
            )

        live_alias = root / "live-root-alias"
        live_alias.symlink_to(registry.LIVE_REGISTRY_ROOT, target_is_directory=True)
        rejected(
            lambda: registry.reserve_qualification_package_attempt(synthetic, live_alias),
            (ValueError,),
        )

        symlink_target = root / "symlink-target"
        symlink_target.mkdir(mode=0o700)
        symlink_root = root / "symlink-root"
        symlink_root.symlink_to(symlink_target, target_is_directory=True)
        rejected(
            lambda: registry.reserve_qualification_package_attempt(synthetic, symlink_root),
            (ValueError,),
        )

        reservation = registry.reserve_qualification_package_attempt(
            synthetic, root / "sealed-registry"
        )
        for operation in (
            lambda: copy.copy(reservation),
            lambda: copy.deepcopy(reservation),
            lambda: pickle.dumps(reservation),
            lambda: setattr(reservation, "sha256", "0" * 64),
            lambda: registry.ValidatedLivePackageAttemptReservation(),
            lambda: registry.ValidatedQualificationPackageAttemptReservation(),
        ):
            rejected(operation, (TypeError,))
        rejected(
            lambda: registry.reserve_qualification_package_attempt(
                synthetic, root / "sealed-registry"
            ),
            (FileExistsError,),
        )

        for operation in (
            lambda: historical.reserve_package_attempt(None),
            lambda: historical.claim_terminal_sinks(None, None, None, None, [], None),
            lambda: historical.claim_qualification_terminal_sinks(None, None, None),
            lambda: historical.bank_terminal(None, {}),
        ):
            rejected(operation, (RuntimeError,))

        # A source/DAG omission or source-blob substitution changes the exact
        # generated document and is therefore rejected for every edge.
        canonical_dag = build_dag()
        for index in range(len(canonical_dag["edges"])):
            changed = copy.deepcopy(canonical_dag)
            changed["edges"].pop(index)
            rejected(lambda changed=changed: validate_dag_document(changed), (ValueError,))
        for index in range(len(canonical_dag["edges"])):
            changed = copy.deepcopy(canonical_dag)
            changed["edges"][index]["source_blob_sha256"] = "f" * 64
            rejected(lambda changed=changed: validate_dag_document(changed), (ValueError,))

        run_digests = set()
        for index in range(20):
            run = run_full_call_path(root / f"full-call-{index:02d}")
            if (run["result"] != "PASS" or any(run["live_counters"].values())
                    or run["original_checkpoint_root_resolved"] is not False
                    or run["full_model_inference"] != "NONE"):
                raise AssertionError("qualification full call path")
            run_digests.add(run["aggregate_sha256"])
        if len(run_digests) != 1:
            raise AssertionError("qualification fresh-process determinism")

    uniqueness = qualify_uniqueness(20)
    dag = validate_dag()
    freeze_cases = ({}, [], [["a", 1], ["b", 2]], {"nested": [{}, []]})
    frozen_cases = [_freeze(value) for value in freeze_cases]
    if (len(set(frozen_cases)) != len(freeze_cases)
            or [_thaw(value) for value in frozen_cases] != list(freeze_cases)):
        raise AssertionError("injective execution-result freeze")
    if passed != total:
        raise AssertionError("mutation campaign")
    result = {
        "schema": "pulsarmlx.f017.event06-v12-package-transaction-qualification/2.0.0",
        "production_public_registry_root_inputs": public_root_inputs,
        "production_public_generic_keyword_inputs": generic_keywords,
        "production_authority_accepted_by_qualification_api": 0,
        "qualification_authority_accepted_by_production_api": 0,
        "cross_mode_reservation_or_sink_substitutions_accepted": 0,
        "production_fixed_root_interception_rehearsal": "PASS",
        "production_live_registry_creates_or_writes": 0,
        "qualification_live_root_aliases_accepted": 0,
        "execution_result_freeze_round_trips": len(freeze_cases),
        "qualification_full_call_path_no_access": "PASS",
        "qualification_full_call_path_repetitions": 20,
        "qualification_unique_aggregate_digests": 1,
        "package_uniqueness": uniqueness,
        "source_derived_dag": dag,
        "mutation_campaign": {
            "passed": passed,
            "total": total,
            "unexpected_passes": total - passed,
        },
        "event06_identities_instantiated_or_consumed": [0, 0],
        "authorization_package_primary_secondary_accounting": [0, 0, 0, 0],
        "original_checkpoint_root_resolved": False,
        "original_checkpoint_access": "NONE",
        "full_model_inference": "NONE",
        "event06_executed": False,
        "new_human_go_document_created": False,
        "historical_master_ledger": 175,
        "result": "PASS",
    }
    result["aggregate_sha256"] = _sha(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    qualified = qualify()
    if args.output is None:
        print(json.dumps(qualified, sort_keys=True, separators=(",", ":")))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(qualified, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
