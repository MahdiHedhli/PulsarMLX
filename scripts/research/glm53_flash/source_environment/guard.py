"""Phase-specific identity checks; measured drift control, not OS isolation."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import stat
import subprocess
import sys

BINDING_SHA = "843b998086df6aea6a6f7df0e0064ac8e1bb790d4683282118e6c8774bfed1c2"
UUID_SHA = "a7ae55a84a578f06d8eb8e4aa443f10499cbbeca61052264c3bf60a05b85bfaf"
MAX_GROWTH = 8 * 1024**3
RESERVE = 512 * 1024**2

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def confined(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root) or path.resolve() != path:
        raise ValueError("phase path must be confined and symlink-free")
    if path.exists() and path.stat().st_dev != root.stat().st_dev:
        raise ValueError("phase path device mismatch")
    return path

def admit_phase(phase, query_volume=True):
    phase = Path(phase).absolute()
    root = phase.parent
    if phase.name != "source-environment-v1" or not phase.is_dir():
        raise ValueError("existing phase role required")
    confined(root, phase)
    binding = confined(root, root / "machine-binding.local.json")
    if sha(binding) != BINDING_SHA or stat.S_IMODE(binding.stat().st_mode) & 0o077:
        raise ValueError("machine binding identity/mode mismatch")
    data = json.loads(binding.read_text())
    if Path(data["workspace"]) != root:
        raise ValueError("workspace binding mismatch")
    mount = Path(data["volume"]["MountPoint"])
    if root.stat().st_dev != mount.stat().st_dev:
        raise ValueError("workspace volume changed")
    if query_volume:
        info = plistlib.loads(subprocess.check_output(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)], timeout=10))
        if (hashlib.sha256(info["VolumeUUID"].upper().encode()).hexdigest() != UUID_SHA
                or info["MountPoint"] != str(mount) or not info["WritableVolume"]
                or info.get("Internal") is not False):
            raise ValueError("mounted external volume identity/readiness mismatch")
    for name in ("evidence", "source", "wheelhouse", "cache", "scratch", "fixtures", "runs", "env-g1"):
        path = confined(phase, phase / name)
        if not path.is_dir():
            raise ValueError("required phase role absent: " + name)
    if (phase / "runs/STOP_NUMERICAL.json").exists():
        raise ValueError("unconfirmed prior teardown: numerical launch blocked")
    return phase

def verify_environment(phase):
    phase = Path(phase)
    install = json.loads((phase / "evidence/installation-g1.json").read_text())
    path = phase / "evidence/environment-manifest-g1.json"
    if sha(path) != install["manifest_sha256"]:
        raise ValueError("environment manifest changed")
    manifest = json.loads(path.read_text())
    if sha(phase / "evidence/wheel-lock-g1.json") != manifest["wheel_lock_sha256"]:
        raise ValueError("environment lock changed")
    env = phase / "env-g1"
    expected = {row["path"]: row for row in manifest["files"]}
    actual = {str(f.relative_to(env)) for f in env.rglob("*") if f.is_file()}
    if actual != set(expected):
        raise ValueError("environment file set changed")
    for rel, row in expected.items():
        path = env / rel
        if not path.resolve().is_relative_to(env) or sha(path) != row["sha256"]:
            raise ValueError("environment file content changed: " + rel)
    return manifest

def verify_origin(module, phase, manifest):
    path = Path(module.__file__).absolute()
    env = Path(phase) / "env-g1"
    if not path.is_relative_to(env) or path.resolve() != path:
        raise ValueError("module origin outside admitted environment")
    relative = str(path.relative_to(env))
    rows = {x["path"]: x for x in manifest["files"]}
    if relative not in rows or sha(path) != rows[relative]["sha256"]:
        raise ValueError("module origin/content not in admitted manifest")
    return {"module": module.__name__, "role_path": relative, "sha256": rows[relative]["sha256"]}

def verify_child_interpreter(phase):
    env = Path(phase) / "env-g1"
    if (Path(sys.prefix).resolve() != env.resolve() or sys.prefix == sys.base_prefix
            or not sys.flags.isolated or not sys.dont_write_bytecode):
        raise ValueError("isolated admitted interpreter required")

def input_manifest(phase):
    phase = Path(phase)
    src = phase.parent / "repos/PulsarMLX"
    paths = list((src / "scripts/research/glm53_flash/source_environment").glob("*.py"))
    paths += list((src / "scripts/research/tests").glob("test_glm53_flash_source_environment_*.py"))
    paths += [f for f in (src / "docs/glm53-flash/source-environment-v1").rglob("*") if f.is_file()]
    paths += [f for f in (src / "fixtures/research/glm53-flash-source-environment-v1").rglob("*") if f.is_file()]
    paths += [phase / "source/group_expert_select.capsule.py", phase / "evidence/capsule-binding.json"]
    paths += list((phase / "evidence").glob("*-source-lock.json"))
    paths += [f for f in (phase / "source").rglob("*") if f.is_file()]
    paths += [phase / "evidence/retained-metadata-custody.json", phase / "evidence/predecessor-source-lock.json"]
    paths += [src / "fixtures/research/glm53-flash-tiny-v1/arithmetic.json"]
    rows = []
    for path in sorted(set(paths)):
        confined(phase.parent, path)
        role = "source-repo/" + str(path.relative_to(src)) if path.is_relative_to(src) else "phase/" + str(path.relative_to(phase))
        rows.append({"path": role, "bytes": path.stat().st_size, "sha256": sha(path)})
    return rows

def manifest_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def phase_size(phase):
    phase = Path(phase)
    size = sum(f.stat().st_size for f in phase.rglob("*") if f.is_file() and not f.is_symlink())
    root = phase.parent
    extra = [root / "repos/PulsarMLX/docs/glm53-flash/source-environment-v1",
             root / "repos/PulsarMLX/scripts/research/glm53_flash/source_environment",
             root / "repos/PulsarMLX/fixtures/research/glm53-flash-source-environment-v1",
             root / "repos/PulsarMLX-Prompts/GLM53-Flash/source-environment-v1"]
    size += sum(f.stat().st_size for d in extra for f in d.rglob("*") if f.is_file() and not f.is_symlink())
    size += sum(f.stat().st_size for f in (root / "repos/PulsarMLX/scripts/research/tests").glob("test_glm53_flash_source_environment_*.py"))
    return size
