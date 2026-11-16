"""Studio017 private preparation. No tensors are decoded, no numerical runtime is loaded.
Fresh private output required. Mode 'full' streams every pinned shard once. 'headers' cannot certify payloads."""
import argparse, collections, contextlib, hashlib, json, math, os, pathlib, re, secrets, stat, struct, sys, time, urllib.request

REV='d43ea8b407ce4e9c25e6ac9baec3feab70d9f5f3'
REPO='pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit'
ROOT=pathlib.Path.home()/'Models/PulsarMLX/GLM-5.3-Flash-MLX-mixed-4_8bit'
URL='https://huggingface.co/api/models/'+REPO+'/revision/'+REV+'?blobs=true'
PIN={'config.json':'3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d','model.safetensors.index.json':'5e0a3768db6fb795c4846bed713785a17d336f4cc4494b4f6b28f75082314383','tokenizer_config.json':'98b1271574f41abf89427ae2dda030d94dc9478f0edc5a8bd240db213c6fd5fc','generation_config.json':'230c30609ecbbb9e6583bedde8e7bdda0c6eb8fe5fad0eaeb3d1b293d751cb4f','chat_template.jinja':'34d5ee66b12fa6446cdae131c352b8f68cd85369e0e6fda115583805fada3891'}
SHARDS=['model-%05d.safetensors'%i for i in range(1,19)]
CAP=16*1024**2
CHUNK=4*1024**2
OFF_MAX=(1<<63)-1
def require(v,why):
 if not v:raise ValueError(why)
def pairs(p):
 d={}
 for k,v in p:
  require(k not in d,'duplicate key '+k);d[k]=v
 return d
def bad(_):raise ValueError('nonfinite JSON literal')
def parse(b):return json.loads(b.decode('utf8'),object_pairs_hook=pairs,parse_constant=bad)
def exact(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
def sha(x):return hashlib.sha256(x).hexdigest()
def put(path,b):
 with path.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def witness(q):return [q.st_dev,q.st_ino,q.st_size,q.st_mtime_ns,q.st_ctime_ns]
def ckname(n):require(type(n)==str and n and n not in ['.','..'] and '/' not in n and '\\' not in n,'unsafe entry name')
@contextlib.contextmanager
def directory(path):
 require(path.is_absolute() and '..' not in path.parts,'root containment')
 flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_DIRECTORY
 with contextlib.ExitStack() as e:
  fd=os.open('/',flags);e.callback(os.close,fd)
  for component in path.parts[1:]:
   ckname(component);fd=os.open(component,flags,dir_fd=fd);e.callback(os.close,fd)
  yield fd
@contextlib.contextmanager
def regular(root,n):
 ckname(n);flags=os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW
 f=os.open(n,flags,dir_fd=root)
 try:
  s=os.fstat(f);require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=OFF_MAX,n+' regular unique descriptor')
  yield f,s
  require(witness(s)==witness(os.fstat(f))==witness(os.stat(n,dir_fd=root,follow_symlinks=False)),n+' identity changed')
 finally:os.close(f)
def pread(f,count,start):
 require(0<=count<=CAP and 0<=start<=OFF_MAX-count,'metadata read outside cap')
 b=bytearray()
 while len(b)<count:
  c=os.pread(f,count-len(b),start+len(b));require(c,'short metadata read');b.extend(c)
 return bytes(b)
def header(b,payload_size):
 d=parse(b);require(type(d)==dict and d.pop('__metadata__',None)=={'format':'mlx'},'unexpected safetensors format')
 ranges=[]
 for k,row in d.items():
  require(isinstance(k,str) and re.fullmatch(r'[a-zA-Z0-9_.]+',k) and set(row)=={'dtype','shape','data_offsets'},'malformed tensor '+str(k))
  dt=row['dtype'];s=row['shape'];o=row['data_offsets'];width={'BF16':2,'U32':4,'F32':4}.get(dt,0)
  require(width and type(s)==list and len(s)<=8 and all(type(v)==int and 0<v<=OFF_MAX for v in s),'wrong shape/type '+k)
  require(type(o)==list and len(o)==2 and all(type(v)==int for v in o) and 0<=o[0]<o[1]<=payload_size and math.prod(s)*width==o[1]-o[0],'invalid extent '+k)
  ranges.append(o)
 pos=0
 for lo,hi in sorted(ranges):require(lo==pos,'hole/overlap in shard');pos=hi
 require(pos==payload_size,'unclaimed payload suffix')
 return d
def stream(f,size,timeout):
 h=hashlib.sha256();offset=0
 while offset<size:
  require(time.monotonic()<timeout,'custody hash deadline');b=os.pread(f,min(CHUNK,size-offset),offset);require(b,'unexpected EOF');offset+=len(b);h.update(b)
 return h.hexdigest()
def ledger(tensors,cfg):
 q=cfg['quantization'];require(q==cfg['quantization_config'] and (q['bits'],q['group_size'])==(4,64),'recipe mismatch')
 tags=set();count=collections.Counter();traffic=collections.Counter();comp=collections.Counter();over=set();layerbytes=collections.defaultdict(collections.Counter);largest=0
 for k,r in tensors.items():
  n=r['bytes'];shape=r['shape'];cls='vision_preserved' if k.startswith('vision_model.') else ('expert' if '.switch_mlp.' in k else ('embedding' if '.embed_tokens.' in k else 'trunk'))
  if cls!='vision_preserved':require(k.startswith('language_model.'),'unknown tensor scope '+k)
  if cls=='expert':require(len(shape)==3 and shape[0]==288 and n%288==0,'expert axis '+k);used=n//288*8
  elif cls=='embedding':require(len(shape)==2 and shape[0]==154880 and n%154880==0,'embedding rows');used=n//154880
  else:used=0 if cls=='vision_preserved' else n
  traffic[cls]+=used;comp[cls]+=n
  if k.startswith('language_model.model.layers.'):
   i=int(k.split('.')[3]);require(0<=i<45,'layer id');layerbytes[i][cls]+=used
  if r['dtype']=='U32':
   require(k.endswith('.weight'),'unrecognized packed tensor');name=k[:-7];ov=q.get(name,{'bits':q['bits'],'group_size':q['group_size']})
   require(set(ov)=={'bits','group_size'} and (ov['bits'],ov['group_size']) in [(4,64),(8,64)],'wrong affine recipe '+k)
   if name in q:over.add(name)
   bits=ov['bits'];group=ov['group_size'];require(len(shape) in (2,3) and shape[-1]*32%bits==0,'packed width');indim=shape[-1]*32//bits
   require(indim%group==0,'unaligned group');expected=shape[:-1]+[indim//group]
   for suff in ['.scales','.biases']:
    t=tensors[name+suff];require(t['dtype']=='BF16' and t['shape']==expected,'wrong affine metadata '+k+suff);tags.add(name+suff)
   r.update(bits=bits,group_size=group,logical_input_width=indim);count[str(bits)]+=1
   largest=max(largest,8*indim) if cls!='vision_preserved' else largest
 require(over==set(q)-{'group_size','bits'},'unconsumed recipe overrides')
 require(tags=={k for k in tensors if k.endswith(('.scales','.biases'))},'orphan affine components')
 require(set(layerbytes)==set(range(45)),'missing layer')
 return dict(full_checkpoint_by_family=dict(comp),logical_single_forward_by_family=dict(traffic),theoretical_logical_total=sum(traffic.values()),per_layer_sorted=[dict(layer=i,logical=dict(layerbytes[i])) for i in range(45)],quantized_module_counts=dict(count),largest_one_text_quant_row_f64_decode_bytes=largest,scope='logical tensor bytes (each trunk tensor once, one embedding row, eight of each 288 routed slots); not memory admission, physical reads, rereads, indexer evaluation, allocator or transient bounds')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['full','headers'],required=True);ap.add_argument('--out',type=pathlib.Path,required=True);ap.add_argument('--operation',required=True)
 a=ap.parse_args();require(re.fullmatch('[a-zA-Z0-9-]{8,80}',a.operation),'bad operation id');out=a.out
 require(out.is_absolute() and out.parent.resolve(strict=True)==out.parent and ROOT not in out.parents and out!=ROOT and out.parent.stat().st_mode&0o077==0,'private external output parent required')
 os.umask(0o077);out.mkdir(mode=0o700);put(out/'operation.json',exact(dict(operation=a.operation,pid=os.getpid(),mode=a.mode,implementation_sha256=sha(pathlib.Path(__file__).read_bytes()),revision=REV,chunk_bytes=CHUNK,deadline_s=1800)))
 limit=time.monotonic()+1800
 with urllib.request.urlopen(URL,timeout=20) as res:
  require(res.status==200 and res.url==URL,'publisher endpoint not pinned');b=res.read((1<<20)+1);require(len(b)<=(1<<20),'publisher metadata cap')
 reg=parse(b);require(reg['sha']==REV and reg['id']==REPO,'publisher identity');sib={}
 for v in reg['siblings']:require(v['rfilename'] not in sib,'duplicate publisher file');sib[v['rfilename']]=v
 put(out/'publisher.json',b);pubsha=sha(b)
 require(sorted(k for k in sib if k.endswith('.safetensors'))==SHARDS,'wrong shard set')
 meta={};witnesses={};rows={};manifest={};invent={};total=0;payload=0
 with directory(ROOT) as root:
  for name,expect in PIN.items():
   ref=sib[name]
   with regular(root,name) as (f,st):
    require(st.st_size==ref['size'] and st.st_size<=CAP,'metadata size');b=pread(f,st.st_size,0);dig=sha(b);blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    require(dig==expect and blob==ref['blobId'],'metadata identity '+name);meta[name]=dict(sha256=dig,bytes=len(b),git_blob=blob)
    if name.endswith('.json'):rows[name]=parse(b)
    witnesses[name]=witness(st)
  index=rows['model.safetensors.index.json'];ix=index['weight_map'];require(type(ix)==dict and isinstance(index['metadata']['total_size'],int) and set(ix.values())==set(SHARDS),'invalid index')
  for name in SHARDS:
   ref=sib[name];lfs=ref['lfs'];require(re.fullmatch('[0-9a-f]{64}',lfs['sha256']),'invalid publisher lfs')
   with regular(root,name) as (f,st):
    size=st.st_size;require(size==ref['size']==lfs['size'] and size>8,'shard size');total+=size
    z=struct.unpack('<Q',pread(f,8,0))[0];require(0<z<=CAP and z<=size-8,'header bound');raw=pread(f,z,8);h=header(raw,size-8-z);payload+=size-8-z
    for k,v in h.items():
     require(ix.get(k)==name and k not in invent,'ambiguous shard/index mapping '+k);lo,hi=v['data_offsets'];invent[k]=dict(shard=name,offset=8+z+lo,bytes=hi-lo,dtype=v['dtype'],shape=v['shape'])
    item=dict(bytes=size,header_bytes=z,header_sha256=sha(raw),tensor_count=len(h),publisher_lfs_sha256=lfs['sha256'],publisher_blob_id=ref['blobId'])
    if a.mode=='full':
     actual=stream(f,size,limit);require(actual==lfs['sha256'],'whole shard mismatch '+name);item['checked_whole_sha256']=actual
    witnesses[name]=witness(st)
   manifest[name]=item;put(out/(name+'.json'),exact(dict(operation=a.operation,witness=witnesses[name],**item)));print(name,a.mode,flush=True)
  require(set(invent)==set(ix) and total==index['metadata']['total_size'],'index or aggregate size');cfg=rows['config.json'];ld=ledger(invent,cfg)
  # Reopen canonical root; rebind every original witness after streaming.
  with directory(ROOT) as fresh:
   require((os.fstat(root).st_dev,os.fstat(root).st_ino)==(os.fstat(fresh).st_dev,os.fstat(fresh).st_ino),'root replaced')
   for name,w in witnesses.items():
    with regular(fresh,name) as (_,st):require(witness(st)==w,'terminal drift '+name)
  put(out/'witnesses.json',exact(witnesses));put(out/'inventory.json',exact(invent));put(out/'logical-ledger.json',exact(ld));tok=rows['tokenizer_config.json'];gen=rows['generation_config.json'];text=cfg['text_config']
  require(tok['pad_token']==tok['eos_token']=='<|endoftext|>' and gen['pad_token_id']==text['pad_token_id']==154820 and 154820 in gen['eos_token_id']==text['eos_token_id'],'special-token cross-check')
  spec=sib['tokenizer.json'];require(spec['size']==20217442 and spec['lfs']['sha256']=='19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d','tokenizer provenance')
  result=dict(schema='studio017-checkpoint-custody/1',operation=a.operation,mode=a.mode,revision=REV,repo=REPO,publisher_response_sha256=pubsha,metadata=meta,shards=manifest,shard_file_bytes=total,payload_bytes=payload,text_tensor_count=sum(k.startswith('language_model.') for k in invent),vision_preserved_tensor_count=sum(k.startswith('vision_model.') for k in invent),tokenizer_large_opaque=dict(publisher_sha256=spec['lfs']['sha256'],publisher_bytes=spec['size'],local_body_read=False,qualification='publisher metadata only; lookup not used for direct numeric input'),direct_input_option=dict(token_id=154820,interpretation='literal model-config pad/end-of-text special id, as single INPUT in empty state; no BPE/text/template; no claim of BOS'),ledger_sha256=sha(exact(ld)),inventory_sha256=sha(exact(invent)),witnesses_sha256=sha(exact(witnesses)),all_shards_byte_verified=a.mode=='full')
  put(out/'receipt.json',exact(result));print('receipt',sha(exact(result)),'verified',result['all_shards_byte_verified'],flush=True)
if __name__=='__main__':main()
