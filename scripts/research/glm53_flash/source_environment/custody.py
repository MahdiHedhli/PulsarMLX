"""Bounded same-buffer reads under the accepted retained-text scope amendment."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

LOCK_SHA = "f7708546c13ea90fc0a4abc0f3152f596f3d8818eae87bc75b3f05e8490f6f11"
REVISION = "d43ea8b407ce4e9c25e6ac9baec3feab70d9f5f3"
ARTIFACT = "pipenetwork--GLM-5.3-Flash-MLX-mixed-4_8bit--" + REVISION
EXPECTED = {
    "config.json": "3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d",
    "model.safetensors.index.json": "5e0a3768db6fb795c4846bed713785a17d336f4cc4494b4f6b28f75082314383",
    "chat_template.jinja": "34d5ee66b12fa6446cdae131c352b8f68cd85369e0e6fda115583805fada3891",
}
MAX_BODY = 16 * 1024**2

class CustodyError(ValueError):
    pass

def unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise CustodyError("duplicate JSON key")
        output[key] = value
    return output

def parse_lock(raw):
    if len(raw) > 64 * 1024 or hashlib.sha256(raw).hexdigest() != LOCK_SHA:
        raise CustodyError("predecessor lock cap/hash mismatch")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if value["schema"] != "pulsarmlx.glm53_flash.model_map_sources.v1":
        raise CustodyError("lock schema mismatch")
    selected = [x for x in value["sources"] if x.get("role") == "selected-artifact"]
    if len(selected) != 1:
        raise CustodyError("ambiguous selected artifact")
    selected = selected[0]
    if (selected["repository"] != "pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit"
            or selected["revision"] != REVISION):
        raise CustodyError("selected artifact/revision mismatch")
    hashes = {}
    for basename, inline in EXPECTED.items():
        key = "external-model-metadata/" + ARTIFACT + "/" + basename
        digest = selected["files"].get(key)
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest) or digest != inline:
            raise CustodyError("exact lock entry absent/inconsistent")
        hashes[basename] = digest
    return hashes

def read_bounded(root, components, expected_sha, cap=MAX_BODY):
    if type(cap) is not int or not 0 < cap <= MAX_BODY:
        raise CustodyError("invalid read ceiling")
    if not components or any(not x or x in (".", "..") or "/" in x or "\\" in x for x in components):
        raise CustodyError("invalid named path component")
    root = Path(root).absolute()
    if root.resolve() != root:
        raise CustodyError("noncanonical role root")
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in components[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        fd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
            raise CustodyError("nonregular/oversized body rejected before read")
        blocks, size = [], 0
        while size < before.st_size:
            block = os.read(fd, min(65536, before.st_size - size))
            if not block:
                break
            blocks.append(block)
            size += len(block)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        if size != before.st_size or any(getattr(before, x) != getattr(after, x) for x in fields):
            raise CustodyError("body descriptor identity/size changed")
        raw = b"".join(blocks)
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected_sha:
            raise CustodyError("body hash mismatch")
        raw.decode("utf-8")
        return raw, {"observed_size_before_read": before.st_size, "bytes_read": size,
                     "sha256": observed, "identity_size_unchanged": True,
                     "regular_file_before_read": True, "named_component_nofollow": True,
                     "cap_bytes": cap, "buffer_semantic_use": "same verified bytes"}
    except OSError as exc:
        raise CustodyError("named path no-follow/read failure: " + type(exc).__name__) from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)

def working_body(phase, basename):
    phase = Path(phase)
    if basename not in EXPECTED:
        raise CustodyError("file not admitted by amendment")
    lock, _ = read_bounded(phase, ["evidence", "predecessor-source-lock.json"], LOCK_SHA, cap=64*1024)
    hashes = parse_lock(lock)
    return read_bounded(phase, ["source", "retained-metadata", basename], hashes[basename])
