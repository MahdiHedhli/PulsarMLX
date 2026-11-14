"""Prospective four-arm weighted qualification. Only a separately issued physical grant can launch."""
import argparse
import ast
import base64
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import resource
import hashlib
import stat
import sys
import time

import f020_resident_mlp_supervise as old
import f020_staged_weighted_bootstrap
import f020_weighted_native_reference as ref
import f020_staged_weighted_check as check
from f020_weighted_native_reference import require,sha
from f020_weighted_native_check import equal

ROOT=ref.ROOT
BASE="5110ab450e51d3e45383bb48ec351f3bb9ef96eb"
TREE="29c60a1ba7756d542652cfe05c9b254780379995"
REFERENCE="6ab6d2d0cc17f95eb18f25ed6230b4e281df7026b446845c60788892e87b587e"
CLAIM="f020-m4b-staged-weighted-v1.claim.json"
M3_CLAIM="f020-m3b-copied-weighted-v1.claim.json"
M3_SPENT="3d85b128040dbe9fa4f17642400dd6c5dc97a76372904c227e17872e79b58f6d"
M3_RESULT="cea19eb076ceeea1d927ee94dddb5b6a942e8e3e302e787736c1044ebea7dbec"
PREDECESSOR="fc6cb8558c56a237e4fc97dc42b87ff0426fb2e85718cb1759c7941fc9770456"
PREVIOUS_RESULT="a0f52ed23847ff5019583cf3bcc70e0301ca4f85c822d00e5cf1e75d101a628d"
FULL="staged-weighted-mlp-physical-grant-v1"
ENVELOPE="staged-weighted-mlp-description-grant-v1"
FORMAT="staged-weighted-description-json-ascii-lf/1"
BUDGET=dict(children=4,child_seconds=300,campaign_seconds=900,grades=1,raw=0,retries=0)
HOST=dict(model="Mac13,2",chip="Apple M1 Ultra",memory="137438953472",page="16384",os="26.0",build="25A354",arch="arm64",system="Darwin")
CONFIG="private_description repo prefix binary build installation freeze diagnostic_receipt output"
MODULES=(*old.VERIFIER_MODULES,"f020_weighted_mlp_reference","f020_weighted_native_rational","f020_weighted_native_reference",
         "f020_weighted_native_check","f020_admission_screen_reference_v1","f020_staged_weighted_check","f020_staged_weighted_bootstrap","f020_staged_weighted_supervise")
PKG="crates/mlx-expert-mlp/"
SEAMS=(PKG+"Cargo.toml",PKG+"build.rs",PKG+"src/weighted/mod.rs")
ADDED={PKG+n for n in ("src/weighted/staged.rs","src/bin/qualify-staged-weighted-mlp.rs","src/staged_weighted_native_child.rs","src/staged_weighted_native_pins.rs","tests/staged_weighted_host.rs")}
ADDED.update("scripts/research/"+n for n in ("f020_staged_weighted_check.py","f020_staged_weighted_supervise.py","f020_staged_weighted_bootstrap.py","tests/f020_staged_weighted_protocol_test.py"))
ADDED.update("docs/research/f020/m4b-staged-native/"+n for n in ("README.md","host-evidence.json"))
path=old.path
keys=old.exact_keys
exclusive=old.exclusive

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
    # Verify the objects actually imported by production source. A matching
    # sys.modules entry alone does not bind an earlier from-import alias.
    for owner in MODULES:
        mod=sys.modules.get(owner) or sys.modules[__name__]
        tree=ast.parse(old.raw(ROOT/"scripts/research"/(owner+".py"),524288))
        for statement in tree.body:
            if not isinstance(statement,(ast.Import,ast.ImportFrom)):continue
            for item in statement.names:
                name=statement.module if isinstance(statement,ast.ImportFrom) else item.name
                if not name or not name.startswith("f020_"):continue
                require(name in result,"unbound imported helper")
                target=sys.modules[name]
                actual=vars(mod)[item.asname or item.name]
                expected=getattr(target,item.name) if isinstance(statement,ast.ImportFrom) else target
                require(actual is expected,"imported helper origin")
                if hasattr(actual,"__code__"):
                    defining=actual.__module__
                    require(defining in result and Path(actual.__code__.co_filename).resolve(strict=True)==ROOT/"scripts/research"/(defining+".py"),"defining helper origin")
    return result


def expected_seams():
    """Rebuild the three permitted insertions from the original Git objects."""
    cargo, build, weighted = [old.cmd("/usr/bin/git","show",BASE+":"+n) for n in SEAMS]
    feature=b"staged-weighted-native = []\n"
    binary=b'\n[[bin]]\nname = "qualify-staged-weighted-mlp"\npath = "src/bin/qualify-staged-weighted-mlp.rs"\nrequired-features = ["staged-weighted-native"]\ntest = false\n'
    extra=b'    if std::env::var_os("CARGO_FEATURE_STAGED_WEIGHTED_NATIVE").is_some() {\n        bins.push("qualify-staged-weighted-mlp");\n    }\n'
    return (cargo.replace(b"weighted-native = []\n",b"weighted-native = []\n"+feature)+binary,
            build.replace(b"    for bin in bins {",extra+b"    for bin in bins {"),
            weighted.replace(b"mod book;\n",b"mod book;\npub mod staged;\n"))

def source():
    head=old.git("rev-parse","HEAD")
    equal(old.git("merge-base",BASE,head),BASE,"staged ancestry")
    equal(old.git("rev-parse",BASE+"^{tree}"),TREE,"Rust022 tree")
    # Check the closed delta before reading its sources or traversing a new candidate.
    stats=old.cmd("/usr/bin/git","diff","--no-renames","--shortstat",BASE,head)
    require(re.match(rb"^\s*"+str(len(SEAMS)+len(ADDED)).encode()+rb" files changed,",stats),"source change count")
    changes=old.cmd("/usr/bin/git","diff","--no-renames","--name-status","-z",BASE,head)
    require(len(changes)<=16384,"source delta size")
    pair=changes.decode().split("\0")[:-1]
    equal(sorted(zip(pair[::2],pair[1::2])),sorted([("M",n) for n in SEAMS]+[("A",n) for n in ADDED]),"exact staged source delta")
    for n in sorted(ADDED|set(SEAMS)):
        require(old.git("ls-tree",head,"--",n).startswith("100644 blob "),"staged mode")
        old.raw(ROOT/n,1<<20)
    for n,expected in zip(SEAMS,expected_seams()):
        equal(sha(old.raw(ROOT/n,1<<20)),sha(expected),"protected insertion")
    observed=old.source()  # Generic complete path/mode/blob verification, independent of M3's delta validator.
    equal([observed["commit"],observed["file_count"]],[head,5193+len(ADDED)],"complete staged inventory")
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
    m2=dict(claim=str(claim),claim_sha256=PREDECESSOR,config=str(cfg),config_sha256=prior["config_sha256"],result=str(result),result_sha256=PREVIOUS_RESULT)
    m3_claim=receipt.parent/M3_CLAIM
    equal(file_hash(m3_claim),M3_SPENT,"original spent M3 claim")
    row=doc(m3_claim);cfg=path(row["config"]);equal(old.hashed(cfg),row["config_sha256"],"original M3 configuration")
    original=doc(cfg);equal(original["installation"],str(receipt),"original M3 installation")
    result=path(original["output"])/"result.json";equal(file_hash(result),M3_RESULT,"original accepted M3 result")
    m3=doc(result);equal([m3["status"],m3["claim_sha256"]],["accepted",M3_SPENT],"M3 completion")
    return dict(m2=m2,m3=dict(claim=str(m3_claim),claim_sha256=M3_SPENT,config=str(cfg),config_sha256=row["config_sha256"],result=str(result),result_sha256=M3_RESULT))


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
    require(len(set(fields.values()))==len(fields),"distinct configuration roles")
    return fields


def compiled_sources():
    """Conservative closure for the local package dependencies and selected native binary."""
    files={"Cargo.toml","Cargo.lock","scripts/research/f020_fused_swiglu_cpu_guard_v2_4.h",
           "fixtures/resident-expert-mlp/manifest.json",PKG+"src/bin/qualify-staged-weighted-mlp.rs"}
    for name in ("backend","expert-residency-core","mlx-affine","safetensors-catalog","mlx-expert-ranges","mlx-native-affine","mlx-expert-mlp"):
        crate=ROOT/"crates"/name
        for f in [crate/"Cargo.toml",crate/"build.rs",*(crate/"src").rglob("*")]:
            if not f.is_file() or f.suffix not in (".rs",".cpp",".c",".toml"):continue
            n=f.relative_to(ROOT).as_posix()
            if "/src/bin/" in n and n not in files and not ("/mlx-native-affine/src/bin/qualify/" in n and f.name in ("bridge.rs","ffi.rs","native.rs","provenance.rs")):continue
            if n==PKG+"src/staged_weighted_native_pins.rs":continue  # generated witness, validated separately
            files.add(n)
    require(len(files)<=192,"compiled source count")
    rows={n:sha(old.raw(ROOT/n,1<<20)) for n in sorted(files)}
    return rows

def binary_seal(closure):
    payload=dict(modules=[[n,closure[n]] for n in MODULES], reference=REFERENCE, abi=old.check.ABI_STAMP,
                 compiled=sha(ref.canonical(compiled_sources())))
    return "staged-weighted-native-build-v1."+sha(ref.canonical(payload))

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


def fixture_identity():
    # Read only these original synthetic files. This is byte admission, never numerical regrading.
    view=ref.fixtures.VIEW; manifest=old.raw(view/"manifest.json",1<<20)
    equal(sha(manifest),old.check.VIEW_SHA,"original view manifest")
    recipes=ref.strict(manifest)["recipes"]
    original_hash=sha(old.raw(ref.fixtures.ORIGINAL/"manifest.json",1<<20))
    equal(original_hash,ref.fixtures.MANIFEST,"original composition manifest")
    rows={}
    for name in ("default","mixed"):
        recipe=recipes[name];inputs={}
        for rel in recipe["inputs"]:
            raw=old.raw(ref.fixtures.ORIGINAL/rel,512)
            equal([len(raw),sha(raw)],[512,ref.fixtures.INPUT],"original activation bytes")
            inputs[rel]=sha(raw)
        equal(len(inputs),3,"fixed activation population")
        root=view/recipe["name"];files={}
        for filename,key in (("model.safetensors","shard"),("model.safetensors.index.json","index"),("config.json","config")):
            files[filename]=sha(old.raw(root/filename,1<<20))
            equal(files[filename],recipe["files"][key],"original copied source")
        ids=ref.route_ids(name,recipe)
        equal(recipe["files"]["original_manifest"],original_hash,"original recipe manifest")
        rows[name]=dict(inputs=inputs,files=files,route=ids,content=recipe["content"],metadata=recipe["metadata"])
    return rows

def identity(config):
    configuration(config);host=host_facts();equal(host,HOST,"physical host facts")
    src=source();closure=modules()
    binary=path(config["binary"]);receipt=path(config["build"]);build=doc(receipt);artifact=path(build["artifact"])
    require(binary.name=="qualify-staged-weighted-mlp" and binary.parent.name=="release" and os.access(binary,os.X_OK),"weighted release executable")
    msg=doc(artifact)
    equal([msg["reason"],msg["target"]["name"],msg["target"]["kind"],msg["target"]["src_path"],msg["executable"],msg["profile"]["test"],msg["profile"]["opt_level"]],
          ["compiler-artifact",binary.name,["bin"],str(ROOT/"crates/mlx-expert-mlp/src/bin/qualify-staged-weighted-mlp.rs"),str(binary),False,"3"],"weighted build artifact")
    require(msg["package_id"].split("#",1)[0]=="path+"+(ROOT/"crates/mlx-expert-mlp").as_uri() and msg["package_id"].split("#")[-1] in ("0.1.0","mlx-expert-mlp@0.1.0") and sorted(msg["features"]) in (["staged-weighted-native"],["default","staged-weighted-native"]),"weighted package feature")
    require(0 < binary.stat().st_size <= 128<<20,"binary size")
    binary_hash=old.hashed(binary)
    equal([build["commit"],build["tree"],build["prefix"],build["binary_sha256"],build["artifact_sha256"],build["verifier_modules"],build["reference"]],
          [src["commit"],src["tree"],config["prefix"],binary_hash,old.hashed(artifact),closure,REFERENCE],"build source/reference binding")
    seal=binary_seal(closure)
    pin_source=old.raw(ROOT/(PKG+"src/staged_weighted_native_pins.rs"),16384).decode()
    strings=re.findall(r'"([^"\n]*)"',pin_source)
    equal(strings,[seal,REFERENCE]+[v for name in MODULES for v in (name,closure[name])],"embedded staged pins")
    require(contains_marker(binary,seal) and contains_marker(binary,old.check.ABI_STAMP),"compiled weighted verifier/reference/ABI seal")
    equal(sha(ref.bounded(ref.FILE,ref.REFERENCE_LIMIT)),REFERENCE,"reference freeze")
    equal(build["compiled_source_sha256"],sha(ref.canonical(compiled_sources())),"compiled source binding")
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
                verifier_modules=closure,compiled_source_sha256=build["compiled_source_sha256"],reference=REFERENCE,seal=seal,accounting=accounting,native=native,predecessor=predecessor(config),
                fixture_bindings=fixture_identity(),artifact_sha256=old.hashed(artifact),version="0.31.2",book=ref.BOOKS,input=ref.fixtures.INPUT)


def description(config,identity):
    c=configuration(config)
    return dict(schema=FULL,configuration=c,config_binding=sha(old.canonical(c)),identity=identity,arms=check.ARMS,budget=BUDGET)


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
    equal(env["budget"],BUDGET,"budget");equal(env["arms"],check.ARMS,"arm order");equal(env["reference"],REFERENCE,"frozen reference")


def fetch(commit,name):
    gh=shutil.which("gh",path="/opt/homebrew/bin:/usr/local/bin:/usr/bin");require(gh,"authenticated GitHub client")
    entry=json.loads(old.cmd(gh,"api","repos/MahdiHedhli/PulsarMLX-Prompts/contents/"+name+"?ref="+commit))
    require(entry["path"]==name and entry["size"]<=1<<20,"operator path and size")
    b=base64.b64decode(entry["content"]);require(len(b)==entry["size"] and entry["sha"]==hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest(),"operator bytes");return b


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
    observed=identity(config);data,expected=binding(description(config,observed))
    equal(expected,envelope,"complete private description binding")
    original=path(config["private_description"]);meta=original.lstat()
    require(stat.S_IMODE(meta.st_mode)==0o600 and meta.st_nlink==1 and meta.st_uid==os.getuid(),"original private description custody")
    require(old.raw(original,1<<20)==data,"original private description bytes")
    return observed


def claim_record(cfg,ident,pid):
    return dict(schema="staged-weighted-mlp-start-v1",pid=pid,config=str(cfg),config_sha256=old.hashed(cfg),identity=ident,budget=BUDGET)


def intent_record(cfg,claim,claim_hash,ident,pid,p,a):
    record=dict(schema="staged-weighted-mlp-intent-v1",repo=str(ROOT),config=str(cfg),claim=str(claim),claim_sha256=claim_hash,
                supervisor_pid=pid,profile=p,arm=a,identity=ident,reference=REFERENCE)
    require(len(old.canonical(record))<=65536,"intent size")
    return record


def receipt(ident,p,a,intent_sha,images):
    return dict(profile=p,arm=a,reference=REFERENCE,intent_sha256=intent_sha,source=ident["commit"],tree=ident["tree"],
                binary_sha256=ident["binary_sha256"],build_sha256=ident["build_sha256"],images=images)


def expected_images(ident,config):
    files=ident["native"]["static_inspection"]["files"]
    loaded={n:files[n]["canonical"] for n in ("libmlx.dylib","libmlxc.dylib")}
    return dict(loaded=loaded,mlx_version_symbol=loaded["libmlxc.dylib"])


def verify_child(intent,observed,compiled,emit=True):
    cap=doc(intent,65536);cfg=path(cap["config"]);config=doc(cfg);output,claim=locations(config)
    p,a=cap["profile"],cap["arm"];i=check.ARMS.index((p,a));directory=output/f"{i}-{p}-{a}"
    require(intent==directory/"staged-intent.json" and not os.path.lexists(directory/"out") and not os.path.lexists(directory/"completed.json") and not os.path.lexists(directory/"startup.json"),"single supervised child position")
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
    for n,(prev,arm) in enumerate(check.ARMS[:i]):
        previous=output/f"{n}-{prev}-{arm}";check_completion(previous)
    summary=receipt(ident,p,a,old.hashed(intent),expected)
    exclusive(directory/"startup.json",summary)
    if emit:old.emit_line(old.compact_line(summary))
    return summary


spawn_child = subprocess.Popen

def group_gone(pid):
    try: os.killpg(pid,0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False

def wait_child(command,env,arm,deadline,limit):
    """Retain terminal observations even if signal delivery or reaping fails."""
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
    remaining=min(limit,deadline-time.monotonic())
    require(remaining>0,"child deadline before spawn")
    with (arm/"stdout.log").open("xb") as stdout,(arm/"stderr.log").open("xb") as stderr:
        child=spawn_child(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=limits)
        timed_out=False;failure=None;signal_error=None
        try:
            exclusive(arm/"started.json",dict(pid=child.pid))
            child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:timed_out=True
        except BaseException as exc:failure=exc
        finally:
            if child.poll() is None or not group_gone(child.pid):
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except OSError as exc:signal_error=type(exc).__name__
            observation=time.monotonic()+5
            try:rc=child.wait(timeout=max(0,observation-time.monotonic()))
            except (subprocess.TimeoutExpired,OSError):rc=None
            while not group_gone(child.pid) and time.monotonic()<observation:time.sleep(.025)
            gone=group_gone(child.pid)
            completion=dict(pid=child.pid,exit=rc,reaped=rc is not None,timeout=timed_out,group_gone=gone,signal_error=signal_error)
            exclusive(arm/"completed.json",completion)
    if failure:raise failure
    require(rc==0 and not timed_out and gone and signal_error is None and time.monotonic()<=deadline,"child failed, timed out or cleanup uncertain")

def check_completion(directory):
    pid=doc(directory/"started.json")["pid"];require(type(pid) is int and pid>0,"child PID")
    equal(doc(directory/"completed.json"),dict(pid=pid,exit=0,reaped=True,timeout=False,group_gone=True,signal_error=None),"serial child completion")


def prepare(cfg,destination):
    raw=old.raw(cfg,1<<20);config=ref.strict(raw);keys(config,CONFIG,"preparation fields")
    dest=path(destination,False);equal(str(dest),config["private_description"],"description destination");output,claim=locations(config)
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


def sync_dir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def launch(cfg):
    config=doc(cfg);output,claim=locations(config)
    require(not os.path.lexists(output) and not os.path.lexists(claim),"occupied weighted output or claim")
    deadline=time.monotonic()+900;pid=os.getpid()
    def live():
        equal(doc(cfg),config,"configuration drift")
        equal(admit(config),ident,"live weighted identity")
        equal(doc(claim),cr,"live weighted claim")
    env=old.child_environment(path(config["prefix"]));created=False
    def timeout(*args):raise TimeoutError("weighted campaign deadline")
    previous=signal.signal(signal.SIGALRM,timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL,max(.000001,deadline-time.monotonic()))
        ident=admit(config);equal(doc(cfg),config,"initial config drift");cr=claim_record(cfg,ident,pid)
        require(not os.path.lexists(output),"occupied weighted output")
        for profile,mode in check.ARMS:intent_record(cfg,claim,"0"*64,ident,pid,profile,mode)
        exclusive(claim,cr);sync_dir(claim.parent);claim_hash=old.hashed(claim);output.mkdir(mode=0o700);created=True
        for i,(p,a) in enumerate(check.ARMS):
            directory=output/f"{i}-{p}-{a}";directory.mkdir(mode=0o700)
            cap=intent_record(cfg,claim,claim_hash,ident,pid,p,a);require(len(old.canonical(cap))<=65536,"intent size")
            intent=directory/"staged-intent.json";exclusive(intent,cap);live()
            # wait_child owns spawn, deadline, kill and reap. An asynchronous
            # alarm in the spawn-to-ownership interval could strand a child.
            signal.setitimer(signal.ITIMER_REAL,0)
            wait_child([config["binary"],"--intent",str(intent)],env,directory,deadline,300)
            check_completion(directory)
            startup=receipt(ident,p,a,old.hashed(intent),expected_images(ident,config))
            equal(doc(directory/"startup.json",8192),startup,"startup verifier receipt")
            require(time.monotonic()<deadline,"campaign deadline after child")
            signal.setitimer(signal.ITIMER_REAL,max(.000001,deadline-time.monotonic()))
        live()
        exclusive(output/"grading-intent.json",dict(claim_sha256=claim_hash,count=1,reference=REFERENCE))
        originals=ref.Originals();equal(originals.verify(),REFERENCE,"independent recomputation")
        pop={};manifest={}
        for i,(p,a) in enumerate(check.ARMS):
            directory=output/f"{i}-{p}-{a}";check_completion(directory)
            intent=directory/"staged-intent.json";equal(doc(intent),intent_record(cfg,claim,claim_hash,ident,pid,p,a),"graded intent")
            equal(sorted(f.name for f in directory.iterdir()),sorted(("staged-intent.json","started.json","startup.json","completed.json","stdout.log","stderr.log","out")),"closed arm directory")
            for name in ("stdout.log","stderr.log"):
                log=path(directory/name);require(log.is_file() and log.stat().st_size<=8<<20,"bounded child capture")
            equal(doc(directory/"startup.json",8192),receipt(ident,p,a,old.hashed(intent),expected_images(ident,config)),"graded startup")
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
        equal(sorted(p.name for p in output.iterdir()),sorted(["grading-intent.json"]+[f"{i}-{p}-{a}" for i,(p,a) in enumerate(check.ARMS)]),"closed campaign output")
        live();require(time.monotonic()<=deadline,"campaign deadline")
        exclusive(output/"result.json",dict(schema="staged-weighted-mlp-result-v1",status="accepted",claim_sha256=claim_hash,identity=ident,reference=REFERENCE,coverage=coverage,evidence=manifest))
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
            rb"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*staged-weighted-mlp-grant\b[^\n]*$", markdown
        )
    )
    require(
        len(openers) == 1 and openers[0][0] == b"```staged-weighted-mlp-grant",
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
