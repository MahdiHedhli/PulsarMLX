"""Prepare a sealed Studio description or supervise one separately issued synthetic campaign."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import signal
import stat
import time

import f020_policy_native_check as check
import f020_policy_native_custody as custody
import f020_staged_weighted_supervise as prior
from f020_weighted_native_check import equal
from f020_weighted_native_reference import Originals, canonical, require, sha

ROOT = Path(__file__).resolve().parents[2]
ARMS = tuple((profile, mode, policy) for profile in ("default", "mixed")
             for mode in ("Serial", "Overlap") for policy in ("BufferedRequested", "NoCacheRequested"))
BUDGET = dict(children=8, child_seconds=300, campaign_seconds=2400, grades=1, retries=0,
              arm_payload=2 << 20, arm_log=8 << 20, campaign_disk=192 << 20,
              controller_working_allowance=192 << 20, grade_one_arm_allowance=64 << 20)
CLAIM = "f020-m4c-staged-policy-native-v1.claim.json"
PATHS = "repo prefix binary artifact build installation freeze diagnostic_receipt output private_description cargo_log".split()
IDS = dict(commit=40, tree=40, input_sha256=64, run=64)


def doc(path, limit=1 << 20):
    return check.strict(prior.old.raw(path, limit), limit)


def keys(value, names, why):
    require(type(value) is dict and set(value) == set(names), why)


def hex_id(value, length):
    require(type(value) is str and re.fullmatch("[0-9a-f]{"+str(length)+"}", value), "hex identity")
    return value


def configuration(config):
    keys(config, PATHS + list(IDS), "configuration fields")
    for key, length in IDS.items():
        hex_id(config[key], length)
    paths = {}
    for key in PATHS:
        v = config[key]
        require(type(v) is str and 0 < len(v.encode()) <= 1024, "configuration path")
        paths[key] = prior.path(v, key not in ("private_description", "output"))
    require(len(set(paths.values())) == len(paths) and paths["repo"] == ROOT, "distinct original locations")
    claim = paths["installation"].parent / CLAIM
    for name in ("output", "private_description"):
        p = paths[name]
        for k, other in paths.items():
            if k == name:
                continue
            require(not p.is_relative_to(other) and not other.is_relative_to(p), "overlapping custody")
        for boundary in (paths["installation"].parent, paths["binary"].parent, paths["build"].parent):
            require(not p.is_relative_to(boundary) and not boundary.is_relative_to(p), "output overlaps protected custody")
    require(len(set(paths.values()) | {claim}) == len(paths) + 1, "claim overlap")
    return paths["output"], claim


def envelope(config, identity):
    require(identity["commit"] == config["commit"] and identity["tree"] == config["tree"]
            and identity["input_sha256"] == config["input_sha256"] and identity["run"] == config["run"],
            "description source, closure or run")
    require(identity["page_size"] in (4096, 16384) and
            str(identity["page_size"]) == identity["host"]["page"], "actual page eligibility")
    desc = dict(schema="staged-policy-private-description/1", configuration=config,
                identity=identity, arms=ARMS, budget=BUDGET)
    raw = canonical(desc)
    require(0 < len(raw) <= 1 << 20, "description bytes")
    public = dict(schema="staged-policy-studio-grant/1", description_sha256=sha(raw),
                  description_bytes=len(raw), source=config["commit"], tree=config["tree"],
                  input_sha256=config["input_sha256"], run=config["run"],
                  binary_sha256=identity["binary_sha256"], build_sha256=identity["build_sha256"],
                  page_size=identity["page_size"], arms=ARMS, budget=BUDGET)
    return raw, public


def prepare(cfg):
    config = doc(cfg)
    output, claim = configuration(config)
    dest = Path(config["private_description"])
    require(not any(os.path.lexists(p) for p in (dest, output, claim)), "preparation already occupied")
    identity = custody.identity(config)
    data, public = envelope(config, identity)
    equal(doc(cfg), config, "configuration drift during preparation")
    fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = prior.old.write_private_description(fd, dest.name, data)
        os.fsync(fd)
        require(os.path.samestat(st, dest.lstat()) and prior.old.raw(dest, 1 << 20) == data,
                "description readback")
    finally:
        os.close(fd)
    return public


def operator(spec):
    keys(spec, ("commit", "path", "sha256"), "immutable Studio grant pointer")
    hex_id(spec["commit"], 40)
    hex_id(spec["sha256"], 64)
    name = spec["path"]
    require(type(name) is str and re.fullmatch(
        r"Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/[A-Za-z0-9_-]+__grant\.json", name),
        "Studio campaign grant path")
    data = prior.fetch(spec["commit"], name)
    equal(sha(data), spec["sha256"], "immutable Studio grant bytes")
    equal(prior.fetch(spec["commit"], name + ".sha256").decode().split(),
          [spec["sha256"], Path(name).name], "Studio grant checksum")
    grant = check.strict(data, 8192)
    equal(grant["schema"], "staged-policy-studio-grant/1", "grant kind")
    return grant


def admit(config, spec, inspect=None, authority=None):
    configuration(config)
    grant = (authority or operator)(spec)
    # Reject a crossed grant before inspecting the target installation or fixture.
    for field, key in (("source", "commit"), ("tree", "tree"), ("input_sha256", "input_sha256"), ("run", "run")):
        equal(grant[field], config[key], "operator " + field)
    equal(grant["arms"], ARMS, "operator population")
    equal(grant["budget"], BUDGET, "operator budget")
    ident = (inspect or custody.identity)(config)
    data, expected = envelope(config, ident)
    equal(grant, expected, "entire measured physical description")
    path = Path(config["private_description"])
    st = path.lstat()
    require(st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1
            and prior.old.raw(path, 1 << 20) == data, "original private description")
    return ident


def claim_for(cfg, spec, ident, pid):
    return dict(schema="staged-policy-campaign-claim/1", run=ident["run"], source=ident["commit"],
                tree=ident["tree"], input_sha256=ident["input_sha256"], config=str(cfg),
                config_sha256=prior.old.hashed(cfg), grant=spec, pid=pid, budget=BUDGET)


def intent_for(cfg, spec, ident, claim_hash, pid, ordinal):
    profile, mode, policy = ARMS[ordinal]
    return dict(schema="staged-policy-intent/1", ordinal=ordinal, profile=profile, arm=mode,
                policy=policy, config=str(cfg), grant=spec, claim_sha256=claim_hash,
                supervisor_pid=pid, run=ident["run"], commit=ident["commit"], tree=ident["tree"],
                input_sha256=ident["input_sha256"], binary_sha256=ident["binary_sha256"],
                build_sha256=ident["build_sha256"], page_size=ident["page_size"])


def startup(ident, intent, raw_hash, images):
    return dict(schema="staged-policy-startup/1", ordinal=intent["ordinal"], profile=intent["profile"],
                arm=intent["arm"], policy=intent["policy"], run=ident["run"],
                source=ident["commit"], tree=ident["tree"], intent_sha256=raw_hash,
                closure_sha256=ident["input_sha256"], input_sha256=ident["input_sha256"],
                page_size=ident["page_size"], reference=ident["reference"], images=images,
                binary_sha256=ident["binary_sha256"], build_sha256=ident["build_sha256"])


def arm_dir(output, index):
    require(type(index) is int and 0 <= index < len(ARMS), "arm ordinal")
    return output / ("-".join((str(index), *ARMS[index])))


def verify_child(intent_path, observed, compiled, emit=True):
    intent = doc(intent_path, 65536)
    cfg = prior.path(intent["config"])
    config = doc(cfg)
    output, claim = configuration(config)
    index = intent["ordinal"]
    directory = arm_dir(output, index)
    require(intent_path == directory / "policy-intent.json" and
            all(not os.path.lexists(directory / n) for n in ("startup.json", "out", "completed.json")),
            "one startup at original position")
    ident = admit(config, intent["grant"])
    pid = observed["parent"]
    require(type(pid) is int and pid > 1, "supervisor PID")
    equal(doc(claim), claim_for(cfg, intent["grant"], ident, pid), "original campaign claim")
    equal(intent, intent_for(cfg, intent["grant"], ident, prior.old.hashed(claim), pid, index),
          "original campaign intent")
    equal(compiled, ident["verifier_modules"], "pre-import verifier closure")
    images = prior.expected_images(ident, config)
    equal(observed, dict(images=images, binary=config["binary"], parent=pid, reference=ident["reference"],
                         abi=prior.old.check.ABI_STAMP, seal=ident["seal"],
                         rustc="rustc 1.95.0 (59807616e 2026-04-14)", profile="release",
                         mlx_commit=prior.old.PINS["mlx"], mlx_c_commit=prior.old.PINS["mlx-c"],
                         prefix=config["prefix"]), "actual loaded images, executable and ABI")
    for _ in range(50):
        if (directory / "started.json").exists():
            break
        time.sleep(.02)
    equal(doc(directory / "started.json"), {"pid": os.getppid()}, "owned native child")
    for prev in range(index):
        prior.check_completion(arm_dir(output, prev))
    cap = startup(ident, intent, prior.old.hashed(intent_path), images)
    prior.exclusive(directory / "startup.json", cap)
    if emit:
        prior.old.emit_line(prior.old.compact_line(cap))
    return cap


def start_campaign(cfg, spec, inspect=None, authority=None, create_claim=None):
    """The immutable installation-side claim is consumed at exclusive creation."""
    config = doc(cfg)
    output, claim = configuration(config)
    require(not os.path.lexists(output) and not os.path.lexists(claim), "occupied campaign")
    identity = admit(config, spec, inspect, authority)
    pid = os.getpid()
    for i in range(len(ARMS)):
        require(len(canonical(intent_for(cfg, spec, identity, "0"*64, pid, i))) <= 65536, "intent bytes")
    record = claim_for(cfg, spec, identity, pid)
    (create_claim or prior.exclusive)(claim, record)
    prior.sync_dir(claim.parent)
    return config, identity, claim, record


def launch(cfg, spec):
    deadline = time.monotonic() + BUDGET["campaign_seconds"]
    def alarm(*_args):
        raise TimeoutError("policy campaign deadline")
    previous = signal.signal(signal.SIGALRM, alarm)
    owned = False
    try:
        signal.setitimer(signal.ITIMER_REAL, BUDGET["campaign_seconds"])
        config, ident, claim, record = start_campaign(cfg, spec)
        output = Path(config["output"])
        output.mkdir(mode=0o700)
        owned = True
        digest = prior.old.hashed(claim)
        def live():
            equal(doc(cfg), config, "live config")
            equal(admit(config, spec), ident, "live physical identity")
            equal(doc(claim), record, "live claim")
        for i in range(len(ARMS)):
            live()
            directory = arm_dir(output, i)
            directory.mkdir(mode=0o700)
            intent = directory / "policy-intent.json"
            prior.exclusive(intent, intent_for(cfg, spec, ident, digest, os.getpid(), i))
            require(time.monotonic() < deadline, "prelaunch deadline")
            signal.setitimer(signal.ITIMER_REAL, 0)
            prior.wait_child([config["binary"], "--intent", str(intent)],
                             prior.old.child_environment(prior.path(config["prefix"])),
                             directory, deadline, BUDGET["child_seconds"])
            remaining = deadline - time.monotonic()
            require(remaining > 0, "postchild deadline")
            signal.setitimer(signal.ITIMER_REAL, remaining)
            prior.check_completion(directory)
        live()
        prior.exclusive(output / "grade-intent.json", dict(run=ident["run"], claim_sha256=digest, grades=1))
        originals = Originals()
        equal(originals.verify(), ident["reference"], "independent original numerical reference")
        pop = {}
        manifest = {}
        for i, (profile, mode, policy) in enumerate(ARMS):
            directory = arm_dir(output, i)
            prior.check_completion(directory)
            equal(sorted(f.name for f in directory.iterdir()),
                  sorted(("policy-intent.json","started.json","completed.json","stdout.log","stderr.log","startup.json","out")),
                  "closed arm directory")
            path = directory / "policy-intent.json"
            intent = intent_for(cfg, spec, ident, digest, os.getpid(), i)
            equal(doc(path,65536), intent, "grade intent")
            cap = startup(ident, intent, prior.old.hashed(path), prior.expected_images(ident, config))
            equal(doc(directory/"startup.json",8192), cap, "live startup receipt")
            pop[profile, mode, policy] = check.arm_output(directory/"out",profile,mode,policy,ident,cap,originals)
            for f in sorted(directory.rglob("*")):
                if f.is_file():
                    require(f.stat().st_size <= BUDGET["arm_log"], "bounded captured file")
                    manifest[f.relative_to(output).as_posix()] = prior.old.hashed(f)
        coverage = check.compare(pop)
        equal(sorted(p.name for p in output.iterdir()),
              sorted(["grade-intent.json"]+[arm_dir(output,i).name for i in range(len(ARMS))]), "campaign file set")
        require(sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) < BUDGET["campaign_disk"]-(1<<20),
                "campaign disk admission")
        live()
        require(time.monotonic() < deadline, "grading deadline")
        prior.exclusive(output/"result.json", dict(schema="staged-policy-native-result/1", run=ident["run"],
                        status="accepted", claim_sha256=digest, identity=ident, coverage=coverage, files=manifest))
    except BaseException as exc:
        if owned:
            prior.exclusive(output/"failure.json", dict(status="failed",reason=str(exc)[:512],
                            remaining_effects="unknown; inspect the retained arm files"))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action",required=True)
    sub.add_parser("describe-binding").add_argument("config",type=Path)
    run = sub.add_parser("launch")
    run.add_argument("config",type=Path)
    run.add_argument("grant_pointer",type=Path)
    args = parser.parse_args()
    cfg = prior.path(args.config)
    if args.action == "describe-binding":
        prior.old.emit_line(canonical(prepare(cfg)))
    else:
        launch(cfg, doc(prior.path(args.grant_pointer),8192))


if __name__ == "__main__":
    main()
