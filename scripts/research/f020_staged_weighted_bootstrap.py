"""Embedded in the staged weighted binary. Validate every byte before importing any project code."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types


def verified_modules(root, bindings):
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError("isolated verifier interpreter required")
    # The system Python launcher adds SDK and manual-page search variables
    # after Command::env_clear. Remove them before executing any project source.
    for name in ("CPATH", "LIBRARY_PATH", "MANPATH", "SDKROOT", "__CF_USER_TEXT_ENCODING", "LC_CTYPE"):
        os.environ.pop(name, None)
    if (set(os.environ) != {"HOME", "PATH"} or not Path(os.environ["HOME"]).is_absolute()
            or os.environ["PATH"] != "/usr/bin:/bin:/usr/sbin:/sbin"):
        raise ValueError("unexpected verifier environment")
    if not 1 <= len(bindings) <= 14:
        raise ValueError("verifier closure size")
    sources = {}
    total = 0
    for name, digest in bindings:
        if not re.fullmatch(r"f020_[a-z0-9_]+", name) or name in sources:
            raise ValueError("verifier module name")
        p = root / (name + ".py")
        if p.resolve(strict=True) != p or not p.is_file() or p.stat().st_size > 524288:
            raise ValueError("verifier module path/size")
        with p.open("rb") as f:
            raw = f.read(524289)
        total += len(raw)
        if total > 2 << 20 or len(raw) > 524288 or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("compiled verifier closure")
        sources[name] = (p, raw)
    for name, (p, raw) in sources.items():
        mod = types.ModuleType(name)
        mod.__file__ = str(p)
        sys.modules[name] = mod
        exec(compile(raw, str(p), "exec"), mod.__dict__)
    return mod


if __name__ == "__main__":
    if len(sys.argv)!=4 or any(len(s.encode())>8192 for s in sys.argv[1:]):
        raise ValueError("startup argument size")
    bindings = json.loads(sys.argv[1])
    verifier = verified_modules(Path.cwd() / "scripts/research", bindings)
    verifier.verify_child(Path(sys.argv[2]), json.loads(sys.argv[3]), dict(bindings))
