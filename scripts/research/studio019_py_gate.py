"""Studio019 native-only isolated CPython execution gate. No checkpoint access or computational entry outside a bound stage."""
import _imp
import ctypes
import hashlib
import importlib.machinery as M
import json
import os
import stat
import sys
from pathlib import Path

SELF=Path(__file__).resolve()
TASK="studio019-route-b-native-diagnostic"
LIMIT=1<<27
KINDS=(".py",".pyw",".pyc",".pth",".so",".dylib",".zip",".egg")
def need(ok, why):
    if not ok: raise ValueError("Python runtime admission: "+why)
def wire(x):
    return (json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def h(b):
    return hashlib.sha256(b).hexdigest()
def stamp(s):
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def real(p):
    p=Path(p);need(p.is_absolute() and p.resolve(strict=True)==p,"noncanonical "+str(p));return p
def raw(p,cap=LIMIT):
    p=real(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as f:
        before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_size<=cap,"nonordinary/large "+str(p))
        b=f.read(before.st_size+1)
        need(len(b)==before.st_size and stamp(before)==stamp(os.fstat(fd))==stamp(p.lstat()),"changed "+str(p))
        return b
def put(p,obj):
    p=Path(p);real(p.parent)
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as f:
        f.write(wire(obj));f.flush();os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
def fresh_cache(p):
    p=Path(p);real(p.parent);p.mkdir(0o700);p.chmod(0o500);os.chflags(p,stat.UF_IMMUTABLE,follow_symlinks=False)
    cache(p)
def cache(p):
    p=real(p);s=p.lstat()
    need(stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode)==0o500 and s.st_uid==os.getuid() and s.st_flags&stat.UF_IMMUTABLE and not list(p.iterdir()),"cache not fresh, empty, private and immutable")
def layout(std,np,src):
    std,np,src=map(real,(std,np,src));dyn=real(std/"lib-dynload")
    need((np/"numpy/__init__.py").is_file() and (std/"encodings/__init__.py").is_file() and (src/SELF.name).is_file(),"incorrect import roots")
    return list(map(str,(std,dyn,np,src)))
def inventory(roots):
    files={};items=[];nbytes=0
    for group,root in enumerate(map(real,(roots[0],roots[2],roots[3]))):
        def walkfail(e):raise e
        for base,dirs,names in os.walk(root,followlinks=False,onerror=walkfail):
            base=Path(base);keep=[]
            for n in sorted(dirs):
                p=base/n
                if p.is_symlink():items.append([group,str(p.relative_to(root)),"link",os.readlink(p)])
                else:items.append([group,str(p.relative_to(root)),"dir"]);keep.append(n)
            dirs[:]=keep
            for n in sorted(names):
                p=base/n
                if not (n.endswith(KINDS) or ".so." in n):continue
                rel=str(p.relative_to(root))
                if p.is_symlink():
                    items.append([group,rel,"link",os.readlink(p)]);continue
                b=raw(p);nbytes+=len(b)
                need(len(items)<16000 and nbytes<=512<<20,"import tree bounds")
                sh=h(b);items.append([group,rel,"file",sh])
                if n.endswith((".py",".so")) and (group!=2 or (base==root and n.startswith(("studio017_","studio019_")))):files[str(p)]=sh
    return h(wire(sorted(items))),files
def dyld():
    lib=ctypes.CDLL(None);count=lib._dyld_image_count;count.restype=ctypes.c_uint32
    name=lib._dyld_get_image_name;name.argtypes=[ctypes.c_uint32];name.restype=ctypes.c_char_p
    header=lib._dyld_get_image_header;header.argtypes=[ctypes.c_uint32];header.restype=ctypes.c_void_p
    size=ctypes.c_size_t();ran=lib._dyld_get_shared_cache_range;ran.argtypes=[ctypes.POINTER(ctypes.c_size_t)];ran.restype=ctypes.c_void_p
    start=ran(ctypes.byref(size));u=(ctypes.c_ubyte*16)();uuid=lib._dyld_get_shared_cache_uuid;uuid.argtypes=[ctypes.POINTER(ctypes.c_ubyte)];uuid.restype=ctypes.c_bool
    need(uuid(u) and start and 0<size.value<64<<30,"missing Darwin shared cache identity")
    n=count();need(0<n<4096,"dyld count");system=[];ext={}
    for i in range(n):
        addr=header(i);nm=name(i);need(addr and nm,"dyld entry");nm=os.fsdecode(nm)
        if start<=addr<start+size.value:system.append(nm)
        else:
            p=Path(nm).resolve(strict=True);ext[str(p)]=h(raw(p))
    need(count()==n,"dyld census changed")
    return bytes(u).hex(),sorted(system),ext
def source_identity(source):
    need(isinstance(source,dict) and set(source)=={"head","tree"} and
         all(isinstance(v,str) and len(v)==40 and all(c in "0123456789abcdef" for c in v) for v in source.values()),"source identity")
    return source

def build_policy(std,np,src,interpreter,pinned,source):
    """Create once *prospectively*: caller holds clean source, pinned host install, original runtime manifest."""
    roots=layout(std,np,src);tree,modules=inventory(roots);images={}
    for row in pinned.values():
        p=real(row["path"]);n=p.name
        if n.endswith((".so",".dylib")) or ".so." in n or n=="Python" or p==real(interpreter):
            sh=h(raw(p));need(row["sha256"]==sh,"original runtime artifact drift");images[str(p)]=sh
    system=real("/usr/lib/libffi-trampolines.dylib");need(system.lstat().st_uid==0 and not system.lstat().st_mode&0o022,"Darwin libffi custody")
    images[str(system)]=h(raw(system))
    images.update({p:d for p,d in modules.items() if p.endswith(".so")})
    policy=dict(schema="studio019-python-policy/1",task=TASK,source=source_identity(source),roots=roots,inventory_sha256=tree,modules=modules,images=images,
                interpreter=str(real(interpreter)),platform_cache_uuid=dyld()[0],flags=["-I","-B","-S","-X","pycache_prefix"])
    validate(policy,True);return policy
def validate(p,full=False):
    need(set(p)=={"schema","task","source","roots","inventory_sha256","modules","images","interpreter","platform_cache_uuid","flags"} and p["schema"]=="studio019-python-policy/1" and p["task"]==TASK,"policy schema")
    source_identity(p["source"])
    roots=p["roots"];need(len(roots)==4 and roots==layout(roots[0],roots[2],roots[3]),"import layout")
    need(str(Path(sys.executable).resolve(strict=True))==p["interpreter"],"approved interpreter")
    if full:
        tree,mods=inventory(roots)
        need(tree==p["inventory_sha256"] and mods==p["modules"],"changed import population (.pyc/.pth/module shadow)")
        for name,sha in p["images"].items():need(h(raw(name))==sha,"changed image "+name)
def source_bytes(name,policy):
    b=raw(name);need(h(b)==policy["modules"].get(str(name)),"unapproved module "+str(name));return b
def flags(c):
    cache(c);need(sys.flags.isolated and sys.flags.dont_write_bytecode and sys.flags.no_site and sys.flags.no_user_site and sys.flags.ignore_environment and sys.flags.safe_path and sys.flags.optimize==0 and sys.pycache_prefix==str(c),"interpreter flags / cache prefix")
def install(p):
    roots=p["roots"];std=Path(roots[0])
    # -S prevents executable .pth and customizations before this gate. CPython prepends a default absent zip path.
    zipfile=std.parent/("python%d%d.zip"%sys.version_info[:2])
    need(not os.path.lexists(zipfile) and sys.path==[str(zipfile),*roots[:2]],"unexpected startup search path")
    sys.path[:]=roots
    class CheckedSource(M.SourceFileLoader):
        def get_code(self,fullname):return compile(source_bytes(self.path,p),self.path,"exec",dont_inherit=True,optimize=0)
    class Finder:
        @staticmethod
        def find_spec(fullname,path=None,target=None):
            need(fullname not in ("sitecustomize","usercustomize"),"startup customization "+fullname)
            spec=M.PathFinder.find_spec(fullname,path,target)
            if spec is None:return None
            need(spec.origin and str(real(spec.origin)) in p["modules"],"unapproved origin "+fullname)
            cp=Path(spec.origin)
            if cp.is_relative_to(roots[2]):need(fullname.split(".")[0]=="numpy","shadow in array root "+fullname)
            if cp.is_relative_to(roots[3]):need(fullname.startswith(("studio017_","studio019_")) and cp.parent==Path(roots[3]),"shadow in task source "+fullname)
            if isinstance(spec.loader,M.SourceFileLoader):spec.loader=CheckedSource(fullname,spec.origin)
            else:
                need(isinstance(spec.loader,M.ExtensionFileLoader) and h(raw(spec.origin))==p["images"].get(spec.origin),"unapproved loader "+fullname)
            return spec
    sys.meta_path[:]=[M.BuiltinImporter,M.FrozenImporter,Finder]
    return Finder
def snapshot(p):
    u,system,images=dyld();need(u==p["platform_cache_uuid"],"platform image set changed")
    for k,v in images.items():need(p["images"].get(k)==v,"unlisted/changed dyld image "+k)
    mods={};special={};seen={}
    for k,m in list(sys.modules.items()):
        spec=getattr(m,"__spec__",None);orig=getattr(spec,"origin",None);n=getattr(spec,"name",k)
        if orig=="built-in" and _imp.is_builtin(n):special[k]=["built-in",n];continue
        if orig=="frozen" and _imp.is_frozen(n):special[k]=["frozen",n];continue
        if k=="__main__" and orig is None:orig=str(SELF)
        need(isinstance(orig,str) and Path(orig).is_absolute(),"unknown loaded origin "+k+" "+str(orig))
        cp=str(real(orig));src=getattr(m,"__file__",None)
        need(src==cp and cp in p["modules"],"unapproved loaded origin "+k)
        if cp not in seen:seen[cp]=h(raw(cp))
        need(seen[cp]==p["modules"][cp],"loaded origin drift "+k);mods[k]=[cp,seen[cp]]
    need(not ({"sitecustomize","usercustomize"}&mods.keys()),"site customization")
    return dict(module_origins=mods,builtin_or_frozen=special,noncache_images=images,shared_cache_uuid=u,shared_cache_images=system)
def binding(spec,sha):
    b=raw(spec,4<<20);need(h(b)==sha,"policy digest");return json.loads(b)
def rolepath(d,role):
    need(role in ("bootstrap","helper","grade","control","lease-numeric","lease-grade","fixture-bootstrap","fixture-worker","fixture-helper"),"role name")
    return Path(d)/("python-"+role+".json")
def cli(interpreter,cache_dir,gate,role,policy,sha,receipt,operation,args):
    return [str(interpreter),"-I","-B","-S","-X","pycache_prefix="+str(cache_dir),str(gate),role,str(policy),sha,str(receipt),operation,*map(str,args)]
def stage_binding(role,spec,sha,receipt,op,av):
    need(role not in ("reference","eligibility"),"reference execution forbidden")
    if role not in ("helper","bootstrap","fixture-bootstrap","fixture-worker","fixture-helper"):
        return None
    import pwd
    basedir=Path(pwd.getpwuid(os.getuid()).pw_dir)/"LocalWorktrees/PulsarMLX-studio019-state"
    need(len(av)==(2 if role in ("bootstrap","fixture-bootstrap") else 1),"stage arguments")
    cap=real(av[0]);d=cap.parent
    if role in ("helper","bootstrap"):
        need(cap==basedir/"campaign-native/child-cap.json" and Path(receipt)==rolepath(d,role),"fresh native stage binding")
    else:
        need(len(op)==32 and all(x in "0123456789abcdef" for x in op)
             and d==basedir/("synthetic-admission-"+op) and cap==d/"fixture-cap.json"
             and Path(receipt)==rolepath(d,role),"fresh synthetic role binding")
    need(Path(sys.pycache_prefix)==d/("cache-"+role),"stage cache binding")
    payload=json.loads(raw(cap))
    expected_schema="studio019-child-cap/1" if role in ("helper","bootstrap") else "studio019-fixture-cap/1"
    expected_stage="native" if role in ("helper","bootstrap") else "synthetic-ack"
    need(payload.get("schema")==expected_schema and payload.get("stage")==expected_stage
         and payload.get("task")==TASK and payload.get("operation")==op
         and payload.get("python_gate")==dict(policy=spec,sha256=sha,interpreter=str(Path(sys.executable).resolve(strict=True))),"issued Python capability mismatch")
    source_identity(payload.get("source"))
    return payload

def gate(args):
    role,spec,sha,receipt,op,*av=args
    need(op and len(op)<=128 and Path(receipt).name==rolepath(Path(receipt).parent,role).name,"original role binding")
    payload=stage_binding(role,spec,sha,receipt,op,av)
    c=real(sys.pycache_prefix);flags(c);p=binding(spec,sha);validate(p,True);need(str(SELF)==str(Path(p["roots"][3])/SELF.name),"entry not in approved source")
    if payload is not None:
        need(payload["task"]==p["task"] and payload["source"]==p["source"],"capability task/source policy mismatch")
    finder=install(p);snapshot(p)
    result=None;replace=None
    try:
        if role in ("helper","bootstrap"):
            import studio019_supervise as s
            if role=="helper":
                need(len(av)==1,"helper arguments");result=s.child(av[0])
            else:
                need(len(av)==2,"bootstrap arguments");replace=s.capsule_exec(av[0],int(av[1]))
        elif role in ("fixture-bootstrap","fixture-worker","fixture-helper"):
            import studio019_supervise as s
            result,replace=s.fixture_enter(role,av,op,spec,sha,receipt)
        elif role in ("lease-numeric","lease-grade"):
            from studio017_lease import watch
            need(len(av)==4,"watcher enrollment")
            watch(int(av[0]),int(av[1]),int(av[2]),float(av[3]))
        elif role=="grade":
            fd=int(os.environ["STUDIO017_GRADE_GATE"])
            try:need(fd>=3 and os.read(fd,1)==b'G',"no armed grade guardian")
            finally:os.close(fd)
            import studio019_grade as gr
            need(len(av)==2,"grader arguments")
            result=gr.grade_pair(*av)
        elif role=="control":
            need(av==["imports"],"control args")
            import numpy as np
            need(int(np.array([2,3])@np.array([4,5]))==23,"CPU synthetic")
        else:raise ValueError("invalid Python worker role")
        flags(c);need(sys.path==p["roots"] and sys.meta_path==[M.BuiltinImporter,M.FrozenImporter,finder],"search path changed")
        evidence=snapshot(p)
        put(receipt,dict(schema="studio017-python-observed/2",role=role,operation=op,pid=os.getpid(),parent=os.getppid(),
                         policy_sha256=sha,cache=str(c),status="closed",**evidence))
    except BaseException as e:
        if not os.path.lexists(receipt):
            put(receipt,dict(schema="studio017-python-refusal/2",role=role,operation=op,pid=os.getpid(),policy_sha256=sha,status="refused",error=type(e).__name__+": "+str(e)[:2048]))
        raise
    if replace is not None:os.execv(replace[0],replace)
    if result is not None:sys.stdout.buffer.write(wire(result))

def cap_cli(cap, putative_role):
    """Private process arguments from a sealed parent capability, not from argv or user environment."""
    need(putative_role in ("helper","bootstrap"),"capability role")
    cp=real(cap);v=json.loads(raw(cp));b=v["python_gate"]
    return cli(b["interpreter"],cp.parent/("cache-"+putative_role),SELF,putative_role,b["policy"],b["sha256"],rolepath(cp.parent,putative_role),v["operation"],
               [str(cp)] if putative_role=="helper" else [str(cp),v["output"]])
def checked_receipt(d,role,op,pid,sha,p,ppid=None):
    rp=rolepath(real(d),role);s=rp.lstat()
    need(stat.S_IMODE(s.st_mode)==0o400 and s.st_uid==os.getuid() and s.st_nlink==1,"unsealed Python receipt")
    b=raw(rp,4<<20);r=json.loads(b)
    need(r.get("schema")=="studio017-python-observed/2" and r["status"]=="closed" and r["role"]==role and r["operation"]==op and r["pid"]==pid and (ppid is None or r["parent"]==ppid) and r["policy_sha256"]==sha and r["cache"]==str(real(d)/("cache-"+role)),"wrong observed Python process or policy")
    cache(r["cache"])
    need(r["shared_cache_uuid"]==p["platform_cache_uuid"] and r["shared_cache_images"] and r["noncache_images"] and all(p["images"].get(n)==v for n,v in r["noncache_images"].items()),"observed image mismatch")
    mm=r["module_origins"];need("__main__" in mm and all(p["modules"].get(n)==v for n,v in mm.values()) and r["builtin_or_frozen"],"observed module mismatch")
    if role in ("bootstrap","helper","fixture-bootstrap","fixture-worker","fixture-helper"):
        origin=str(Path(p["roots"][3])/"studio017_authority.py")
        need(origin in p["modules"] and mm.get("studio017_authority")==[origin,p["modules"][origin]],"authority module missing from actual child")
    if role in ("reference","eligibility","grade","control"):
        need("numpy" in mm and any("openblas" in n.lower() for n in r["noncache_images"]),"missing observed NumPy/BLAS")
    return h(b)
if __name__=="__main__":gate(sys.argv[1:])
