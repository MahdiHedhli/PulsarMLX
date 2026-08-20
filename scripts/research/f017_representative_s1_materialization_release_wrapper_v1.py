#!/usr/bin/env python3
"""One-shot checkpoint-free S1 reconstruction and durable retention wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any

from f017_representative_expert_ledger_adapter_v1 import current_ledger
from f017_representative_s1_materialization_executor_v1 import reconstruct, EXPECTED_S1_SHA256


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-materialization-single-use-release-v1.json"
OUTPUT_NAME = "representative-s1.f32le"
MANIFEST_NAME = "representative-s1-private-manifest-v1.json"


class ReleaseError(RuntimeError): pass


def require(value: bool, message: str) -> None:
    if not value: raise ReleaseError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def sha_path(path: Path) -> str: return sha(path.read_bytes())


def fixed_paths(home: Path | None = None) -> dict[str, Path]:
    home = home or Path.home()
    root = home / ".local/share/pulsarmlx/f017/representative-s1-materialization-release-1"
    return {
        "candidate": ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-candidate-v3.json",
        "s0": Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-vocabulary/.pulsarmlx-local/dprefix-exact-1/retained/layer_3_entry.f32le"),
        "s0_manifest": Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-vocabulary/.pulsarmlx-local/dprefix-exact-1/retained/manifest.json"),
        "attention_retention": home / ".local/share/pulsarmlx/f017/representative-m1f0-release-1/retention",
        "root": root, "state": root / "attempt-state", "outputs": root / "outputs",
        "output": root / "outputs" / OUTPUT_NAME, "manifest": root / "outputs" / MANIFEST_NAME,
    }


def open_dir(path: Path, mode: int = 0o700) -> int:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), "DIRECTORY_IDENTITY")
    require(stat.S_IMODE(before.st_mode) == mode and before.st_uid == os.getuid(), "DIRECTORY_MODE")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    after = os.fstat(fd)
    require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), "DIRECTORY_SUBSTITUTION")
    return fd


def publish(fd: int, name: str, raw: bytes, mode: int = 0o400) -> str:
    require(Path(name).name == name, "BASENAME")
    try: os.stat(name, dir_fd=fd, follow_symlinks=False); raise ReleaseError("DESTINATION_EXISTS")
    except FileNotFoundError: pass
    temporary = f".{name}.{secrets.token_hex(16)}"
    out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=fd)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(out, view); require(count > 0, "SHORT_WRITE"); view = view[count:]
        os.fsync(out); os.fchmod(out, mode); os.fsync(out)
    finally: os.close(out)
    try:
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.fsync(fd); os.unlink(temporary, dir_fd=fd); os.fsync(fd)
        check = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
        try:
            metadata = os.fstat(check)
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == mode, "READBACK_METADATA")
            observed = b""
            while True:
                chunk = os.read(check, 1024 * 1024)
                if not chunk: break
                observed += chunk
            require(observed == raw, "READBACK_BYTES")
        finally: os.close(check)
    finally:
        try: os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError: pass
    return sha(raw)


def state_write(root: Path, name: str, value: dict[str, Any]) -> str:
    fd = open_dir(root)
    try: return publish(fd, name, canonical(value))
    finally: os.close(fd)


def preflight(release_path: Path, home: Path | None = None) -> tuple[dict[str, Any], dict[str, Path]]:
    release = json.loads(release_path.read_text(encoding="utf-8")); paths = fixed_paths(home)
    require(release.get("schema") == "pulsarmlx.f017.representative-s1-materialization-single-use-release", "RELEASE_SCHEMA")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL" and release.get("real_event_authorized") is False, "RELEASE_STATUS")
    accounting = release.get("accounting", {})
    require(accounting == {"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_materializations":1,"ffn_compositions":0,"s2_constructions":0,"ledger_before":175,"ledger_after":175}, "ACCOUNTING")
    require(release.get("stop_boundary") == "AFTER_REPRESENTATIVE_S1_RETENTION_ONLY", "STOP_BOUNDARY")
    for binding in release.get("bindings", {}).values():
        require(sha_path(ROOT / binding["path"]) == binding["sha256"], "BINDING_SHA")
    ledger = current_ledger(); require(ledger["current_ledger"] == 175 and ledger["checkpoint_reads"] == 0 and ledger["shard_opens"] == 0, "LEDGER")
    require(not paths["state"].exists() and not paths["output"].exists() and not paths["manifest"].exists(), "PRIOR_STATE")
    require(not any("checkpoint" in key.lower() or "shard" in key.lower() for key in release.get("runtime_interface", {})), "CHECKPOINT_INTERFACE")
    return release, paths


def execute(release_path: Path) -> dict[str, Any]:
    release, paths = preflight(release_path)
    paths["root"].mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(paths["root"], 0o700)
    paths["outputs"].mkdir(mode=0o700); os.mkdir(paths["state"], 0o700)
    parent = open_dir(paths["root"]); os.fsync(parent); os.close(parent)
    attempt_sha = state_write(paths["state"], "attempt-start.json", {"schema":"pulsarmlx.f017.representative-s1-attempt-start","event_id":release["event_id"],"release_id":release["release_id"],"attempt_id":release["attempt_id"],"release_sha256":sha_path(release_path),"no_retry":True,"no_resume":True})
    start_sha = state_write(paths["state"], "materialization-start.json", {"schema":"pulsarmlx.f017.representative-s1-materialization-start","attempt_sha256":attempt_sha,"s1_materializations":1,"checkpoint_reads":0,"shard_opens":0})
    output_sha = manifest_sha = receipt_sha = None
    try:
        raw, sources = reconstruct(paths["candidate"], paths["attention_retention"], paths["s0"])
        require(sha(raw) == EXPECTED_S1_SHA256, "PRODUCED_SHA")
        output_fd = open_dir(paths["outputs"])
        try:
            output_sha = publish(output_fd, OUTPUT_NAME, raw)
            manifest = {"schema":"pulsarmlx.f017.representative-s1-private-manifest","schema_version":"1.0.0","artifact":{"path":OUTPUT_NAME,"semantic_role":"LAYER3_POST_ATTENTION_RESIDUAL","sha256":output_sha,"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"finite":True},"expected_equals_produced_equals_readback":True,"matching_complete_terminal_required":True}
            manifest_sha = publish(output_fd, MANIFEST_NAME, canonical(manifest))
        finally: os.close(output_fd)
        receipt_sha = state_write(paths["state"], "s1-execution-receipt.json", {"schema":"pulsarmlx.f017.representative-s1-execution-receipt","materialization_start_sha256":start_sha,"output_sha256":output_sha,"manifest_sha256":manifest_sha,"source_after_sha256":sources,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"ffn_compositions":0,"s2_constructions":0})
        terminal_sha = state_write(paths["state"], "terminal.json", {"schema":"pulsarmlx.f017.representative-s1-terminal","status":"COMPLETE","output_authority":True,"output_sha256":output_sha,"manifest_sha256":manifest_sha,"receipt_sha256":receipt_sha,"ledger":175})
        return {"result":"COMPLETE","output_sha256":output_sha,"manifest_sha256":manifest_sha,"receipt_sha256":receipt_sha,"terminal_sha256":terminal_sha,"ledger":175,"checkpoint_reads":0,"shard_opens":0,"s1_materializations":1}
    except BaseException as error:
        if not (paths["state"] / "terminal.json").exists():
            state_write(paths["state"], "terminal.json", {"schema":"pulsarmlx.f017.representative-s1-terminal","status":"TERMINAL_FAILURE","output_authority":False,"reason":type(error).__name__,"ledger":175,"retry":False,"resume":False})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--preflight-only", action="store_true"); mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.preflight_only:
        release, _ = preflight(args.release); print(json.dumps({"result":"PRODUCTION_BINDINGS_RESOLVED","ledger":175,"checkpoint_reads":0,"shard_opens":0,"s1_materializations":0,"stop_boundary":release["stop_boundary"]}, sort_keys=True)); return 0
    print(json.dumps(execute(args.release), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
