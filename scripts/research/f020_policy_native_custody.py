"""Versioned source seal, Studio-only build receipt and read-only live identity."""
import argparse
import ast
import hashlib
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import f020_staged_weighted_supervise as prior
from f020_weighted_native_reference import canonical, require, sha, strict

ROOT = Path(__file__).resolve().parents[2]
BASE = "2ef37bc90c557d2767ace80dcba2c9491686264a"
BASE_TREE = "28adbed1e2e3d2af0a11a988314744212847192e"
PINS = "crates/mlx-expert-mlp/src/staged_policy_native_pins.rs"
REFERENCE = prior.REFERENCE
SEAL_PREFIX = "staged-policy-native-build-v1."
BIN = "qualify-staged-policy-mlp"
FEATURE = "staged-policy-native"
RUSTC = "rustc 1.95.0 (59807616e 2026-04-14)"
STUDIO014_CLAIM = "61659d90c4731accbda8a566d18e4946fa478793843bb106bb1fc5e53408ba48"
STUDIO014_RESULT = "35eea49b6ede105bcd4e92d1dd6399c2da2d6a9756b7fb957f08dbeb510d709d"
CONFIG = set("repo prefix binary artifact build installation freeze diagnostic_receipt output private_description cargo_log commit tree input_sha256 run".split())
FILE_LIMIT = 32 << 20
SOURCE_LIMIT = 256 << 20
LOG_LIMIT = 8 << 20


def _git(root, *args):
    return subprocess.check_output(["/usr/bin/git", *args], cwd=root, timeout=45)


def _modules(root):
    """Derive topological order from actual project imports; only stdlib is loaded by the bootstrap."""
    seen = {}
    visiting = set()
    total = 0
    def visit(name):
        nonlocal total
        if name in seen:
            return
        require(re.fullmatch(r"f020_[a-z0-9_]+", name) and name not in visiting, "cyclic or invalid project module")
        visiting.add(name)
        p = root / "scripts/research" / (name + ".py")
        raw = prior.old.raw(p, 524288)
        total += len(raw)
        require(total <= 2 << 20 and len(seen) + len(visiting) <= 32, "bounded verifier module closure")
        dependencies = set()
        for node in ast.walk(ast.parse(raw, filename=str(p))):
            if isinstance(node, ast.ImportFrom):
                require(not node.level, "unexpected relative project import")
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            dependencies.update(n for n in names if n.startswith("f020_"))
        for dependency in sorted(dependencies):
            visit(dependency)
        visiting.remove(name)
        seen[name] = sha(raw)
    visit("f020_policy_native_bootstrap")
    visit("f020_policy_native_supervise")
    require("f020_policy_native_custody" in seen and "f020_policy_native_check" in seen, "supervisor input closure")
    return list(seen.items())


def _render(digest, modules):
    lines = ["//! Generated from the complete qualified input closure.",
             'pub const SEAL: &str = "' + SEAL_PREFIX + digest + '";',
             'pub const REFERENCE: &str = "' + REFERENCE + '";',
             'pub const MODULES: &[(&str, &str)] = &[']
    lines.extend('    ("' + name + '", "' + value + '"),' for name, value in modules)
    return ("\n".join(lines + ["];"]) + "\n").encode("ascii")


def _closure(root, check_pins):
    root = Path(root).resolve(strict=True)
    modules = _modules(root)
    # Generation also accounts for new, not-yet-staged source. Physical admission separately
    # proves the complete live tree matches HEAD and refuses untracked work.
    names = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")
    require(names.pop() == b"" and 0 < len(names) <= 8192 and len(set(names)) == len(names), "source inventory")
    paths = set(os.fsdecode(n) for n in names)
    paths.add(PINS)
    h = hashlib.sha256(b"pulsarmlx.policy.qualified-inputs/1\0")
    total = 0
    for name in sorted(paths):
        p = root / name
        require(len(name.encode()) <= 2048 and not Path(name).is_absolute() and ".." not in Path(name).parts,
                "source entry name")
        if name == PINS:
            # The exact surrounding Rust, reference and ordered Python hashes all participate.
            # Only the 64 hex characters printed into the SEAL constant are neutralized.
            raw = _render("0" * 64, modules)
            if p.exists() or p.is_symlink():
                require(p.resolve(strict=True) == p and stat.S_ISREG(p.lstat().st_mode)
                        and not p.lstat().st_mode & 0o111, "generated pin mode")
            mode, size, digest = "100644", len(raw), sha(raw)
        else:
            require(p.parent.resolve(strict=True) == p.parent, "source parent alias")
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                raw = os.fsencode(os.readlink(p))
                mode, size, digest = "120000", len(raw), sha(raw)
            else:
                require(stat.S_ISREG(st.st_mode) and st.st_size <= FILE_LIMIT, "bounded source blob")
                mode = "100755" if st.st_mode & 0o111 else "100644"
                size, digest = st.st_size, prior.old.runtime.file_hash(p)
        total += size
        require(total <= SOURCE_LIMIT, "qualified source population")
        h.update(canonical([name, mode, size, digest]))
    value = h.hexdigest()
    if check_pins:
        require(prior.old.raw(root / PINS, 16384) == _render(value, modules), "stale generated policy seal")
    return value, modules


def closure(root):
    return _closure(root, True)


def make_pins(root):
    return _render(*_closure(root, False))


def _same(left, right, message):
    require(canonical(left) == canonical(right), message)


def _path(value, exists=True):
    require(type(value) is str and 0 < len(value.encode()) <= 1024, "bounded custody path")
    p = Path(value)
    require(p.is_absolute() and str(p) == value and p.resolve(strict=exists) == p, "canonical custody path")
    return p


def _paths(config):
    require(set(config) == CONFIG, "physical configuration schema")
    for name, count in (("commit", 40), ("tree", 40), ("input_sha256", 64), ("run", 64)):
        require(type(config[name]) is str and re.fullmatch("[0-9a-f]{%d}" % count, config[name]), "configuration identity")
    existing = {"repo", "prefix", "installation", "freeze", "diagnostic_receipt"}
    paths = {k: _path(config[k], k in existing) for k in CONFIG - {"commit", "tree", "input_sha256", "run"}}
    require(paths["repo"] == ROOT and len(set(paths.values())) == len(paths), "distinct physical roles")
    binary = paths["binary"]
    require(binary.name == BIN and binary.parent.name == "release", "physical release target")
    target = binary.parent.parent
    outputs = [paths[k] for k in ("cargo_log", "build", "artifact", "output", "private_description")]
    outputs.append(paths["cargo_log"].with_name(paths["cargo_log"].name + ".stderr"))
    require(len(set(outputs)) == len(outputs), "distinct build transcripts and receipts")
    protected = [ROOT, paths["prefix"], paths["installation"].parent, paths["freeze"].parent,
                 paths["diagnostic_receipt"].parent, target]
    for p in outputs:
        require(p.parent.is_dir() and all(not p.is_relative_to(q) and not q.is_relative_to(p)
                for q in protected + [v for v in outputs if v != p]), "overlapping build/campaign custody")
    require(target.parent.is_dir() and all(not target.is_relative_to(q) and not q.is_relative_to(target)
            for q in protected[:-1]), "separate fresh target")
    return paths


def _host():
    host = prior.host_facts()
    actual = os.sysconf("SC_PAGE_SIZE")
    require(actual in (4096, 16384) and host["page"] == str(actual), "actual Studio page size")
    for field in ("model", "chip", "memory", "arch", "system"):
        require(host[field] == prior.HOST[field], "physical Studio " + field)
    require(all(type(host[field]) is str and 0 < len(host[field]) <= 128
                and host[field].isprintable() for field in ("os", "build")), "actual Studio OS and build")
    return host


def _history(config):
    history = prior.predecessor(config)
    claim = _path(config["installation"]).parent / prior.CLAIM
    claim_raw = prior.old.raw(claim, 1 << 20)
    require(sha(claim_raw) == STUDIO014_CLAIM, "spent original Studio014 claim")
    original = strict(claim_raw)
    cfg = prior.old.raw(_path(original["config"]), 1 << 20)
    require(sha(cfg) == original["config_sha256"], "Studio014 configuration custody")
    old_config = strict(cfg)
    require(old_config["installation"] == config["installation"], "Studio014 installation")
    result = _path(old_config["output"]) / "result.json"
    result_raw = prior.old.raw(result, 1 << 20)
    require(sha(result_raw) == STUDIO014_RESULT and strict(result_raw)["claim_sha256"] == STUDIO014_CLAIM,
            "accepted original Studio014 result")
    history["staged"] = dict(claim=str(claim), claim_sha256=STUDIO014_CLAIM,
                             result=str(result), result_sha256=STUDIO014_RESULT)
    return history


def _headers(prefix):
    # Both qualification translation units include mlx/c/mlx.h from this installation.
    # Cover the whole C header directory so conditional/transitive includes participate.
    directory = (prefix / "include/mlx/c").resolve(strict=True)
    require(directory.is_dir() and (directory / "mlx.h").is_file(), "installed MLX C headers")
    files = {}
    total = 0
    for base, dirs, names in os.walk(directory):
        require(all(not (Path(base) / d).is_symlink() for d in dirs), "unbound header directory alias")
        for n in names:
            p = Path(base) / n
            q = p.resolve(strict=True)
            st = q.stat()
            require(stat.S_ISREG(st.st_mode) and st.st_size <= FILE_LIMIT, "bounded installed header")
            total += st.st_size
            require(len(files) < 2048 and total <= 64 << 20, "installed header population")
            files[str(p.relative_to(directory))] = [str(q), st.st_size, prior.old.runtime.file_hash(q)]
    return dict(directory=str(directory), files=len(files), bytes=total, sha256=sha(canonical(files)))


def _cargo_configs():
    # CARGO_HOME is not forwarded. Cargo also discovers configuration up to the filesystem root.
    dirs = {p / ".cargo" for p in (ROOT, *ROOT.parents, Path.home())}
    found = {}
    for d in sorted(dirs):
        for name in ("config", "config.toml"):
            p = d / name
            if os.path.lexists(p):
                real = p.resolve(strict=True)
                found[str(p)] = [str(real), sha(prior.old.raw(real, 1 << 20))]
    return found


def _admission(config, paths, host):
    src = prior.old.source()
    require(_git(ROOT, "merge-base", BASE, "HEAD").decode().strip() == BASE
            and _git(ROOT, "rev-parse", BASE + "^{tree}").decode().strip() == BASE_TREE
            and src["commit"] != BASE, "Rust026 base identity")
    _same([src["commit"], src["tree"]], [config["commit"], config["tree"]], "reviewed source")
    digest, modules = closure(ROOT)
    require(digest == config["input_sha256"], "qualified inputs")
    native = prior.installed(config)
    prior.old.check.accounting_proof(ROOT, prior.old.check.ABI_STAMP)
    require(sha(prior.ref.bounded(prior.ref.FILE, prior.ref.REFERENCE_LIMIT)) == REFERENCE, "weighted reference")
    return dict(**src, input_sha256=digest, run=config["run"], host=host, page_size=int(host["page"]),
                reference=REFERENCE, seal=SEAL_PREFIX + digest, verifier_modules=dict(modules),
                accounting_abi_stamp=prior.old.check.ABI_STAMP, prefix=str(paths["prefix"]),
                native=native, headers=_headers(paths["prefix"]), cargo_configs=_cargo_configs(),
                predecessor=_history(config), fixture_bindings=prior.fixture_identity(),
                version="0.31.2")


def _record(path, raw):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(fd)
    parent = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def _artifact(paths):
    raw = prior.old.raw(paths["cargo_log"], LOG_LIMIT)
    require(raw.endswith(b"\n"), "complete Cargo capture")
    selected = []
    finished = []
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        require(len(line) <= 1 << 20, "bounded Cargo record")
        row = strict(line)
        if row["reason"] == "build-finished":
            require(row["success"] is True, "Cargo build refused")
            finished.append(index)
        if row["reason"] == "compiler-artifact" and row["target"]["name"] == BIN:
            target = row["target"]
            package = row["package_id"].rsplit("#", 1)
            require(package[0] == "path+" + (ROOT / "crates/mlx-expert-mlp").as_uri()
                    and package[1] in ("0.1.0", "mlx-expert-mlp@0.1.0"), "Cargo package")
            _same([target["kind"], target["src_path"], row["executable"], row["profile"]["test"],
                   row["profile"]["opt_level"], row["fresh"], sorted(row["features"])],
                  [["bin"], str(ROOT / ("crates/mlx-expert-mlp/src/bin/" + BIN + ".rs")),
                   str(paths["binary"]), False, "3", False, [FEATURE]], "original physical compiler artifact")
            selected.append(line)
    require(finished == [len(lines)-1] and len(selected) == 1, "successful unique Cargo artifact")
    return selected[0], sha(raw)


def _toolchain():
    rustup = shutil.which("rustup", path=str(Path.home() / ".cargo/bin") + ":/opt/homebrew/bin:/usr/local/bin")
    require(rustup is not None, "installed Rust toolchain manager")
    env = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    tools = {}
    for name in ("cargo", "rustc"):
        path = Path(subprocess.check_output([rustup, "which", "--toolchain", "1.95.0", name],
                    env=env, timeout=30).decode().strip()).resolve(strict=True)
        version = subprocess.check_output([path, "-V"], env=env, timeout=30).decode().strip()
        require((name == "rustc" and version == RUSTC) or (name == "cargo" and version.startswith("cargo 1.95.0 ")),
                "approved installed compiler/toolchain")
        tools[name] = dict(path=str(path), sha256=prior.old.hashed(path), version=version)
    return tools


def _command(paths, tools):
    args = [tools["cargo"]["path"], "build", "--release", "--offline", "--locked", "--no-default-features",
            "-j", "2", "-p", "mlx-expert-mlp", "--features", FEATURE, "--bin", BIN, "--message-format=json"]
    env = dict(HOME=str(Path.home()), PATH=str(Path(tools["rustc"]["path"]).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin",
               RUSTC=tools["rustc"]["path"], MLX_PREFIX=str(paths["prefix"]), MLX_C_PREFIX=str(paths["prefix"]),
               PULSAR_REQUIRE_NATIVE_MLX="1", CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(paths["binary"].parent.parent))
    return args, env


def _built(paths, admission, tools):
    artifact_bytes, cargo_hash = _artifact(paths)
    binary = _path(str(paths["binary"]))
    require(binary.is_file() and os.access(binary, os.X_OK) and 0 < binary.stat().st_size <= 128 << 20, "bounded executable")
    require(prior.contains_marker(binary, admission["seal"]) and prior.contains_marker(binary, admission["accounting_abi_stamp"]),
            "compiled candidate/ABI markers")
    links = prior.links(binary)
    libraries = admission["native"]["static_inspection"]["files"]
    selected = []
    for import_entry in links:
        name, separator, _ = import_entry.strip().partition(" (compatibility")
        require(separator and ".." not in Path(name).parts, "original ordered binary import")
        leaf = Path(name).name
        if name.startswith(("/usr/lib/", "/System/Library/")):
            require(not os.path.lexists(paths["prefix"] / "lib" / leaf), "competing system import")
        else:
            require(leaf in ("libmlx.dylib", "libmlxc.dylib")
                    and name in ("@rpath/" + leaf, libraries[leaf]["lexical"], libraries[leaf]["canonical"]),
                    "pinned physical binary import")
            selected.append(leaf)
    require(sorted(selected) == ["libmlx.dylib", "libmlxc.dylib"], "selected pinned images")
    args, env = _command(paths, tools)
    return artifact_bytes, dict(schema="pulsarmlx.policy-native-build/1", commit=admission["commit"], tree=admission["tree"],
        run=admission["run"], input_sha256=admission["input_sha256"], seal=admission["seal"], reference=REFERENCE,
        prefix=admission["prefix"], installation_sha256=admission["native"]["install_sha256"],
        installed_assets_sha256=sha(canonical(admission["native"])),
        headers=admission["headers"], cargo_configs=admission["cargo_configs"], page_size=admission["page_size"],
        host=admission["host"], tools=tools, command=args, environment=env,
        artifact=str(paths["artifact"]), artifact_sha256=sha(artifact_bytes), cargo_log=str(paths["cargo_log"]),
        cargo_log_sha256=cargo_hash, binary=str(binary), binary_sha256=prior.old.hashed(binary),
        linkage=links, accounting_abi_stamp=admission["accounting_abi_stamp"])


def _run_build(paths, tools):
    target = paths["binary"].parent.parent
    target.mkdir(mode=0o700)
    args, env = _command(paths, tools)
    stderr = paths["cargo_log"].with_name(paths["cargo_log"].name + ".stderr")
    def logfile(path):
        return os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "wb")
    with logfile(paths["cargo_log"]) as out, logfile(stderr) as err, selectors.DefaultSelector() as poll:
        child = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        deadline = time.monotonic() + 1800
        try:
            for src, target_log in ((child.stdout, out), (child.stderr, err)):
                poll.register(src, selectors.EVENT_READ, target_log)
            while poll.get_map():
                left = deadline - time.monotonic()
                require(left > 0, "Studio build deadline")
                for key, _ in poll.select(left):
                    chunk = os.read(key.fd, 65536)
                    if chunk:
                        require(key.data.tell() + len(chunk) <= LOG_LIMIT, "build transcript cap")
                        key.data.write(chunk)
                    else:
                        poll.unregister(key.fileobj)
            child.wait(timeout=max(.001, deadline - time.monotonic()))
        finally:
            child.stdout.close()
            child.stderr.close()
            if child.poll() is None or not prior.group_gone(child.pid):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            until = time.monotonic() + 5
            child.wait(timeout=max(.001, until - time.monotonic()))
            while not prior.group_gone(child.pid) and time.monotonic() < until:
                time.sleep(.025)
            require(prior.group_gone(child.pid), "owned build group unresolved")
        require(child.returncode == 0 and time.monotonic() <= deadline and os.fstat(out.fileno()).st_size <= LOG_LIMIT
                and os.fstat(err.fileno()).st_size <= LOG_LIMIT, "bounded physical build failed")
        out.flush()
        err.flush()
        os.fsync(out.fileno())
        os.fsync(err.fileno())


def capture_build(config):
    """Studio build-only action. Never execute the selected artifact or create a launch claim."""
    host = _host()
    paths = _paths(config)
    before = _admission(config, paths, host)
    tools = _toolchain()
    target = paths["binary"].parent.parent
    stderr = paths["cargo_log"].with_name(paths["cargo_log"].name + ".stderr")
    require(not any(os.path.lexists(p) for p in (target, paths["artifact"], paths["build"], paths["cargo_log"], stderr,
            paths["output"], paths["private_description"])), "occupied Studio build destination")
    _run_build(paths, tools)
    _same(_admission(config, paths, _host()), before, "build source/installation drift")
    _same(_toolchain(), tools, "build toolchain drift")
    line, build = _built(paths, before, tools)
    _record(paths["artifact"], line)
    _record(paths["build"], canonical(build))
    return build


def identity(config):
    """Recompute and compare original build inputs, artifact and loaded-image expectations without loading MLX."""
    host = _host()
    paths = _paths(config)
    admission = _admission(config, paths, host)
    line, build = _built(paths, admission, _toolchain())
    require(prior.old.raw(paths["artifact"], 1 << 20) == line
            and prior.old.raw(paths["build"], 1 << 20) == canonical(build), "original fresh policy build custody")
    return dict(**admission, binary=build["binary"], binary_sha256=build["binary_sha256"],
                artifact=build["artifact"], artifact_sha256=build["artifact_sha256"],
                build=str(paths["build"]), build_sha256=sha(canonical(build)), linkage=build["linkage"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build-record",))
    parser.add_argument("config")
    args = parser.parse_args()
    value = capture_build(strict(prior.old.raw(_path(args.config), 1 << 20)))
    sys.stdout.buffer.write(canonical({"build_sha256": sha(canonical(value)), "binary_sha256": value["binary_sha256"]}))
