"""Complete portable text/byte parts, verified without executing archived code."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,stat
PART_CAP=512*1024
BODY_CAP=16*1024**2
TOTAL_CAP=64*1024**2
class ArchiveError(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()

# Only the three path operands in this runner's recorded prefix may change.
# Scientific inputs, receipts, observations and source text are never rewritten.
REDACTION_FIELDS = (('argv', 0), ('argv', 3), ('argv', 5))
HOME_LOCATOR = re.compile(r'(?:/(?:Users|home)/[^/\s\x00"\'\\]+|[A-Za-z]:\\Users\\[^\\\s\x00"\']+)', re.IGNORECASE)

def redaction_plan(roots):
    """Validate explicitly supplied lexical roots; never inspect the host."""
    admitted = []
    for original, role in roots:
        if (type(original) is not str or type(role) is not str
                or not original.startswith('/') or len(PurePosixPath(original).parts) < 3
                or str(PurePosixPath(original)) != original or '..' in PurePosixPath(original).parts
                or any(c in original for c in ('\x00', '\n', '\r', '\\'))
                or re.fullmatch(r'role:[a-z][a-z0-9-]{0,63}', role) is None):
            raise ArchiveError('ARCHIVE_REDACTION_POLICY')
        if any(original == old for old, _ in admitted):
            raise ArchiveError('ARCHIVE_REDACTION_DUPLICATE_ROOT')
        admitted.append((original, role))
    return tuple(sorted(admitted, key=lambda pair: (-len(pair[0]), pair[0])))

def portable_body(name, original, roots=()):
    """Fail closed on undeclared locators; preserve raw bytes when unchanged.

    A changed prefix is a separately hashed JSON serialization. Root values are
    caller-supplied data, not discovered from HOME, credentials or directories.
    This policy detects named roots and ordinary home locators, not every secret.
    """
    roots = redaction_plan(roots)
    text = original.decode('utf-8')
    def private(value):
        return HOME_LOCATOR.search(value) is not None or any(old in value for old, _ in roots)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ArchiveError('ARCHIVE_REDACTION_DUPLICATE_KEY')
            value[key] = item
        return value
    def inspect(item):
        if isinstance(item, str) and private(item):
            raise ArchiveError('ARCHIVE_UNDECLARED_PRIVATE_LOCATOR')
        if isinstance(item, dict):
            for key, child in item.items():
                inspect(key)
                inspect(child)
        elif isinstance(item, list):
            for child in item:
                inspect(child)
    if name != 'producer/prefix.json':
        inspect(text)
        # Inspect JSON escapes without reserializing scientific evidence. The
        # stdout stream can mix JSON records with ordinary diagnostic lines.
        candidates = [text] if name.endswith('.json') else [text, *text.splitlines()]
        for candidate in candidates:
            try:
                value = json.loads(candidate, object_pairs_hook=unique)
            except json.JSONDecodeError:
                continue
            inspect(value)
        return original, []
    value = json.loads(text, object_pairs_hook=unique)
    changes = []
    def walk(item, path=()):
        if isinstance(item, dict):
            if any(private(key) for key in item):
                raise ArchiveError('ARCHIVE_UNDECLARED_PRIVATE_LOCATOR')
            return {key: walk(child, path + (key,)) for key, child in item.items()}
        if isinstance(item, list):
            return [walk(child, path + (i,)) for i, child in enumerate(item)]
        if isinstance(item, str):
            result = item
            if path in REDACTION_FIELDS:
                for old, role in roots:
                    if item == old or item.startswith(old + '/'):
                        result = role + item[len(old):]
                        break
            if private(result):
                raise ArchiveError('ARCHIVE_UNDECLARED_PRIVATE_LOCATOR')
            if result != item:
                changes.append({'field': list(path), 'original_value_sha256': sha(item.encode()),
                                'portable_value_sha256': sha(result.encode())})
            return result
        return item
    transformed = walk(value)
    body = (json.dumps(transformed, indent=2, allow_nan=False) + '\n').encode() if changes else original
    return body, changes

def bounded_read(path,cap):
    if path.resolve()!=path:raise ArchiveError('ARCHIVE_PATH_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>cap:raise ArchiveError('ARCHIVE_READ_SIZE_TYPE')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(cap+1)
        after=os.fstat(fd)
        if len(raw)!=before.st_size or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ArchiveError('ARCHIVE_READ_DRIFT')
        return raw
    finally:os.close(fd)
def safe_name(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not name or '\\' in name:raise ArchiveError('ARCHIVE_PATH')
    return p
def check_part(raw,record):
    if len(raw)!=record['bytes'] or len(raw)>PART_CAP or sha(raw)!=record['sha256']:raise ArchiveError('ARCHIVE_PART_DIGEST_SIZE')
def verify_archive(root,expected_manifest=None):
    root=Path(root).absolute()
    if root.resolve()!=root:raise ArchiveError('ARCHIVE_ROOT_SYMLINK')
    path=root/'manifest.json';raw=bounded_read(path,1024**2)
    if len(raw)>1024**2 or (expected_manifest is not None and sha(raw)!=expected_manifest):raise ArchiveError('ARCHIVE_MANIFEST_DIGEST_SIZE')
    m=json.loads(raw);bodies={};total=0
    if m['schema']!='router-caller-portable-parts-v1' or len(m['files'])>256:raise ArchiveError('ARCHIVE_SCHEMA')
    for row in m['files']:
        name=row['path'];safe_name(name)
        if name in bodies or row['bytes']>BODY_CAP:raise ArchiveError('ARCHIVE_BODY_LIMIT')
        parts=[]
        for part in row['parts']:
            safe_name(part['path']);p=root/part['path']
            if p.resolve()!=p or not p.is_relative_to(root):raise ArchiveError('ARCHIVE_PART_PATH')
            b=bounded_read(p,PART_CAP);check_part(b,part);parts.append(b)
        body=b''.join(parts);total+=len(body)
        if len(body)!=row['bytes'] or sha(body)!=row['sha256'] or total>TOTAL_CAP:raise ArchiveError('ARCHIVE_BODY_DIGEST_SIZE')
        bodies[name]=body
    receipt=json.loads(bodies['producer/receipt.json']);prefix=json.loads(bodies['producer/prefix.json'])
    events=[json.loads(line) for line in bodies['producer/stdout.txt'].decode().splitlines() if line.startswith('{')]
    result=[e for e in events if e.get('event')=='result'][-1]
    if receipt['status']!='PASS' or result['status']!='PASS' or not receipt['termination']['stop_confirmed']:raise ArchiveError('ARCHIVE_PRODUCER_NOT_PASS')
    if receipt['input_manifest_sha256']!=m['generation'] or prefix['ticket']['input_digest']!=m['generation']:raise ArchiveError('ARCHIVE_GENERATION_MISMATCH')
    checkpoint=json.loads(bodies['producer/checkpoint.json'])
    if checkpoint['generation']!=m['generation'] or checkpoint['files']!=prefix['source_inputs']:raise ArchiveError('ARCHIVE_CHECKPOINT_MISMATCH')
    # Every original checkpoint input is present, with its source identity and
    # any portable role substitution distinguished from that original identity.
    listed={r['path']:r for r in m['files']}
    for stream in ('stdout','stderr'):
        if listed['producer/'+stream+'.txt']['original_sha256']!=receipt['outputs'][stream]['sha256']:raise ArchiveError('ARCHIVE_PRODUCER_OUTPUT_BINDING')
    if sha(json.dumps(prefix['source_inputs'],sort_keys=True,separators=(',',':')).encode())!=m['generation']:raise ArchiveError('ARCHIVE_INPUT_MANIFEST_DIGEST')
    for row in prefix['source_inputs']:
        entry=listed['inputs/'+row['path']]
        if entry['original_sha256']!=row['sha256']:raise ArchiveError('ARCHIVE_INPUT_IDENTITY_MISMATCH')
    return {'manifest_sha256':sha(raw),'logical_files':len(bodies),'logical_bytes':total,'parts_verified':sum(len(r['parts']) for r in m['files']),'producer_run':receipt['run'],'generation':m['generation'],'source_code_executed':False,'numerical_backend_imported':False,'scope':'portable evidence readback; existing hash-locked runtime bodies remain separately retained, not a standalone runtime installation'}
def pack_run(phase,run_name,target,*,redaction_roots=()):
    import rc_guard as guard
    phase=guard.admit_phase(phase);root=phase.parent;run=phase/'runs'/run_name;target=guard.confined(phase,target)
    if target.exists():raise ArchiveError('ARCHIVE_ALREADY_EXISTS')
    prefix=json.loads((run/'prefix.json').read_text());receipt=json.loads((run/'receipt.json').read_text())
    if receipt['status']!='PASS':raise ArchiveError('ARCHIVE_PRODUCER_NOT_PASS')
    inputs=[('producer/'+name,run/name) for name in ('prefix.json','receipt.json','stdout.txt','stderr.txt')]
    inputs.append(('producer/checkpoint.json',phase/'evidence/checkpoints'/(receipt['input_manifest_sha256']+'.json')))
    inputs.extend(('inputs/'+row['path'],guard.resolve_input(row)) for row in prefix['source_inputs'])
    roots=redaction_plan(((str(root),'role:flash-workspace'),*redaction_roots))
    policy={'schema':'router-prefix-path-redaction-v1','artifact':'producer/prefix.json',
            'permitted_fields':[list(p) for p in REDACTION_FIELDS],
            'roots':[{'original_root_sha256':sha(old.encode()),'role':role} for old,role in roots],
            'other_fields':'unchanged; unhandled private locators refused'}
    target.mkdir();(target/'parts').mkdir();files=[]
    for name,path in inputs:
        original=path.read_bytes()
        if len(original)>BODY_CAP:raise ArchiveError('ARCHIVE_BODY_LIMIT')
        body,changes=portable_body(name,original,roots);parts=[]
        for offset in range(0,len(body),PART_CAP):
            chunk=body[offset:offset+PART_CAP];rel='parts/'+sha(chunk)+'.part';dest=target/rel
            if dest.exists() and dest.read_bytes()!=chunk:raise ArchiveError('ARCHIVE_PART_COLLISION')
            dest.write_bytes(chunk);parts.append({'path':rel,'bytes':len(chunk),'sha256':sha(chunk)})
        files.append({'path':name,'original_bytes':len(original),'original_sha256':sha(original),'bytes':len(body),'sha256':sha(body),'portable_role_substitution':body!=original,'transformations':changes,'parts':parts})
    manifest={'schema':'router-caller-portable-parts-v1','producer_run':run_name,'generation':receipt['input_manifest_sha256'],'part_cap':PART_CAP,'files':files,'redaction_policy':policy,'raw_originals':'retained externally; separately hashed derivatives only; no source or scientific field rewriting'}
    raw=(json.dumps(manifest,indent=2)+'\n').encode();(target/'manifest.json').write_bytes(raw)
    (target/'manifest.json.sha256').write_text(sha(raw)+'  manifest.json\n')
    return verify_archive(target,sha(raw))
