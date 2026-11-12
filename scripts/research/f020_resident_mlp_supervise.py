"""One future physical copied-resident campaign. No upload, build, dispatch, or retry."""

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import f020_resident_mlp_runtime as runtime
import f020_resident_mlp_check as check
from f020_resident_mlp_fixtures import (
    ROOT,
    MANIFEST,
    INPUT,
    prepare,
    require,
    sha,
    canonical,
)

BASE = "94af723930f6502e72b4c32c65375735b1be3900"
ORIGIN = "https://github.com/MahdiHedhli/PulsarMLX"
INSTALL = "7c2301eb59c037191cd296e3139a7ca4a93e61e27c5e8b05b1ae717888b16523"
FREEZE = "3066d1259eff69f174854f26656ef35980365063710709090939cba2adde668a"
PINS = {
    "mlx": "68cf2fddd8de5edd8ab3d926391772b2e2cedad8",
    "mlx-c": "0726ca922fc902c4c61ef9c27d94132be418e945",
}
CLAIM = "f020-m2b-copied-resident-v1.claim.json"
BUDGET = dict(
    children=4, child_seconds=300, campaign_seconds=900, grades=1, raw=0, retries=0
)


def path(v, existing=True):
    p = Path(v)
    require(
        p.is_absolute()
        and str(p) == str(v)
        and p.resolve(strict=existing) == p
        and p.parent.is_dir(),
        "canonical path",
    )
    return p


def raw(p, limit):
    p = path(p)
    require(p.is_file() and p.stat().st_size <= limit, "bounded regular file")
    with p.open("rb") as stream:
        b = stream.read(limit + 1)
    require(len(b) <= limit, "file grew")
    return b


def hashed(p):
    p = path(p)
    require(p.is_file(), "regular file")
    with p.open("rb") as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def exclusive(p, value):
    with path(p, False).open("xb") as f:
        f.write(canonical(value))
        f.flush()
        os.fsync(f.fileno())


def doc(p):
    return json.loads(raw(p, 1 << 20))


def cmd(*a):
    return subprocess.check_output(a, cwd=ROOT, timeout=45)


def git(*a):
    return cmd("/usr/bin/git", *a).decode().strip()


def equal(a, b, why):
    require(canonical(a) == canonical(b), why)


FULL_SCHEMA = "resident-mlp-physical-grant-v1"
DIGEST_SCHEMA = "resident-mlp-description-grant-v1"
DESCRIPTION_FORMAT = "resident-description-json-ascii-lf/1"
DESCRIPTION_LIMIT = 1 << 20


def strict_json(data):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, "duplicate JSON key")
            result[name] = value
        return result

    def finite(token):
        value = float(token)
        require(math.isfinite(value), "non-finite JSON value")
        return value

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=unique,
        parse_constant=finite,
        parse_float=finite,
    )


def compact_line(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def description_bytes(full):
    # JSON member names must already be strings; coercion could collapse distinct identities.
    def check_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                require(isinstance(key, str), "description JSON key")
                check_keys(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                check_keys(child)

    check_keys(full)
    data = compact_line(full)
    require(len(data) <= DESCRIPTION_LIMIT, "full description exceeds 1 MiB")
    return data


def exact_keys(value, expected, label):
    require(isinstance(value, dict) and value.keys() == set(expected.split()), label)


def hex_field(value, width):
    require(
        isinstance(value, str) and re.fullmatch("[0-9a-f]{%d}" % width, value),
        "invalid grant digest or Git identity",
    )


def validate_grant(grant):
    require(isinstance(grant, dict), "grant object")
    schema = grant.get("schema")
    if schema == FULL_SCHEMA:
        exact_keys(
            grant, "schema identity config_binding arms budget", "full grant fields"
        )
        require(isinstance(grant["identity"], dict), "full grant identity")
    elif schema == DIGEST_SCHEMA:
        exact_keys(
            grant,
            "schema description source binary_sha256 build_sha256 config_binding arms budget",
            "digest grant fields",
        )
        desc = grant["description"]
        exact_keys(desc, "schema format bytes sha256", "description fields")
        require(
            desc["schema"] == FULL_SCHEMA and desc["format"] == DESCRIPTION_FORMAT,
            "description schema/format",
        )
        require(
            type(desc["bytes"]) is int and 0 < desc["bytes"] <= DESCRIPTION_LIMIT,
            "description length",
        )
        exact_keys(grant["source"], "commit tree", "source fields")
        for n in ("commit", "tree"):
            hex_field(grant["source"][n], 40)
        for digest in (desc["sha256"], grant["binary_sha256"], grant["build_sha256"]):
            hex_field(digest, 64)
    else:
        raise ValueError("unsupported resident grant schema")
    hex_field(grant["config_binding"], 64)
    equal(grant["arms"], check.ARMS, "resident arm order")
    equal(grant["budget"], BUDGET, "resident campaign budget")


def parse_grant_block(markdown):
    # Count all grant openers first: a malformed second block must not disappear.
    openers = list(
        re.finditer(
            rb"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*resident-mlp-grant\b[^\n]*$", markdown
        )
    )
    require(
        len(openers) == 1 and openers[0][0] == b"```resident-mlp-grant",
        "one exact resident grant fence",
    )
    enclosing = None
    for line in markdown[: openers[0].start()].splitlines():
        fence = re.match(rb"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            continue
        mark, tail = fence.groups()
        if enclosing is None:
            enclosing = mark
        elif mark.startswith(enclosing) and not tail.strip():
            enclosing = None
    require(enclosing is None, "grant inside another fence")
    payload = re.match(rb"\n([^\n]+)\n```(?:\n|\Z)", markdown[openers[0].end() :])
    require(payload is not None, "malformed resident grant fence")
    grant = strict_json(payload[1])
    validate_grant(grant)
    return grant


def description_binding(full):
    validate_grant(full)
    data = description_bytes(full)
    identity = full["identity"]
    envelope = dict(
        schema=DIGEST_SCHEMA,
        description=dict(
            schema=full["schema"],
            format=DESCRIPTION_FORMAT,
            bytes=len(data),
            sha256=sha(data),
        ),
        source=dict(commit=identity["commit"], tree=identity["tree"]),
        binary_sha256=identity["binary_sha256"],
        build_sha256=identity["build_sha256"],
        config_binding=full["config_binding"],
        arms=full["arms"],
        budget=full["budget"],
    )
    validate_grant(envelope)
    return data, envelope


def match_grant(grant, full):
    # The authenticated parser has already validated the committed schema.
    if grant["schema"] == DIGEST_SCHEMA:
        _, expected = description_binding(full)
        equal(grant, expected, "operator description and scope")
    elif grant["schema"] == FULL_SCHEMA:
        require(
            description_bytes(grant) == description_bytes(full),
            "operator population and current bindings",
        )
    else:
        raise ValueError("unsupported resident grant schema")


def emit_line(data):
    require(sys.stdout.buffer.write(data) == len(data), "incomplete standard output")
    sys.stdout.buffer.flush()


def operator(spec):
    commit, name, digest = spec["commit"], spec["path"], spec["sha256"]
    require(
        re.fullmatch("[0-9a-f]{40}", commit)
        and re.fullmatch(
            r"Prompts/[^/]+/Mac-Studio-M1-Ultra/[a-zA-Z0-9_-]+__prompt\.md", name
        )
        and re.fullmatch("[0-9a-f]{64}", digest),
        "future physical prompt",
    )

    def fetch(n):
        gh = shutil.which("gh", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin")
        require(gh, "existing authenticated repository client")
        result = json.loads(
            cmd(
                gh,
                "api",
                "repos/MahdiHedhli/PulsarMLX-Prompts/contents/" + n + "?ref=" + commit,
            )
        )
        require(result["path"] == n and result["size"] <= 1 << 20, "prompt path/size")
        b = base64.b64decode(result["content"])
        require(len(b) == result["size"], "complete response")
        return b

    b = fetch(name)
    equal(sha(b), digest, "operator identity")
    equal(
        fetch(name + ".sha256").decode().split(),
        [digest, Path(name).name],
        "operator checksum",
    )
    return parse_grant_block(b)


def source():
    equal(
        git("remote", "get-url", "origin").removesuffix(".git"), ORIGIN, "source origin"
    )
    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    equal(git("merge-base", BASE, head), BASE, "M2a ancestry")
    require(
        head != BASE and not git("status", "--porcelain=v1", "--untracked-files=all"),
        "clean candidate",
    )
    inventory = cmd("/usr/bin/git", "ls-tree", "-rz", "--full-tree", head)
    rows = [line.split(b"\t", 1) for line in inventory.split(b"\0") if line]
    for meta, name in rows:
        mode, kind, blob = meta.split()
        require(kind == b"blob", "source object type")
        f = ROOT / os.fsdecode(name)
        if mode == b"120000":
            require(f.is_symlink(), "source symlink")
            b = os.fsencode(os.readlink(f))
            actual = hashlib.sha1(
                b"blob " + str(len(b)).encode() + b"\0" + b
            ).hexdigest()
        else:
            require(
                f.is_file()
                and not f.is_symlink()
                and (f.stat().st_mode & 0o111 != 0) == (mode == b"100755"),
                "source mode",
            )
            h = hashlib.sha1(b"blob " + str(f.stat().st_size).encode() + b"\0")
            with f.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    h.update(block)
            actual = h.hexdigest()
        equal(actual, blob.decode(), "working file bytes")
    return dict(
        commit=head, tree=tree, inventory_sha256=sha(inventory), file_count=len(rows)
    )


def links(binary):
    listing = runtime.inspect_image("-L", binary).splitlines()
    require(listing and listing[0] == str(binary) + ":", "binary linkage image")
    return listing[1:]


def child_environment(prefix):
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": os.environ["HOME"],
        "MLX_C_PREFIX": str(prefix),
        "DYLD_LIBRARY_PATH": str(prefix / "lib"),
        "MLX_ENABLE_TF32": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def runtime_source_bindings():
    return {
        name: hashed(ROOT / name)
        for name in (
            "scripts/research/f020_resident_mlp_runtime.py",
            "scripts/research/f020_resident_mlp_supervise.py",
            "crates/mlx-expert-mlp/src/resident_native.rs",
            "crates/mlx-expert-mlp/src/resident_verifier.rs",
        )
    }


def installed(config):
    receipt = path(config["installation"])
    freeze = path(config["freeze"])
    equal(hashed(receipt), INSTALL, "original installation")
    equal(hashed(freeze), FREEZE, "original freeze")
    diagnostic = path(config["diagnostic_receipt"])
    equal(
        hashed(diagnostic),
        "d867b245b6be75e62cf352ba5c73cf376a2b2b3fa9b66943e8beb062c3d8f920",
        "original diagnostic receipt",
    )
    d = doc(diagnostic)
    equal(
        [d["native_prefix"], d["native_build_receipt"]],
        [config["prefix"], str(receipt)],
        "original prefix and receipt custody",
    )
    f = doc(freeze)
    equal(f["native_build_receipt"], str(receipt), "original installation location")
    r = doc(receipt)
    pins = r.get(
        "source_pins", {"mlx": r.get("mlx_commit"), "mlx-c": r.get("mlx_c_commit")}
    )
    equal(pins, PINS, "source pins")
    prefix = path(config["prefix"])
    libs = prefix / "lib"
    names = {
        "libmlx": "libmlx.dylib",
        "libmlxc": "libmlxc.dylib",
        "metallib": "mlx.metallib",
    }
    actual = {k: hashed((libs / v).resolve(strict=True)) for k, v in names.items()}
    equal(
        {names[k]: v for k, v in actual.items()},
        f["native_libraries"],
        "original runtime data",
    )
    static = runtime.retained_runtime(
        prefix, child_environment(prefix), runtime_source_bindings()
    )
    equal(
        r["extra_runtime_library_sha256"],
        runtime.RUNTIME_SHA256,
        "original runtime pin",
    )
    for role in ("libmlx", "libmlxc"):
        equal(
            static["files"][names[role]]["sha256"],
            actual[role],
            "inspected MLX file identity",
        )
    return {
        **actual,
        "mlx_commit": PINS["mlx"],
        "mlx_c_commit": PINS["mlx-c"],
        "install_sha256": INSTALL,
        "static_runtime_sha256": runtime.RUNTIME_SHA256,
        "static_inspection": static,
    }


VERIFIER_MODULES = (
    "f020_expert_mlp_r1_v1",
    "f020_expert_mlp_qualify_v1",
    "f020_resident_mlp_fixtures",
    "f020_resident_mlp_runtime",
    "f020_resident_mlp_check",
    "f020_resident_mlp_supervise",
)


def verifier_modules():
    return {
        n: hashed(ROOT / "scripts/research" / (n + ".py")) for n in VERIFIER_MODULES
    }


def physical_identity(config):
    runtime.clean_inspector()
    require(
        sys.platform == "darwin" and not os.environ.get("GITHUB_ACTIONS"),
        "physical target",
    )
    host = {
        k: cmd("/usr/sbin/sysctl", "-n", v).decode().strip()
        for k, v in (
            ("model", "hw.model"),
            ("chip", "machdep.cpu.brand_string"),
            ("memory", "hw.memsize"),
            ("page", "hw.pagesize"),
        )
    }
    host.update(
        os=cmd("/usr/bin/sw_vers", "-productVersion").decode().strip(),
        build=cmd("/usr/bin/sw_vers", "-buildVersion").decode().strip(),
    )
    equal(
        host,
        dict(
            model="Mac13,2",
            chip="Apple M1 Ultra",
            memory="137438953472",
            page="16384",
            os="26.0",
            build="25A354",
        ),
        "physical host facts",
    )
    require(config["repo"] == str(ROOT), "working source")
    src = source()
    binary = path(config["binary"])
    build = doc(path(config["build"]))
    require(
        binary.name == "qualify-resident-mlp"
        and binary.parent.name == "release"
        and os.access(binary, os.X_OK),
        "resident child build",
    )
    msg = json.loads(raw(path(build["artifact"]), 1 << 20))
    require(
        msg["target"]["kind"] == ["bin"]
        and msg["profile"]["opt_level"] == "3"
        and "mlx-expert-mlp" in msg["package_id"],
        "release resident package",
    )
    equal(build["artifact_sha256"], hashed(path(build["artifact"])), "build artifact")
    equal(
        [
            msg["reason"],
            msg["target"]["name"],
            msg["target"]["src_path"],
            msg["executable"],
            msg["profile"]["test"],
        ],
        [
            "compiler-artifact",
            binary.name,
            str(ROOT / "crates/mlx-expert-mlp/src/bin/qualify-resident-mlp.rs"),
            str(binary),
            False,
        ],
        "actual cargo child",
    )
    require(
        set(msg["features"]) == {"resident-native"}
        or set(msg["features"]) == {"default", "resident-native"},
        "physical build feature",
    )
    equal(
        [build["commit"], build["tree"], build["binary_sha256"], build["prefix"]],
        [src["commit"], src["tree"], hashed(binary), config["prefix"]],
        "build/source identity",
    )
    modules = verifier_modules()
    equal(build["verifier_modules"], modules, "compiled verifier helper set")
    stamp = build["accounting_abi_stamp"]
    accounting = check.accounting_proof(ROOT, stamp)
    require(
        stamp.encode("ascii") in raw(binary, 128 << 20),
        "compiled accounting ABI witness",
    )
    actual = links(binary)
    equal(actual, build["linkage"], "current child linkage")
    require(
        all(
            any(n in line for line in actual) for n in ("libmlx.dylib", "libmlxc.dylib")
        ),
        "native child linkage",
    )
    prepare()
    identity = {
        **src,
        "host": host,
        "verifier_modules": modules,
        "accounting": accounting,
        "native": installed(config),
        "binary_sha256": hashed(binary),
        "build_sha256": hashed(path(config["build"])),
        "fixture_sha256": check.VIEW_SHA,
        "original_manifest": MANIFEST,
        "input_sha256": INPUT,
        "checker_sha256": hashed(Path(check.__file__).resolve()),
        "supervisor_sha256": hashed(Path(__file__).resolve()),
    }
    return identity


def grant_for(config, identity):
    return dict(
        schema="resident-mlp-physical-grant-v1",
        identity=identity,
        config_binding=sha(
            canonical({k: v for k, v in config.items() if k != "operator"})
        ),
        arms=check.ARMS,
        budget=BUDGET,
    )


def describe(cfg):
    config = doc(cfg)
    full = grant_for(config, physical_identity(config))
    emit_line(description_bytes(full))


def preparation_paths(cfg, config, destination):
    exact_keys(
        config,
        "repo prefix binary build installation freeze diagnostic_receipt output",
        "preparation configuration paths (operator must be absent)",
    )
    equal(config["repo"], str(ROOT), "working source")
    output, claim = locations(config)
    require(
        not os.path.lexists(claim) and not os.path.lexists(output),
        "existing physical claim or original output",
    )
    dest = path(destination, False)
    require(not os.path.lexists(dest), "description destination already exists")
    require(
        dest != cfg and dest != path(config["build"]),
        "description overlaps config/build",
    )
    for protected in (
        ROOT,
        path(config["prefix"]),
        path(config["installation"]).parent,
        path(config["freeze"]).parent,
        path(config["diagnostic_receipt"]).parent,
        path(config["binary"]).parent,
        output,
    ):
        require(
            not dest.is_relative_to(protected) and not protected.is_relative_to(dest),
            "description destination overlaps protected location",
        )
    return dest, output, claim


def write_private_description(parent_fd, name, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            os.fchmod(stream.fileno(), 0o600)
            require(
                stream.write(data) == len(data), "incomplete private description write"
            )
            stream.flush()
            os.fsync(stream.fileno())
            saved = os.fstat(stream.fileno())
            require(
                stat.S_ISREG(saved.st_mode)
                and stat.S_IMODE(saved.st_mode) == 0o600
                and saved.st_size == len(data),
                "private description file",
            )
    finally:
        os.close(fd)
    return saved


def describe_binding(cfg, destination):
    config_data = raw(cfg, DESCRIPTION_LIMIT)
    config = strict_json(config_data)
    dest, output, claim = preparation_paths(cfg, config, destination)
    # Pin the checked parent across the potentially lengthy identity observation.
    parent_fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(
            dest.parent.resolve(strict=True) == dest.parent
            and os.path.samestat(os.fstat(parent_fd), dest.parent.lstat()),
            "description parent changed",
        )
        full = grant_for(config, physical_identity(config))
        data, envelope = description_binding(full)
        public = compact_line(envelope)
        require(
            raw(cfg, DESCRIPTION_LIMIT) == config_data,
            "preparation configuration changed",
        )
        preparation_paths(cfg, config, destination)
        require(
            os.path.samestat(os.fstat(parent_fd), dest.parent.lstat()),
            "description parent changed",
        )
        saved = write_private_description(parent_fd, dest.name, data)
        observed = dest.lstat()
        require(
            dest.resolve(strict=True) == dest
            and os.path.samestat(saved, observed)
            and observed.st_nlink == 1
            and saved.st_size == observed.st_size
            and saved.st_ctime_ns == observed.st_ctime_ns,
            "private description location changed",
        )
        require(
            not os.path.lexists(claim) and not os.path.lexists(output),
            "preparation custody changed",
        )
    finally:
        os.close(parent_fd)
    emit_line(public)


def admit(config):
    runtime.clean_inspector()
    grant = operator(config["operator"])
    identity = physical_identity(config)
    match_grant(grant, grant_for(config, identity))
    return identity


def locations(config):
    output = path(config["output"], False)
    receipt = path(config["installation"])
    for protected in (
        ROOT,
        path(config["prefix"]),
        receipt.parent,
        path(config["freeze"]).parent,
        path(config["diagnostic_receipt"]).parent,
        path(config["build"]).parent,
        path(config["binary"]).parent,
    ):
        require(
            not output.is_relative_to(protected)
            and not protected.is_relative_to(output),
            "distinct original output",
        )
    return output, receipt.parent / CLAIM


def authorization(cfg, identity):
    return dict(
        schema="resident-mlp-start-v1",
        identity=identity,
        config=str(cfg),
        config_sha256=hashed(cfg),
        pid=os.getpid(),
        budget=BUDGET,
    )


def wait_child(command, env, arm, deadline, limit):
    started = time.monotonic()
    require(started < deadline, "campaign deadline")
    with (
        (arm / "stdout.log").open("xb") as stdout,
        (arm / "stderr.log").open("xb") as stderr,
    ):
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            env=env,
            start_new_session=True,
        )
        timed_out = False
        try:
            exclusive(arm / "started.json", dict(pid=child.pid))
            child.wait(timeout=max(0, min(limit, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            rc = child.wait()
            exclusive(
                arm / "completed.json",
                dict(pid=child.pid, exit=rc, reaped=True, timeout=timed_out),
            )
    require(
        not timed_out and rc == 0 and time.monotonic() <= deadline,
        "child failed or timed out; retirement unverified",
    )


def sequence(cfg, config, identity, output, claim, launch, grade):
    require(not output.exists(), "original output already exists")
    claim_record = authorization(cfg, identity)
    claim_hash = sha(canonical(claim_record))
    intents = [
        dict(
            schema="resident-mlp-intent-v1",
            supervisor_pid=os.getpid(),
            repo=str(ROOT),
            config=str(cfg),
            claim=str(claim),
            claim_sha256=claim_hash,
            identity=identity,
            profile=profile,
            arm=arm,
        )
        for profile, arm in check.ARMS
    ]
    require(
        all(len(canonical(record)) <= 65536 for record in intents),
        "native child intent size",
    )
    exclusive(claim, claim_record)
    output.mkdir(mode=0o700)
    deadline = time.monotonic() + 900
    for i, record in enumerate(intents):
        directory = output / f"{i}-{record['profile']}-{record['arm']}"
        directory.mkdir(mode=0o700)
        intent = directory / "intent.json"
        equal(hashed(claim), claim_hash, "original stable claim")
        exclusive(intent, record)
        launch(intent, directory, deadline)
    require(time.monotonic() <= deadline, "campaign deadline")
    exclusive(output / "grading-intent.json", dict(claim_sha256=hashed(claim), count=1))

    def expired(_signal, _frame):
        raise TimeoutError("overall campaign deadline during final admission")

    previous = signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, max(0.000001, deadline - time.monotonic()))
        result = grade()
        require(
            time.monotonic() <= deadline, "overall deadline expired during admission"
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    exclusive(output / "result.json", result)


def evidence_manifest(output):
    names = ["grading-intent.json"]
    for i, (p, a) in enumerate(check.ARMS):
        prefix = f"{i}-{p}-{a}/"
        names.extend(
            prefix + n
            for n in (
                "intent.json",
                "started.json",
                "completed.json",
                "out/report.json",
            )
        )
        names.extend(prefix + f"out/occ-{j:02}.json" for j in range(9))
    return {name: hashed(output / name) for name in names}


def inspect(cfg):
    config = doc(cfg)
    identity = admit(config)
    output, claim = locations(config)
    result = doc(output / "result.json")
    equal(
        result,
        dict(
            status="accepted",
            claim_sha256=hashed(claim),
            children=4,
            occurrences=36,
            identity=identity,
            evidence=evidence_manifest(output),
        ),
        "stored once-graded result",
    )
    c = doc(claim)
    equal(
        [c["config_sha256"], c["identity"], c["budget"]],
        [hashed(cfg), identity, BUDGET],
        "original completed claim",
    )
    print("Verified once-graded physical evidence")


def launch(cfg):
    config = doc(cfg)
    output, claim = locations(config)
    require(
        not claim.exists() and not output.exists(),
        "existing physical claim or original output",
    )
    identity = admit(config)
    env = child_environment(path(config["prefix"]))

    # Use the existing repository login. Never forward a credential in the intent or child environment.
    def run(intent, armdir, deadline):
        equal(admit(config), identity, "before-child source/build/install admission")
        wait_child(
            [config["binary"], "--intent", str(intent)], env, armdir, deadline, 300
        )

    def grade():
        equal(admit(config), identity, "final source/build/install admission")
        equal(doc(claim), authorization(cfg, identity), "final claim")
        refs = check.Reference()
        pop = {}
        for i, (p, a) in enumerate(check.ARMS):
            directory = output / f"{i}-{p}-{a}"
            start = doc(directory / "started.json")
            end = doc(directory / "completed.json")
            equal(
                end,
                dict(pid=start["pid"], exit=0, reaped=True, timeout=False),
                "actual child completion",
            )
            pop[p, a] = check.admit_arm(
                directory / "out",
                p,
                a,
                identity,
                refs,
                hashed(directory / "intent.json"),
            )
        check.compare(pop)
        equal(admit(config), identity, "post-grading custody")
        return dict(
            status="accepted",
            claim_sha256=hashed(claim),
            children=4,
            occurrences=36,
            identity=identity,
            evidence=evidence_manifest(output),
        )

    try:
        sequence(cfg, config, identity, output, claim, run, grade)
    except Exception as e:
        if (
            claim.is_file()
            and output.is_dir()
            and doc(claim) == authorization(cfg, identity)
        ):
            exclusive(
                output / "failure.json",
                dict(
                    status="failed",
                    reason=str(e),
                    retirement="see successful child receipts; otherwise unverified",
                ),
            )
        raise


def verify_child(intent):
    v = doc(intent)
    cfg = path(v["config"])
    config = doc(cfg)
    output, claim = locations(config)
    p, a = v["profile"], v["arm"]
    i = check.ARMS.index((p, a))
    directory = output / f"{i}-{p}-{a}"
    require(intent == directory / "intent.json", "intent location")
    require(
        not (directory / "out").exists()
        and not (directory / "completed.json").exists(),
        "one child start",
    )
    require(
        str(claim) == v["claim"] and hashed(claim) == v["claim_sha256"],
        "original claim",
    )
    c = doc(claim)
    equal(
        [c["pid"], c["config"], c["config_sha256"], c["identity"]],
        [v["supervisor_pid"], str(cfg), hashed(cfg), v["identity"]],
        "live claim",
    )
    for _ in range(50):
        if (directory / "started.json").exists():
            break
        time.sleep(0.02)
    for ordinal, (profile, arm) in enumerate(check.ARMS[:i]):
        previous = output / f"{ordinal}-{profile}-{arm}"
        completed = doc(previous / "completed.json")
        equal(
            completed,
            dict(
                pid=doc(previous / "started.json")["pid"],
                exit=0,
                reaped=True,
                timeout=False,
            ),
            "prior child completed",
        )
    equal(admit(config), v["identity"], "fresh child authority")
    require(
        os.getppid() == doc(directory / "started.json")["pid"],
        "verifier was started by the admitted child",
    )
    require(
        hashed(path(config["binary"])) == v["identity"]["binary_sha256"]
        and git("rev-parse", "HEAD") == v["identity"]["commit"]
        and git("rev-parse", "HEAD^{tree}") == v["identity"]["tree"],
        "child current build",
    )
    equal(installed(config), v["identity"]["native"], "child installation")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("describe", "describe-binding", "run", "inspect", "verify-child"),
    )
    parser.add_argument("file")
    parser.add_argument("description_output", nargs="?")
    args = parser.parse_args(argv)
    if args.action == "describe-binding":
        if args.description_output is None:
            parser.error("describe-binding requires CONFIG DESCRIPTION_OUTPUT")
        describe_binding(path(args.file), args.description_output)
    else:
        if args.description_output is not None:
            parser.error("unexpected description output")
        {
            "describe": describe,
            "run": launch,
            "inspect": inspect,
            "verify-child": verify_child,
        }[args.action](path(args.file))


if __name__ == "__main__":
    main()
