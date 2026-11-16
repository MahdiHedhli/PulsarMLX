"""Host synthetic fixture setup. Zero real inputs; this file is outside the stage import allowlist."""
import hashlib,json,os,sys
from pathlib import Path
def cfg(c,p):
    import studio017_py_gate as g
    src=Path(__file__).resolve().parent
    f=os.environ.get('STUDIO017_CONTROL_POLICY')
    if f:
        row=Path(f).resolve(strict=True);pb=g.binding(row,g.h(g.raw(row)));g.validate(pb,True)
    else:
        # Only small fixture controls; no authority or claim. Actual numerical CONFIG requires external review/grant.
        import numpy as np
        import studio017_supervise
        nn=Path(np.__file__).resolve().parent.parent
        exe=Path(sys.executable).resolve(strict=True)
        images=g.dyld()[2]
        pins={k:dict(path=n,sha256=v) for k,(n,v) in enumerate(images.items())}
        pb=g.build_policy(Path(os.__file__).resolve().parent,nn,src,exe,pins)
        row=p/'fixture-runtime-policy.json';g.put(row,pb)
    c=dict(c,artifacts={'python-policy':{'path':str(row),'sha256':g.h(g.raw(row))}})
    if 'reference' not in c['stages']:c['stages']=dict(c['stages'],reference=c['stages']['native'])
    return c
