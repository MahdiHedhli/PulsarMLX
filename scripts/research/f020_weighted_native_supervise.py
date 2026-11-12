"""Prospective four-arm weighted qualification. Only a separately issued physical grant can launch."""
import argparse
import base64
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import sys
import time

import f020_resident_mlp_supervise as old
import f020_weighted_native_bootstrap
import f020_weighted_native_reference as ref
import f020_weighted_native_check as check
from f020_weighted_native_reference import require,sha
from f020_weighted_native_check import equal

ROOT=ref.ROOT
BASE="b4da34f654e739878b411689e9065646df897b70"
TREE="0370f22dcf2f96d4599173a92928945181193c62"
REFERENCE="6ab6d2d0cc17f95eb18f25ed6230b4e281df7026b446845c60788892e87b587e"
CLAIM="f020-m3b-copied-weighted-v1.claim.json"
PREDECESSOR="fc6cb8558c56a237e4fc97dc42b87ff0426fb2e85718cb1759c7941fc9770456"
PREVIOUS_RESULT="a0f52ed23847ff5019583cf3bcc70e0301ca4f85c822d00e5cf1e75d101a628d"
FULL="weighted-mlp-physical-grant-v1"
ENVELOPE="weighted-mlp-description-grant-v1"
FORMAT="weighted-description-json-ascii-lf/1"
BUDGET=dict(children=4,child_seconds=300,campaign_seconds=900,grades=1,raw=0,retries=0)
HOST=dict(model="Mac13,2",chip="Apple M1 Ultra",memory="137438953472",page="16384",os="26.0",build="25A354",arch="arm64",system="Darwin")
CONFIG="repo prefix binary build installation freeze diagnostic_receipt output"
MODULES=(*old.VERIFIER_MODULES,"f020_weighted_mlp_reference","f020_weighted_native_rational","f020_weighted_native_reference","f020_weighted_native_check","f020_weighted_native_bootstrap","f020_weighted_native_supervise")
SEAMS={'crates/mlx-expert-mlp/Cargo.toml': '34eec17d2d322eb90552357e2265127045b7695c1c58317b5549646e379f9d7a', 'crates/mlx-expert-mlp/build.rs': '8a8d500e83eb1e4365fd849c98f7cd9abc18dcd1d6d6f4288a0d98a9c6d20b05', 'crates/mlx-expert-mlp/src/resident_native.rs': '8ee8aed58a8028790a784d909fc6c4dd98b641d5c9f57d6c15da374b3256ef2b'}
path=old.path
keys=old.exact_keys
exclusive=old.exclusive
wait_child=old.wait_child
installed=old.installed
links=old.links
file_hash=old.hashed
emit_line=old.emit_line


def doc(p,limit=1<<20):
    return ref.strict(old.raw(p,limit))


def modules():
    result={}
    for name in MODULES:
        m=sys.modules.get(name) or (sys.modules[__name__] if name==MODULES[-1] else None)
        p=ROOT/"scripts/research"/(name+".py")
        require(m is not None and Path(m.__file__).resolve(strict=True)==p and p.resolve(strict=True)==p,"verifier module origin")
        result[name]=sha(old.raw(p,524288))
    return result


def source():
    observed=old.source()
    equal(old.git("merge-base",BASE,observed["commit"]),BASE,"weighted ancestry")
    equal(old.git("rev-parse",BASE+"^{tree}"),TREE,"Rust019 base")
    require(observed["commit"]!=BASE,"weighted candidate")
    delta=old.cmd("/usr/bin/git","diff","--no-renames","--name-status","-z",BASE,observed["commit"]).decode().split("\0")[:-1]
    require(len(delta)%2==0,"source delta")
    seen=set()
    for mode,n in zip(delta[::2],delta[1::2]):
        if n in SEAMS:
            require(mode=="M" and old.hashed(ROOT/n)==SEAMS[n],"protected native seam");seen.add(n)
        else:
            require(mode=="A" and re.fullmatch(r"(?:crates/mlx-expert-mlp/src/bin/qualify-weighted-mlp\.rs|crates/mlx-expert-mlp/(?:src|tests)/weighted_native[^/]*\.rs|crates/mlx-expert-mlp/src/weighted_native/.+|scripts/research/(?:tests/)?f020_weighted_native_\w+\.py|(?:fixtures/weighted-native-mlp|docs/research/f020/m3b-weighted-native)/.+)",n),"protected source delta")
        require(old.git("ls-tree",observed["commit"],"--",n).startswith("100644 blob "),"weighted source mode")
    equal(sorted(seen),sorted(SEAMS),"all three inherited seams")
    return observed


def host_facts():
    old.runtime.clean_inspector()
    require(not os.environ.get("GITHUB_ACTIONS"),"physical host")
    result={k:old.cmd("/usr/sbin/sysctl","-n",n).decode().strip() for k,n in
            (("model","hw.model"),("chip","machdep.cpu.brand_string"),("memory","hw.memsize"),("page","hw.pagesize"))}
    return dict(result,os=old.cmd("/usr/bin/sw_vers","-productVersion").decode().strip(),build=old.cmd("/usr/bin/sw_vers","-buildVersion").decode().strip(),arch=platform.machine(),system=platform.system())


def predecessor(config):
    receipt=path(config["installation"]);claim=receipt.parent/old.CLAIM
    equal(file_hash(claim),PREDECESSOR,"original spent M2b claim")
    prior=doc(claim);cfg=path(prior["config"]);equal(old.hashed(cfg),prior["config_sha256"],"original M2b configuration")
    original=doc(cfg);equal(original["installation"],str(receipt),"original installation location")
    result=path(original["output"])/"result.json"
    equal(file_hash(result),PREVIOUS_RESULT,"original accepted M2b result")
    prev=doc(result);equal([prev["claim_sha256"],prev["status"]],[PREDECESSOR,"accepted"],"M2b completion")
    return dict(claim=str(claim),claim_sha256=PREDECESSOR,config=str(cfg),config_sha256=prior["config_sha256"],result=str(result),result_sha256=PREVIOUS_RESULT)


def locations(config):
    output=path(config["output"],False);receipt=path(config["installation"])
    for p in (ROOT,path(config["prefix"]),receipt.parent,path(config["freeze"]).parent,path(config["diagnostic_receipt"]).parent,
              path(config["build"]).parent,path(config["binary"]).parent):
        require(not output.is_relative_to(p) and not p.is_relative_to(output),"separate original output")
    return output,receipt.parent/CLAIM


def configuration(config):
    fields={k:v for k,v in config.items() if k!="operator"}
    keys(fields,CONFIG,"weighted configuration")
    require(all(type(v) is str and 0<len(v.encode())<=1024 for v in fields.values()),"configuration paths")
    equal(fields["repo"],str(ROOT),"working source")
    return fields


def binary_seal(closure):
    payload = dict(modules=[[n, closure[n]] for n in MODULES], reference=REFERENCE, abi=old.check.ABI_STAMP)
    return "weighted-native-build-v1." + sha(ref.canonical(payload))


def contains_marker(binary, marker):
    value = marker.encode("ascii")
    require(0 < binary.stat().st_size <= 128 << 20, "physical binary size")
    tail = b""
    with binary.open("rb") as stream:
        for part in iter(lambda: stream.read(65536), b""):
            chunk = tail + part
            if value in chunk:
                return True
            tail = chunk[-(len(value)-1):]
    return False


def identity(config):
    configuration(config);host=host_facts();equal(host,HOST,"physical host facts")
    src=source();closure=modules()
    binary=path(config["binary"]);receipt=path(config["build"]);build=doc(receipt);artifact=path(build["artifact"])
    require(binary.name=="qualify-weighted-mlp" and binary.parent.name=="release" and os.access(binary,os.X_OK),"weighted release executable")
    msg=doc(artifact)
    equal([msg["reason"],msg["target"]["name"],msg["target"]["kind"],msg["target"]["src_path"],msg["executable"],msg["profile"]["test"],msg["profile"]["opt_level"]],
          ["compiler-artifact",binary.name,["bin"],str(ROOT/"crates/mlx-expert-mlp/src/bin/qualify-weighted-mlp.rs"),str(binary),False,"3"],"weighted build artifact")
    require("mlx-expert-mlp" in msg["package_id"] and sorted(msg["features"]) in (["weighted-native"],["default","weighted-native"]),"weighted package feature")
    binary_hash=old.hashed(binary)
    equal([build["commit"],build["tree"],build["prefix"],build["binary_sha256"],build["artifact_sha256"],build["verifier_modules"],build["reference"]],
          [src["commit"],src["tree"],config["prefix"],binary_hash,old.hashed(artifact),closure,REFERENCE],"build source/reference binding")
    seal=binary_seal(closure)
    require(contains_marker(binary,seal) and contains_marker(binary,old.check.ABI_STAMP),"compiled weighted verifier/reference/ABI seal")
    equal(sha(ref.bounded(ref.FILE,ref.REFERENCE_LIMIT)),REFERENCE,"reference freeze")
    stamp=build["accounting_abi_stamp"];accounting=old.check.accounting_proof(ROOT,stamp)
    equal(stamp,old.check.ABI_STAMP,"compiler and accounting ABI")
    linkage=links(binary);equal(linkage,build["linkage"],"live linkage")
    require(all(any(n in line for line in linkage) for n in ("libmlx.dylib","libmlxc.dylib")),"native links")
    native=installed(config)
    equal([native["install_sha256"],native["mlx_commit"],native["mlx_c_commit"],native["static_runtime_sha256"]],
          [old.INSTALL,old.PINS["mlx"],old.PINS["mlx-c"],old.runtime.RUNTIME_SHA256],"retained installation identity")
    for key,filename in (("libmlx","libmlx.dylib"),("libmlxc","libmlxc.dylib")):
        record=native["static_inspection"]["files"][filename]
        equal(record["lexical"],str(path(config["prefix"])/"lib"/filename),"retained image location")
        equal(record["sha256"],native[key],"retained image identity")
    return dict(**src,host=host,binary=str(binary),binary_sha256=binary_hash,build=str(receipt),build_sha256=old.hashed(receipt),artifact=str(artifact),
                verifier_modules=closure,reference=REFERENCE,seal=seal,accounting=accounting,native=native,predecessor=predecessor(config),
                version="0.31.2",book=ref.BOOKS,input=ref.fixtures.INPUT)


def description(config,identity):
    c=configuration(config)
    return dict(schema=FULL,configuration=c,config_binding=sha(old.canonical(c)),identity=identity,arms=ref.ARMS,budget=BUDGET)


def binding(full):
    keys(full,"schema configuration config_binding identity arms budget","weighted full description")
    equal(full["schema"],FULL,"full schema");data=old.description_bytes(full);i=full["identity"]
    env=dict(schema=ENVELOPE,description=dict(schema=FULL,format=FORMAT,bytes=len(data),sha256=sha(data)),
             source={k:i[k] for k in ("commit","tree")},binary_sha256=i["binary_sha256"],build_sha256=i["build_sha256"],reference=i["reference"],
             config_binding=full["config_binding"],arms=full["arms"],budget=full["budget"])
    validate(env);return data,env


def validate(env):
    keys(env,"schema description source binary_sha256 build_sha256 reference config_binding arms budget","weighted envelope fields")
    equal(env["schema"],ENVELOPE,"weighted envelope")
    keys(env["source"],"commit tree","source");keys(env["description"],"schema format bytes sha256","description")
    d=env["description"]
    equal([d["schema"],d["format"]],[FULL,FORMAT],"serializer")
    require(type(d["bytes"]) is int and 0<d["bytes"]<=1<<20,"description length")
    for v in env["source"].values():old.hex_field(v,40)
    for v in [env[k] for k in ("binary_sha256","build_sha256","reference","config_binding")]+[d["sha256"]]:old.hex_field(v,64)
    equal(env["budget"],BUDGET,"budget");equal(env["arms"],ref.ARMS,"arm order");equal(env["reference"],REFERENCE,"frozen reference")


def fetch(commit,name):
    gh=shutil.which("gh",path="/opt/homebrew/bin:/usr/local/bin:/usr/bin");require(gh,"authenticated GitHub client")
    entry=json.loads(old.cmd(gh,"api","repos/MahdiHedhli/PulsarMLX-Prompts/contents/"+name+"?ref="+commit))
    require(entry["path"]==name and entry["size"]<=1<<20,"operator path and size")
    b=base64.b64decode(entry["content"]);require(len(b)==entry["size"],"operator bytes");return b


def operator(spec):
    keys(spec,"commit path sha256","operator keys")
    commit,name,digest=(spec[k] for k in ("commit","path","sha256"))
    old.hex_field(commit,40);old.hex_field(digest,64)
    require(re.fullmatch(r"Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/[A-Za-z0-9_-]+__prompt\.md",name),"physical operator path")
    markdown=fetch(commit,name);equal(sha(markdown),digest,"operator bytes")
    equal(fetch(commit,name+".sha256").decode().split(),[digest,Path(name).name],"operator checksum")
    return parse_fence(markdown)


def admit(config):
    old.runtime.clean_inspector()
    envelope=operator(config["operator"])
    observed=identity(config);equal(binding(description(config,observed))[1],envelope,"complete private description binding")
    return observed


def claim_record(cfg,ident,pid):
    return dict(schema="weighted-mlp-start-v1",pid=pid,config=str(cfg),config_sha256=old.hashed(cfg),identity=ident,budget=BUDGET)


def intent_record(cfg,claim,claim_hash,ident,pid,p,a):
    return dict(schema="weighted-mlp-intent-v1",repo=str(ROOT),config=str(cfg),claim=str(claim),claim_sha256=claim_hash,
                supervisor_pid=pid,profile=p,arm=a,identity=ident,reference=REFERENCE)


def receipt(ident,p,a,intent_sha,images):
    return dict(profile=p,arm=a,reference=REFERENCE,intent_sha256=intent_sha,source=ident["commit"],tree=ident["tree"],
                binary_sha256=ident["binary_sha256"],build_sha256=ident["build_sha256"],images=images)


def expected_images(ident,config):
    files=ident["native"]["static_inspection"]["files"]
    loaded={n:files[n]["canonical"] for n in ("libmlx.dylib","libmlxc.dylib")}
    return dict(loaded=loaded,mlx_version_symbol=loaded["libmlxc.dylib"])


def verify_child(intent,observed,compiled,emit=True):
    cap=doc(intent,65536);cfg=path(cap["config"]);config=doc(cfg);output,claim=locations(config)
    p,a=cap["profile"],cap["arm"];i=ref.ARMS.index((p,a));directory=output/f"{i}-{p}-{a}"
    require(intent==directory/"intent.json" and not os.path.lexists(directory/"out") and not os.path.lexists(directory/"completed.json"),"single supervised child position")
    ident=admit(config);pid=observed["parent"];cr=claim_record(cfg,ident,pid)
    equal(doc(claim),cr,"weighted original claim");equal(cap,intent_record(cfg,claim,old.hashed(claim),ident,pid,p,a),"complete weighted intent")
    equal(compiled,ident["verifier_modules"],"compiled verifier closure")
    expected=expected_images(ident,config)
    equal(observed,dict(images=expected,binary=config["binary"],parent=pid,reference=REFERENCE,abi=old.check.ABI_STAMP,seal=ident["seal"],
        rustc="rustc 1.95.0 (59807616e 2026-04-14)",profile="release",mlx_commit=old.PINS["mlx"],mlx_c_commit=old.PINS["mlx-c"],prefix=config["prefix"]),"actual child image, build or ABI")
    for _ in range(50):
        if (directory/"started.json").exists():break
        time.sleep(.02)
    started=doc(directory/"started.json");equal(started,dict(pid=os.getppid()),"verifier parent PID")
    for n,(prev,arm) in enumerate(ref.ARMS[:i]):
        previous=output/f"{n}-{prev}-{arm}";check_completion(previous)
    summary=receipt(ident,p,a,old.hashed(intent),expected)
    if emit:old.emit_line(old.compact_line(summary))
    return summary


def check_completion(directory):
    pid=doc(directory/"started.json")["pid"];require(type(pid) is int and pid>0,"child PID")
    equal(doc(directory/"completed.json"),dict(pid=pid,exit=0,reaped=True,timeout=False),"serial child completion")


def prepare(cfg,destination):
    raw=old.raw(cfg,1<<20);config=ref.strict(raw);keys(config,CONFIG,"preparation fields")
    dest=path(destination,False);output,claim=locations(config)
    def check_paths():
        require(not any(os.path.lexists(p) for p in (claim,output,dest)),"occupied preparation destination")
        require(dest not in (cfg,path(config["build"])),"description overlaps config/build")
        for p in (ROOT,path(config["prefix"]),claim.parent,path(config["freeze"]).parent,path(config["diagnostic_receipt"]).parent,path(config["binary"]).parent,output):
            require(not dest.is_relative_to(p) and not p.is_relative_to(dest),"protected description location")
    check_paths();fd=os.open(dest.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parent=os.fstat(fd);data,envelope=binding(description(config,identity(config)));check_paths()
        require(old.raw(cfg,1<<20)==raw and os.path.samestat(parent,dest.parent.lstat()),"preparation custody drift")
        saved=old.write_private_description(fd,dest.name,data);os.fsync(fd);actual=dest.lstat()
        require(os.path.samestat(actual,saved) and actual.st_nlink==1 and actual.st_ctime_ns==saved.st_ctime_ns and
                not os.path.lexists(output) and not os.path.lexists(claim),"private description custody")
        emit_line(old.compact_line(envelope))
    finally:os.close(fd)


def launch(cfg):
    config=doc(cfg);output,claim=locations(config)
    require(not os.path.lexists(output) and not os.path.lexists(claim),"occupied weighted output or claim")
    deadline=time.monotonic()+900;pid=os.getpid();ident=admit(config);cr=claim_record(cfg,ident,pid)
    def live():
        equal(doc(cfg),config,"configuration drift")
        equal(admit(config),ident,"live weighted identity")
        equal(doc(claim),cr,"live weighted claim")
    env=old.child_environment(path(config["prefix"]));created=False
    def timeout(*args):raise TimeoutError("weighted campaign deadline")
    previous=signal.signal(signal.SIGALRM,timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL,max(.000001,deadline-time.monotonic()))
        require(not os.path.lexists(output),"occupied weighted output")
        exclusive(claim,cr);claim_hash=old.hashed(claim);output.mkdir(mode=0o700);created=True
        for i,(p,a) in enumerate(ref.ARMS):
            directory=output/f"{i}-{p}-{a}";directory.mkdir(mode=0o700)
            cap=intent_record(cfg,claim,claim_hash,ident,pid,p,a);require(len(old.canonical(cap))<=65536,"intent size")
            intent=directory/"intent.json";exclusive(intent,cap);live()
            # wait_child owns spawn, deadline, kill and reap. An asynchronous
            # alarm in the spawn-to-ownership interval could strand a child.
            signal.setitimer(signal.ITIMER_REAL,0)
            wait_child([config["binary"],"--intent",str(intent)],env,directory,deadline,300)
            require(time.monotonic()<deadline,"campaign deadline after child")
            signal.setitimer(signal.ITIMER_REAL,max(.000001,deadline-time.monotonic()))
        live()
        exclusive(output/"grading-intent.json",dict(claim_sha256=claim_hash,count=1,reference=REFERENCE))
        originals=ref.Originals();equal(originals.verify(),REFERENCE,"independent recomputation")
        pop={};manifest={}
        for i,(p,a) in enumerate(ref.ARMS):
            directory=output/f"{i}-{p}-{a}";check_completion(directory)
            intent=directory/"intent.json";equal(doc(intent),intent_record(cfg,claim,claim_hash,ident,pid,p,a),"graded intent")
            equal(sorted(f.name for f in directory.iterdir()),sorted(("intent.json","started.json","completed.json","stdout.log","stderr.log","out")),"closed arm directory")
            for name in ("stdout.log","stderr.log"):
                log=path(directory/name);require(log.is_file() and log.stat().st_size<=8<<20,"bounded child capture")
            with (directory/"gate-progress.jsonl").open("xb") as log:
                def observe(value):
                    record=old.compact_line(value)
                    require(log.tell()+len(record)<=16384,"gate progress bound")
                    log.write(record);log.flush();os.fsync(log.fileno())
                population=check.arm_output(directory/"out",p,a,ident,receipt(ident,p,a,old.hashed(intent),expected_images(ident,config)),originals,observe)
            pop[p,a]=population
            exclusive(directory/"gates.json",population[2])
            for f in sorted(directory.rglob("*")):
                if f.is_file():manifest[str(f.relative_to(output))]=old.hashed(f)
        coverage=check.compare(pop)
        manifest["grading-intent.json"]=old.hashed(output/"grading-intent.json")
        equal(sorted(p.name for p in output.iterdir()),sorted(["grading-intent.json"]+[f"{i}-{p}-{a}" for i,(p,a) in enumerate(ref.ARMS)]),"closed campaign output")
        live();require(time.monotonic()<=deadline,"campaign deadline")
        exclusive(output/"result.json",dict(schema="weighted-mlp-result-v1",status="accepted",claim_sha256=claim_hash,identity=ident,reference=REFERENCE,coverage=coverage,evidence=manifest))
    except BaseException as exc:
        if created:
            exclusive(output/"failure.json",dict(status="failed",reason=str(exc)[:512],retirement="see reached child records; otherwise unknown"))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("describe-binding","launch","identity"));p.add_argument("configuration");p.add_argument("destination",nargs="?")
    args=p.parse_args();cfg=path(args.configuration)
    if args.action=="describe-binding":
        require(args.destination,"private description destination");prepare(cfg,args.destination)
    else:
        require(args.destination is None,"unexpected argument")
        if args.action=="launch":launch(cfg)
        else:old.emit_line(old.description_bytes(identity(doc(cfg))))



def parse_fence(markdown):
    # Count all grant openers first: a malformed second block must not disappear.
    openers = list(
        re.finditer(
            rb"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*weighted-mlp-grant\b[^\n]*$", markdown
        )
    )
    require(
        len(openers) == 1 and openers[0][0] == b"```weighted-mlp-grant",
        "one exact weighted grant fence",
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
    require(payload is not None, "malformed weighted grant fence")
    grant = ref.strict(payload[1])
    validate(grant)
    return grant


if __name__=="__main__":
    main()
