"""Physical, pre-payload controls for the released candidate's Darwin image policy."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio017_guard import digest, doc, put, sha
import studio017_supervise as sup
from studio017_supervise import native_image_policy

LIBRARY_NAMES = ("libmlx.dylib", "libmlxc.dylib", "libjaccl.dylib")


def exercise_owner(binary, library_prefix, pins, policy_file, runtime_files, profile, directory):
    """Bind actual inherited stdout on this binary; all stage metadata below is local fixture data."""
    directory.mkdir(mode=0o700)
    op = uuid.uuid4().hex
    dummy_run = uuid.uuid4().hex * 2
    repo = Path(__file__).resolve().parents[2]
    src = sup.source(repo)
    stage = dict(program=str(binary), library_prefix=str(library_prefix))
    python = doc(policy_file)
    row = dict(path=str(policy_file), sha256=digest(policy_file))
    config = dict(source=src, run=dummy_run, stages={'native': stage, 'reference': {'python': python['interpreter']}},
                  artifacts={'python-policy': row}, runtime_files=runtime_files)
    cap = directory/'child-cap.json'
    put(cap, dict(schema='synthetic-owner-census-control/1', stage='native', expected_image=str(binary),
                  python_gate=dict(interpreter=python['interpreter'], policy=str(policy_file), sha256=row['sha256']),
                  native_image_policy=pins, native_image_source={k:src[k] for k in ('head','tree')},
                  operation=op, run=dummy_run, supervisor=os.getpid()))
    identity = directory/'fixture-identity.json'
    put(identity, dict(schema='synthetic-owner-census-control/1', stage='native', operation=op, run=dummy_run,
                       supervisor=os.getpid(), source=src['head'], cap_sha256=digest(cap)))
    bindings = dict(operation=op, claim_sha256=digest(identity), cap_sha256=digest(cap))
    args = ['/usr/bin/sandbox-exec', '-f', str(profile), str(binary), '--synthetic-image-observations',
            str(profile.parent/'positive.json'), op]
    put(directory/'intent.json', dict(operation=op, argv=args, synthetic_only=True, source=src))
    stdout = directory/'stdout'
    with os.fdopen(os.open(stdout, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600), 'wb') as out, (directory/'stderr').open('xb') as err:
        st = os.fstat(out.fileno())
        inode = [st.st_dev, st.st_ino]
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=directory,
                                   env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}, start_new_session=True)
        try:
            put(directory/'active.json', dict(**bindings, supervisor=os.getpid(), child=process.pid, native_stdout_inode=inode))
            rc = process.wait(30)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(5)
    put(directory/'numeric-exit.json', dict(operation=op, claim_sha256=digest(identity), pid=process.pid, exit=rc,
        child_admitted=True, completed=rc==0, clean_reap=True, residual_group_killed=False, fixture=True))
    if rc != 0:
        raise ValueError('synthetic native observation child refused')
    put(directory/'admitted.json',dict(**bindings, stage='native', worker=process.pid, fixture=True))
    seal = sup.owner_native_images(config, directory, identity)
    if seal['stdout_sha256'] != digest(stdout) or set(seal['observations']) != {'before','after'}:
        raise ValueError('native owner failed to bind original observations')
    put(directory/'synthetic-seal.json', seal)
    if doc(directory/'synthetic-seal.json') != sup.owner_native_images(config, directory, identity):
        raise ValueError('cannot reproduce owner census seal')

    observations = [sup.parse(line) for line in stdout.read_bytes().splitlines()]
    before, after = observations
    mutated_hashes = {**pins['noncache_images'],str(binary):'0'*64}
    bad_after = {**after,'census':{**after['census'],'noncache_images':mutated_hashes}}
    shared = sorted(after['census']['shared_cache_images'] + ['/System/Library/Studio017SyntheticMissing.dylib'])
    bad_cache = {**after, 'census': {**after['census'], 'shared_cache_images': shared}}
    scope_error = {**after,'phase':'before'}
    trials = {'absent': [], 'no-after':[before], 'extra':[before,after,after], 'reversed':[after,before],
              'changed-image':[before,bad_after], 'unknown-shared-image':[before,bad_cache], 'wrong-role-order':[before,scope_error],
              'wrong-pid':[before,{**after,'pid':process.pid+1}],
              'stale-operation':[before,{**after,'operation':uuid.uuid4().hex}]}
    refusals = {}
    for label, records in trials.items():
        candidate = directory/(label+'.synthetic')
        with os.fdopen(os.open(candidate,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as f:
            for record in records:
                f.write(sup.enc(record))
        st = candidate.stat()
        try:
            sup.checked_observations(candidate,[st.st_dev,st.st_ino],pins,op,process.pid)
        except ValueError as error:
            refusals[label] = str(error)
        else:
            raise ValueError('owner accepted negative control '+label)
    try:
        sup.owner_native_images({**config,'source':{**src,'tree':'0'*40}},directory,identity)
    except ValueError as error:
        refusals['wrong-tree'] = str(error)
    else:
        raise ValueError('owner accepted observations from wrong source tree')
    put(directory/'result.json', dict(operation=op, pid=process.pid, source=src,
        seal_sha256=digest(directory/'synthetic-seal.json'), refusals=refusals, elapsed_scope='two loader samples around no model work'))


def run(binary, build_hash, python_policy, runtime, output):
    if binary.resolve(strict=True) != binary or binary.name != "qualify-full-flash":
        raise ValueError("expected canonical Cargo binary")
    if digest(binary) != build_hash:
        raise ValueError("original Cargo executable digest mismatch")
    output.mkdir(mode=0o700)
    rows = doc(runtime)
    paths = {Path(row["path"]): row["sha256"] for row in rows.values()}
    libs = [p for p in paths if p.name in LIBRARY_NAMES]
    if len(libs) != 3 or len({p.parent for p in libs}) != 1:
        raise ValueError("original installed library population")
    for path in libs:
        if digest(path) != paths[path]:
            raise ValueError("installed library drift")
    policy = doc(python_policy)
    runtime_files = {**rows, "current_cargo_binary": {"path": str(binary), "sha256": build_hash}}
    pins = native_image_policy({"runtime_files": runtime_files},
                               {"program": str(binary), "library_prefix": str(libs[0].parent.parent)},
                               policy)
    hashes = dict(pins["noncache_images"])
    # Keep four expectations and the correct current executable. Removing the actual executable
    # from the allowed images must be detected by its header address, although its name
    # contains neither 'mlx' nor '.dylib'. This control loads no additional code.
    hashes[str(output/"unused-neutral-image")] = hashes.pop(str(binary))
    policies = {"positive": pins, "unknown-executable": {**pins, "noncache_images": hashes}}
    for key, value in policies.items():
        put(output/(key+".json"), value)
    spec = output/"profile.sb"
    files = [binary, *libs, *(output/(key+".json") for key in policies)]
    dirs = [Path("/System/Library"), Path("/usr/lib"), Path("/Library/Apple"), Path("/private/var/db/dyld"), Path("/dev")]
    ancestors = {a for p in files + dirs for a in p.parents}
    allow = ["(literal "+json.dumps(str(p))+")" for p in sorted(set(files) | ancestors)]
    allow.extend("(subpath "+json.dumps(str(p))+")" for p in dirs)
    spec.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-read*)\n'
                    '(deny file-write*)\n(allow file-read-metadata)\n(import "dyld-support.sb")\n'
                    '(allow file-read* '+" ".join(allow)+')\n')
    spec.chmod(0o400)
    op = str(uuid.uuid4())
    put(output/"intent.json", dict(operation=op, binary=str(binary), binary_sha256=build_hash,
                                 python_policy_sha256=digest(python_policy), runtime_sha256=digest(runtime),
                                 profile_sha256=digest(spec),
                                 policies={key:digest(output/(key+".json")) for key in policies}))
    for key in policies:
        argv = ["/usr/bin/sandbox-exec", "-f", str(spec), str(binary),
                "--synthetic-image-census", str(output/(key+".json"))]
        with (output/(key+".stdout")).open("xb") as out, (output/(key+".stderr")).open("xb") as err:
            proc = subprocess.Popen(argv, cwd=output, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                    env={"PATH":"/usr/bin:/bin","LC_ALL":"C","LANG":"C"}, start_new_session=True)
            try:
                code = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                raise
        stdout = (output/(key+".stdout")).read_bytes()
        stderr = (output/(key+".stderr")).read_bytes()
        put(output/(key+".exit.json"), dict(operation=op, pid=proc.pid, exit=code, argv=argv,
                                          stdout_sha256=sha(stdout), stderr_sha256=sha(stderr)))
        if key == "positive":
            if code != 0:
                raise ValueError("native census refused the pinned images")
            receipt = json.loads(stdout)
            if (receipt["schema"] != "studio017-native-images/1"
                or receipt["shared_cache_uuid"] != pins["platform_cache_uuid"]
                or not 0 < receipt["shared_cache_bytes"] < 64<<30
                or not receipt["shared_cache_images"]
                or receipt["noncache_images"] != pins["noncache_images"]):
                raise ValueError("native census did not match prospectively pinned images")
        elif code != 1 or stdout or stderr.strip() != ("cold forward refused: unapproved non-cache image "+str(binary)).encode():
            raise ValueError("missing refusal for unapproved executable outside shared cache")
    exercise_owner(binary, libs[0].parent.parent, pins, python_policy, runtime_files, spec, output/'owner')
    put(output/"result.json", dict(operation=op, controls=2, passed=2, owner_result_sha256=digest(output/'owner/result.json'),
                                 pre_payload_census_only=True, stage_claims_consumed=0))


if __name__ == "__main__":
    binary, build_hash, policy, runtime, output = sys.argv[1:]
    run(Path(binary), build_hash, Path(policy), Path(runtime), Path(output))
