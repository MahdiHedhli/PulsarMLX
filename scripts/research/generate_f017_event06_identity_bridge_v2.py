#!/usr/bin/env python3
"""Generate the Sequence 12 prompt-bound identity bridge contract surfaces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-requirements-v1.json"
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-v2.json"
MODULE = ROOT / "scripts/research/f017_event06_identity_bridge_contract_v2.py"


def _contract(requirements: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.event06-v12-identity-to-numerical-bridge-contract/2.1.0",
        "requirements": REQUIREMENTS.relative_to(ROOT).as_posix(),
        "generation": requirements["generation"],
        "numerical_authority": requirements["numerical_authority"],
        "result_authority": requirements["result_authority"],
        "identity_input": requirements["identity_input"],
        "numerical_bridge": requirements["numerical_bridge"],
        "consumer_view": requirements["consumer_view"],
        "accounting_closure": requirements["accounting_closure"],
        "package_terminal": requirements["package_terminal"],
        "signature_graph_nodes": requirements["signature_graph_nodes"],
        "signature_graph_edges": requirements["signature_graph_edges"],
        "digest_edges": requirements["digest_edges"],
        "stage_vocabulary": requirements["stage_vocabulary"],
        "accounting_units": requirements["accounting_units"],
        "failure_outcomes": requirements["failure_outcomes"],
        "legacy_projection_permitted": False,
        "caller_created_mapping_permitted": False,
        "unknown_fields_permitted": False,
    }


def _module(contract: dict[str, object]) -> str:
    roles = contract["consumer_view"]["roles"]  # type: ignore[index]
    rows = {
        "IDENTITY_INPUT_SCHEMA": contract["identity_input"]["schema"],  # type: ignore[index]
        "IDENTITY_INPUT_FIELDS": tuple(contract["identity_input"]["fields"]),  # type: ignore[index]
        "IDENTITY_INPUT_TYPES": contract["identity_input"]["types"],  # type: ignore[index]
        "BRIDGE_SCHEMA": contract["numerical_bridge"]["schema"],  # type: ignore[index]
        "BRIDGE_FIELDS": tuple(contract["numerical_bridge"]["fields"]),  # type: ignore[index]
        "BRIDGE_TYPES": contract["numerical_bridge"]["types"],  # type: ignore[index]
        "CONSUMER_VIEW_SCHEMA": contract["consumer_view"]["schema"],  # type: ignore[index]
        "CONSUMER_VIEW_FIELDS": tuple(contract["consumer_view"]["fields"]),  # type: ignore[index]
        "CONSUMER_VIEW_TYPES": contract["consumer_view"]["types"],  # type: ignore[index]
        "CONSUMER_ROLES": tuple(roles),
        "ACCOUNTING_SCHEMA": contract["accounting_closure"]["schema"],  # type: ignore[index]
        "ACCOUNTING_FIELDS": tuple(contract["accounting_closure"]["fields"]),  # type: ignore[index]
        "ACCOUNTING_TYPES": contract["accounting_closure"]["types"],  # type: ignore[index]
        "PACKAGE_TERMINAL_SCHEMA": contract["package_terminal"]["schema"],  # type: ignore[index]
        "PACKAGE_TERMINAL_FIELDS": tuple(contract["package_terminal"]["fields"]),  # type: ignore[index]
        "PACKAGE_TERMINAL_TYPES": contract["package_terminal"]["types"],  # type: ignore[index]
        "SIGNATURE_GRAPH_NODES": tuple(contract["signature_graph_nodes"]),
        "SIGNATURE_GRAPH_EDGES": tuple(contract["signature_graph_edges"]),
        "DIGEST_EDGES": tuple(contract["digest_edges"]),
        "STAGE_VOCABULARY": tuple(contract["stage_vocabulary"]),
        "ACCOUNTING_UNITS": tuple(contract["accounting_units"]),
        "FAILURE_OUTCOMES": tuple(contract["failure_outcomes"]),
    }
    body = ["#!/usr/bin/env python3", '"""Generated collapsed-identity bridge contract. Do not edit."""', "from __future__ import annotations", ""]
    body.extend(f"{name} = {value!r}" for name, value in rows.items())
    return "\n".join(body) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    requirements = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    contract_bytes = (json.dumps(_contract(requirements), indent=2, sort_keys=True) + "\n").encode()
    module_bytes = _module(_contract(requirements)).encode()
    outputs = ((CONTRACT, contract_bytes), (MODULE, module_bytes))
    if args.check:
        if any(not path.exists() or path.read_bytes() != data for path, data in outputs):
            raise SystemExit("generated identity bridge contract is stale")
        return 0
    for path, data in outputs:
        path.write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
