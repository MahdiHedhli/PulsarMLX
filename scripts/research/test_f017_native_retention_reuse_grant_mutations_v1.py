#!/usr/bin/env python3
import copy, json, pathlib, tempfile
import validate_f017_native_retention_reuse_grant_v1 as validator

BASE = json.loads(validator.GRANT.read_text())
PACKAGE = json.loads(validator.PACKAGE.read_text())

def rejected(mutator, package_mutator=None):
    grant, package = copy.deepcopy(BASE), copy.deepcopy(PACKAGE)
    mutator(grant)
    if package_mutator: package_mutator(package)
    with tempfile.TemporaryDirectory() as td:
        gp, pp = pathlib.Path(td)/"g.json", pathlib.Path(td)/"p.json"
        gp.write_text(json.dumps(grant)); pp.write_text(json.dumps(package))
        try: validator.validate(gp, pp)
        except Exception: return True
    return False

cases = [
    lambda g: g.update(consumer_id="OTHER"),
    lambda g: g.update(consumer_source_sha256="0"*64),
    lambda g: g.update(d0_sha256="0"*64),
    lambda g: g.update(historical_master_ledger_sha256="0"*64),
    lambda g: g.update(tensor_count=39),
    lambda g: g["allowed_reads"].pop(),
    lambda g: g["allowed_reads"].append(copy.deepcopy(g["allowed_reads"][0])),
    lambda g: g["allowed_reads"][0].update(ordinal=1),
    lambda g: g["allowed_reads"][0].update(path="/tmp/wrong"),
    lambda g: g["allowed_reads"][0].update(sha256="0"*64),
    lambda g: g["allowed_reads"][0].update(byte_count=1),
    lambda g: g["allowed_reads"][0].update(encoding="F64_LE"),
    lambda g: g["allowed_reads"][0].update(shape=[1]),
    lambda g: g["allowed_reads"][0].update(source_commit="0"*40),
    lambda g: g["allowed_reads"][0].update(source_authority_sha256="0"*64),
    lambda g: g.update(checkpoint_fallback=True),
    lambda g: g.update(original_checkpoint_reads=1),
    lambda g: g.update(original_checkpoint_shard_opens=1),
    lambda g: g.update(historical_payload_ledger_delta=1),
    lambda g: g.update(attempts=2),
]

for index, case in enumerate(cases):
    assert rejected(case), f"mutation {index} passed"
print(f"PASS: {len(cases)}/{len(cases)} grant mutations rejected")
