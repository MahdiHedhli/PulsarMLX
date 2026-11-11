"""Static fixed-entry inspection for the copied resident child. No library loading."""

import hashlib
import os
import re
import select
import stat
import subprocess
import time
from pathlib import Path
from f020_resident_mlp_fixtures import canonical

RUNTIME_SHA256 = "36d3439033afa76443943a1a6967623cde063e435283ccf3b4e6a4e93a8755ca"
INSPECTION_BYTES = 1 << 20


def equal(actual, expected, reason):
    if canonical(actual) != canonical(expected):
        raise ValueError(reason)


def file_hash(p):
    digest = hashlib.sha256()
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("fixed-entry regular file required")
        remaining = before.st_size
        while remaining:
            block = stream.read(min(remaining, 1 << 20))
            if not block:
                raise ValueError("fixed file shortened during observation")
            remaining -= len(block)
            digest.update(block)
        after = os.fstat(fd)
        if stream.read(1) or (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("fixed file changed during observation")
    return digest.hexdigest()


def clean_inspector():
    if any(
        k.startswith("DYLD_")
        or k
        in ("LD_PRELOAD", "LD_LIBRARY_PATH", "OTOOL", "TOOLCHAINS", "DEVELOPER_DIR")
        for k in os.environ
    ):
        raise ValueError("inspector overrides forbidden")


def inspect_image(flag, image):
    """Bounded, read-only otool capture; no library is loaded by this inspector."""
    if flag not in ("-L", "-l"):
        raise ValueError("unsupported inspection flag")
    clean_inspector()
    argv = ["/usr/bin/otool", flag, str(image)]
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    data = bytearray()
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([p.stdout], [], [], left)[0]:
                raise ValueError("otool inspection deadline")
            block = os.read(
                p.stdout.fileno(), min(65536, INSPECTION_BYTES + 1 - len(data))
            )
            if not block:
                break
            data.extend(block)
            if len(data) > INSPECTION_BYTES:
                raise ValueError("otool inspection output bound")
        if p.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise ValueError("otool inspection failed")
        return bytes(data).decode("utf-8")
    finally:
        if p.poll() is None:
            p.kill()
        try:
            p.wait(timeout=5)
        finally:
            p.stdout.close()


def load_commands(text, image):
    """Parse one thin Mach-O display, preserving typed imports and own IDs."""
    lines = text.splitlines()
    if (
        len(text.encode()) > INSPECTION_BYTES
        or not lines
        or lines[0] != str(image) + ":"
        or len(lines) > 16384
        or any(len(x) > 4096 or "\x00" in x for x in lines)
    ):
        raise ValueError("bounded single-image load commands")
    groups = []
    current = None
    for line in lines[1:]:
        match = re.fullmatch(r"Load command (\d+)", line)
        if match:
            if int(match[1]) != len(groups) or len(groups) >= 512:
                raise ValueError("load command sequence/bound")
            current = []
            groups.append(current)
        elif current is None:
            if line.strip():
                raise ValueError("unframed load command")
        else:
            current.append(line.strip())
    if not groups:
        raise ValueError("missing load commands")
    result = []
    imports = {
        "LC_LOAD_DYLIB",
        "LC_LOAD_WEAK_DYLIB",
        "LC_REEXPORT_DYLIB",
        "LC_LOAD_UPWARD_DYLIB",
    }
    for number, fields in enumerate(groups):
        cmds = [x[4:] for x in fields if x.startswith("cmd ")]
        sizes = [x[8:] for x in fields if x.startswith("cmdsize ")]
        if (
            len(cmds) != 1
            or not re.fullmatch(r"LC_[A-Z0-9_]+", cmds[0])
            or len(sizes) != 1
            or not sizes[0].isdigit()
            or not 8 <= int(sizes[0]) <= 65536
        ):
            raise ValueError("malformed load command header")
        cmd = cmds[0]
        record = {"number": number, "command": cmd}
        if cmd in imports or cmd == "LC_ID_DYLIB" or cmd == "LC_RPATH":
            key = "path" if cmd == "LC_RPATH" else "name"
            values = [
                re.fullmatch(key + r" (.+) \(offset (\d+)\)", x)
                for x in fields
                if x.startswith(key + " ")
            ]
            if (
                len(values) != 1
                or values[0] is None
                or not (12 if key == "path" else 24)
                <= int(values[0][2])
                < int(sizes[0])
            ):
                raise ValueError("malformed dependency/rpath record")
            value = values[0][1]
            if any(ord(x) < 32 for x in value) or len(value.encode()) + int(
                values[0][2]
            ) + 1 > int(sizes[0]):
                raise ValueError("truncated dependency/rpath record")
            record.update(
                kind="rpath"
                if key == "path"
                else "own_id"
                if cmd == "LC_ID_DYLIB"
                else "import",
                value=value,
            )
        elif (
            any(x in cmd for x in ("DYLIB", "DYLINKER", "FVMLIB"))
            or cmd == "LC_DYLD_ENVIRONMENT"
        ):
            raise ValueError("unsupported dependency/environment load command")
        else:
            continue  # Not a dependency command; complete raw bytes remain bound.
        result.append(record)
    if sum(x.get("kind") == "own_id" for x in result) != 1:
        raise ValueError("one dylib own ID required")
    return result


def fixed_file(path):
    """Observe exactly this entry and its bounded symlink chain; never search."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute fixed entry required")
    pending = list(path.parts[1:])
    current = Path("/")
    links = []
    steps = 0
    while pending:
        steps += 1
        if steps > 1024 or len(links) > 32:
            raise ValueError("fixed-entry symlink traversal bound")
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            if len(links) >= 32:
                raise ValueError("fixed-entry symlink traversal bound")
            target = os.readlink(current)
            links.append(
                {
                    "path": str(current),
                    "target": target,
                    "device": info.st_dev,
                    "inode": info.st_ino,
                    "mtime_ns": info.st_mtime_ns,
                    "ctime_ns": info.st_ctime_ns,
                }
            )
            parts = Path(target).parts
            current = Path("/") if Path(target).is_absolute() else current.parent
            pending = list(parts[1:] if Path(target).is_absolute() else parts) + pending
        elif pending and not stat.S_ISDIR(info.st_mode):
            raise ValueError("fixed-entry non-directory component")
    info = current.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("fixed-entry regular file required")
    equal(str(path.resolve(strict=True)), str(current), "fixed-entry canonical path")
    return {
        "lexical": str(path),
        "canonical": str(current),
        "symlinks": links,
        "bytes": info.st_size,
        "mode": stat.S_IMODE(info.st_mode),
        "device": info.st_dev,
        "inode": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
        "sha256": file_hash(current),
    }


def retained_runtime(prefix, environment, bindings):
    """Fixed child-library-path policy; static evidence, never loaded-image proof."""
    clean_inspector()
    equal(
        environment["DYLD_LIBRARY_PATH"],
        str(prefix / "lib"),
        "fixed resident child search path",
    )
    if set(
        k
        for k in environment
        if k.startswith("DYLD_") or k in ("LD_PRELOAD", "LD_LIBRARY_PATH")
    ) != {"DYLD_LIBRARY_PATH"}:
        raise ValueError("unsupported child library overrides")
    linked = {}
    linkage_inspections = []
    for name in ("libmlx.dylib", "libmlxc.dylib"):
        image = prefix / "lib" / name
        listing = inspect_image("-L", image)
        lines = listing.splitlines()
        if not lines or lines[0] != str(image) + ":":
            raise ValueError("linkage inspection image")
        linked[name] = lines[1:]
        linkage_inspections.append(
            dict(
                image=name,
                bytes=len(listing.encode()),
                sha256=hashlib.sha256(listing.encode()).hexdigest(),
            )
        )
    names = ("libmlx.dylib", "libmlxc.dylib", "libjaccl.dylib")
    files = {name: fixed_file(prefix / "lib" / name) for name in names}
    equal(files["libjaccl.dylib"]["sha256"], RUNTIME_SHA256, "retained runtime bytes")
    if len({r["canonical"] for r in files.values()}) != 3:
        raise ValueError("competing image identities")
    records = []
    inspections = []
    seen_runtime = False
    for name in names:
        image = prefix / "lib" / name
        text = inspect_image("-l", image)
        commands = load_commands(text, image)
        if name in linked:
            displayed = [x.strip().split(" (compatibility")[0] for x in linked[name]]
            equal(
                displayed,
                [x["value"] for x in commands if x["kind"] != "rpath"],
                "typed/linkage dependency mismatch",
            )
        inspections.append(
            {
                "image": str(image),
                "method": "otool -l",
                "bytes": len(text.encode()),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "commands": commands,
            }
        )
        for command in commands:
            edge = {"image": str(image), **command}
            value = command["value"]
            kind = command["kind"]
            if kind == "rpath":
                edge["classification"] = "recorded_unselected_rpath"
            elif kind == "own_id":
                if Path(value).name != name:
                    raise ValueError("own install ID/image mismatch")
                edge["classification"] = "own_id_not_import"
            elif value.startswith(("/usr/lib/", "/System/Library/")):
                if os.path.normpath(value) != value:
                    raise ValueError("noncanonical system dependency")
                if os.path.lexists(prefix / "lib" / Path(value).name):
                    raise ValueError("competing fixed-prefix system override")
                edge["classification"] = "system_shared_cache_allowed"
            else:
                leaf = Path(value).name
                if leaf not in files:
                    raise ValueError("unexpected non-system dependency")
                target = files[leaf]
                if value != "@rpath/" + leaf and value not in (
                    target["lexical"],
                    target["canonical"],
                ):
                    raise ValueError("unsupported dependency resolution context")
                edge.update(
                    classification="retained_extra_runtime"
                    if leaf == "libjaccl.dylib"
                    else "pinned_MLX_image",
                    resolution="fixed_child_DYLD_LIBRARY_PATH_leaf_first_no_fallback",
                    lexical_candidate=target["lexical"],
                    canonical_target=target["canonical"],
                    observed_sha256=target["sha256"],
                )
                seen_runtime |= leaf == "libjaccl.dylib" and name in linked
            records.append(edge)
    if not seen_runtime:
        raise ValueError("retained runtime import missing")
    equal(
        {name: fixed_file(prefix / "lib" / name) for name in names},
        files,
        "static dependency inspection drift",
    )
    return {
        "schema": "pulsarmlx.retained-runtime-static/1",
        "policy": "fixed-prefix-child-library-path/1",
        "inspector_loader_overrides": "absent",
        "child_environment": {
            "inherited": "cleared",
            "keys": sorted(environment),
            "MLX_ENABLE_TF32": environment["MLX_ENABLE_TF32"],
            "DYLD_LIBRARY_PATH": str(prefix / "lib"),
        },
        "source_bindings": bindings,
        "linkage_inspections": linkage_inspections,
        "files": files,
        "edges": records,
        "inspections": inspections,
        "expected_runtime_sha256": RUNTIME_SHA256,
        "loaded_runtime_image_observed": False,
    }
