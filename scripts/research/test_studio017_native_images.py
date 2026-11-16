"""Physical, pre-payload controls for the released candidate's Darwin image policy."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio017_guard import digest, doc, put, sha
from studio017_supervise import native_image_policy

LIBRARY_NAMES = ("libmlx.dylib", "libmlxc.dylib", "libjaccl.dylib")


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
    put(output/"result.json", dict(operation=op, controls=2, passed=2,
                                 pre_payload_census_only=True, stage_claims_consumed=0))


if __name__ == "__main__":
    binary, build_hash, policy, runtime, output = sys.argv[1:]
    run(Path(binary), build_hash, Path(policy), Path(runtime), Path(output))
