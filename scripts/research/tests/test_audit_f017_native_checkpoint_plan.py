from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/research/audit_f017_native_checkpoint_plan.py"
SPEC = importlib.util.spec_from_file_location("f017_plan_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def authorities():
    return (
        MODULE.strict_json(ROOT / "docs/validation/glm52-checkpoint.json"),
        MODULE.strict_json(ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"),
    )


def test_exact_committed_1809_tensor_plan_passes_without_checkpoint_access():
    result = MODULE.audit(*authorities())
    assert result["status"] == "PASS"
    assert result["tensor_count"] == 1809
    assert result["layer_count"] == 79
    assert len(result["quant_formats"]) == 11
    assert result["checkpoint_shard_opens"] == 0
    assert result["checkpoint_payload_reads"] == 0


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda m, c: c["tensors"][0].update(type_id=13), "type-ID mismatch"),
        (lambda m, c: c["tensors"][0].update(type="UNKNOWN"), "unsupported format"),
        (lambda m, c: c["tensors"][0].update(data_offset_abs=1), "offset/alignment"),
        (lambda m, c: c["tensors"][1].update(name=c["tensors"][0]["name"]), "duplicate logical"),
        (lambda m, c: c["tensors"][0].update(file="alternate.gguf"), "unknown shard"),
        (lambda m, c: c["tensors"][0].update(data_offset_abs=10**15), "exceeds shard"),
        (lambda m, c: c["tensors"][1].update(data_offset_abs=c["tensors"][0]["data_offset_abs"]), "overlapping tensors"),
        (lambda m, c: c.update(tensor_count=1808), "1,809"),
        (lambda m, c: c["kv_selected"].update(embedding_length=1), "model architecture"),
        (lambda m, c: m.update(file_count=5), "six shards"),
    ],
)
def test_plan_mutations_fail_closed(mutation, message):
    manifest, catalog = authorities()
    manifest, catalog = copy.deepcopy(manifest), copy.deepcopy(catalog)
    mutation(manifest, catalog)
    with pytest.raises(ValueError, match=message):
        MODULE.audit(manifest, catalog)
