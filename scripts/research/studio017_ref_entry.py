"""Independent reference entry; admission challenge completes before model descriptors open."""
import json,os,subprocess,sys
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parent
def require(v,why):
 if not v:raise ValueError(why)
def query_helper(command,fd):
 try:return json.loads(subprocess.check_output(command,pass_fds=(fd,),timeout=30))
 finally:os.close(fd)
def main(args):
 require(len(args)==2 and sys.flags.isolated,'private role/isolated interpreter')
 cap,out=map(Path,args);fd=int(os.environ['STUDIO017_ADMIT_CHANNEL'])
 from studio017_py_gate import cap_cli
 command=cap_cli(cap,'helper')
 role=query_helper(command,fd)
 require(role['stage']=='reference' and Path(role['output'])==out==out.resolve(strict=True),'reference admission')
 require(str(SCRIPTS) in sys.path,'approved source root')
 from studio017_guard import doc,opened,fdstamp,digest
 from studio017_ref_store import Store
 from studio017_ref_output import run_admitted_reference
 import contextlib
 manifest=doc(role['checkpoint_receipt']);require(manifest['all_shards_byte_verified'] is True and digest(role['inventory'])==manifest['inventory_sha256'] and digest(role['witnesses'])==manifest['witnesses_sha256'],'reference metadata bindings')
 inv=doc(role['inventory']);wit=doc(role['witnesses']);model=Path(role['model_root'])
 from studio017_text_config import validate_witnessed
 validate_witnessed(model/'config.json',wit['config.json'],opened,fdstamp)
 rows={k:(x['shard'],x['offset'],x['dtype'],tuple(x['shape'])) for k,x in inv.items() if k.startswith('language_model.')}
 require(len(rows)==2651 and len(wit)>=18,'whole text inventory')
 with contextlib.ExitStack() as stack:
  files={}
  for n in sorted({v[0] for v in rows.values()}):
   require('/' not in n and n in manifest['shards'],'canonical shard')
   f,st=stack.enter_context(opened(model/n,32<<30));require(fdstamp(st)==wit[n] and manifest['shards'][n]['checked_whole_sha256']==manifest['shards'][n]['publisher_lfs_sha256'],'bound shard')
   files[n]=f
  store=Store(files,rows,{n:tuple(wit[n]) for n in files})
  run_admitted_reference(store,out)
if __name__=='__main__':main(sys.argv[1:])
