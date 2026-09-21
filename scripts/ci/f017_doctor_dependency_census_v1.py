"""Read-only installed NumPy Mach-O dependency census; no dynamic loading."""
import hashlib,os,pathlib,stat,struct
def need(v,m):
    if not v:raise ValueError(m)
def image(path):
    p=pathlib.Path(path).resolve(strict=True);before=p.stat();need(stat.S_ISREG(before.st_mode)and before.st_size<=256*1024**2,'DEPENDENCY_REGULAR_BOUND')
    h=hashlib.sha256()
    with p.open('rb')as f:
        while part:=f.read(1024*1024):h.update(part)
    after=p.stat();need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'DEPENDENCY_CHANGED')
    return dict(path=str(p),bytes=before.st_size,sha256=h.hexdigest(),device=before.st_dev,inode=before.st_ino)
def commands(path):
    with open(path,'rb')as f:
        raw=f.read(1024*1024)
        if raw[:4] in (b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf'):
            wide=raw[:4]==b'\xca\xfe\xba\xbf';count=struct.unpack_from('>I',raw,4)[0]
            need(0<count<=64,'FAT_ARCH_CENSUS');size=32 if wide else 20;arm=[]
            for i in range(count):
                at=8+i*size;cpu=struct.unpack_from('>I',raw,at)[0]
                offset,length=struct.unpack_from('>QQ'if wide else'>II',raw,at+8)
                if cpu==0x100000c:arm.append((offset,length))
            need(len(arm)==1 and arm[0][1]>=32,'ONE_ARM64_SLICE')
            f.seek(arm[0][0]);raw=f.read(min(1024*1024,arm[0][1]))
    need(raw[:4]==b'\xcf\xfa\xed\xfe','ARM64_THIN_MACHO_REQUIRED')
    header=struct.unpack_from('<8I',raw);need(header[1]==0x100000c and header[4]<=4096 and header[5]<len(raw),'BOUNDED_ARM64_COMMANDS')
    at=32;loads=[];rpaths=[]
    for _ in range(header[4]):
        cmd,size=struct.unpack_from('<II',raw,at);need(size>=8 and at+size<=len(raw),'MACHO_COMMAND_SIZE')
        if cmd in (0xc,0x80000018,0x8000001f,0x20,0x80000023,0x8000001c):
            offset=struct.unpack_from('<I',raw,at+8)[0];need(12<=offset<size,'MACHO_STRING_OFFSET')
            text=raw[at+offset:at+size].split(b'\0',1)[0].decode('utf-8')
            (rpaths if cmd==0x8000001c else loads).append(text)
        at+=size
    return loads,rpaths
def census(package):
    package=pathlib.Path(package).resolve(strict=True)
    initial=sorted(str(p.resolve(strict=True))for p in package.rglob('*.so'))
    need(0<len(initial)<=128,'NUMPY_EXTENSION_CENSUS')
    pending=[(p,[])for p in initial];seen={};edges=[];system=set();literal_paths=set(initial)
    while pending:
        path,inherited=pending.pop(0);real=str(pathlib.Path(path).resolve(strict=True))
        if real in seen:continue
        need(len(seen)<160,'DEPENDENCY_COUNT_BOUND');seen[real]=image(real)
        loads,rpaths=commands(real);parent=pathlib.Path(real).parent
        def local(v):return v.replace('@loader_path',str(parent))
        search=[local(p)for p in rpaths]+inherited
        for name in loads:
            if name.startswith(('/usr/lib/','/System/Library/')):system.add(name);continue
            candidates=[local(name)]if not name.startswith('@rpath/')else[str(pathlib.Path(p)/name[len('@rpath/'):])for p in search]
            existing=[pathlib.Path(p)for p in candidates if '@'not in p and pathlib.Path(p).is_file()]
            need(existing,'DEPENDENCY_UNAVAILABLE:'+name);chosen=existing[0];resolved=chosen.resolve(strict=True)
            need(resolved.suffix in ('.dylib','.so')and(str(resolved).startswith('/opt/homebrew/')or resolved.is_relative_to(package.parent)),'DEPENDENCY_LOCATION_SCOPE')
            literal_paths.update((str(chosen),str(resolved)));edges.append(dict(source=real,load_name=name,resolved=str(resolved)));pending.append((str(resolved),search))
    return dict(scope='FIXED_INSTALLED_NUMPY_RUNTIME_ONLY_NO_COMPILE',extensions=len(initial),images=[seen[k]for k in sorted(seen)],literal_paths=sorted(literal_paths),edges=edges,system_cache_dependencies=sorted(system),system_cache_image_bytes_independently_observed=False)
