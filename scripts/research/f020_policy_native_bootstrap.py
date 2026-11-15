"""Compiled child bootstrap. Hash the entire ordered verifier before executing project code."""
import hashlib
import json
import os
import re
import stat
import sys
import types
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "duplicate verifier JSON key")
        result[k] = v
    return result


def strict(raw):
    def invalid(value):
        raise ValueError("invalid verifier JSON number " + value)
    return json.loads(raw, object_pairs_hook=unique, parse_float=invalid, parse_constant=invalid)


def verified_modules(root, bindings):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "isolated verifier required")
    for name in ("CPATH", "LIBRARY_PATH", "MANPATH", "SDKROOT", "__CF_USER_TEXT_ENCODING", "LC_CTYPE"):
        os.environ.pop(name, None)
    require(set(os.environ) == {"HOME", "PATH"} and Path(os.environ["HOME"]).is_absolute()
            and os.environ["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin", "verifier environment")
    require(type(bindings) is list and 1 <= len(bindings) <= 32, "verifier population")
    require(root.is_absolute() and root.resolve(strict=True) == root, "verifier root")
    sources = {}
    total = 0
    for pair in bindings:
        require(type(pair) is list and len(pair) == 2, "verifier binding")
        name, digest = pair
        require(type(name) is str and re.fullmatch(r"f020_[a-z0-9_]+", name)
                and name not in sources and name not in sys.modules
                and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "verifier name/digest")
        p = root / (name + ".py")
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 524288, "bounded verifier file")
            raw = stream.read(524289)
            after = os.fstat(fd)
        total += len(raw)
        require(total <= 2 << 20 and len(raw) == before.st_size and os.path.samestat(before, p.lstat())
                and before.st_ctime_ns == after.st_ctime_ns and hashlib.sha256(raw).hexdigest() == digest,
                "compiled verifier source")
        sources[name] = (p, raw)
    require(list(sources)[-1] == "f020_policy_native_supervise", "verifier entrypoint")
    for name, (p, raw) in sources.items():
        module = types.ModuleType(name)
        module.__file__ = str(p)
        sys.modules[name] = module
        exec(compile(raw, str(p), "exec"), module.__dict__)
    return module


if __name__ == "__main__":
    require(len(sys.argv) == 4 and all(len(v.encode()) <= 8192 for v in sys.argv[1:]), "verifier arguments")
    bindings = strict(sys.argv[1])
    verifier = verified_modules(Path.cwd() / "scripts/research", bindings)
    verifier.verify_child(Path(sys.argv[2]), strict(sys.argv[3]), dict(bindings))
