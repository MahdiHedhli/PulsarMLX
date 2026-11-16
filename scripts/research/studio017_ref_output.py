"""Receipt writer for the already-admitted reference child; never opens a model.

No CLI. The caller must authenticate the exclusive reference grant/claim and
checkpoint custody, serialize the heavy job, bound RSS/time/BLAS, isolate the
output directory, and seal/reconcile its original bytes after positive reap.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

import numpy as np

from studio017_ref_graph import cold_forward
from studio017_ref_store import finite, require


class Output:
    def __init__(self,dirfd):
        st=os.fstat(dirfd)
        require(stat.S_ISDIR(st.st_mode) and st.st_uid==os.geteuid() and
                st.st_mode&0o077==0 and not os.listdir(dirfd),'fresh private output')
        self.dirfd=dirfd
        self.written={}
        self.routes=[]
        self.byte_total=0

    def write(self,name,data):
        require(name not in self.written and '/' not in name and 0<len(data)<=8*1024**2,
                'duplicate or oversized reference output')
        self.byte_total+=len(data)
        require(self.byte_total<256*1024**2,'reference output budget')
        fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o600,dir_fd=self.dirfd)
        with os.fdopen(fd,'wb') as f:
            require(f.write(data)==len(data),'short reference output')
            f.flush()
            os.fsync(f.fileno())
        self.written[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

    def vector(self,i,label,a):
        require(type(i) is int and 0<=i<=45,'layer id')
        x=finite(np.asarray(a,dtype='<f4',order='C'))
        self.write(f'{i:02}.{label}.f32',x.tobytes())

    def __call__(self,kind,meta,row):
        i=meta.get('layer')
        if kind=='embedding':
            self.vector(0,'input.embedding',row['embedding'])
        elif kind=='mhc':
            self.vector(i,'mhc.'+meta['branch'],row['coefficients'])
        elif kind=='kda':
            self.vector(i,'kda.qkv_beta',row['qkv_beta'])
            self.vector(i,'kda.decay',row['decay'])
            self.vector(i,'kda.conv_state',row['suffix'])
            self.vector(i,'kda.recurrent_state',row['state'])
            self.vector(i,'state.offset',[meta['position']])
        elif kind=='mla':
            self.vector(i,'mla.latent',row['latent_k'])
            self.vector(i,'mla.indexer',row['indexer_cache'])
            self.vector(i,'state.offset',[meta['position']])
        elif kind=='route':
            for n in ('corrected','routed','shared'):
                self.vector(i,'moe.'+n,row[n])
            self.routes.append(dict(layer=i,ids=meta['selected'],weights=row['weights'].tolist(),
                                    cutoff_gap=meta['cutoff_gap']))
        elif kind=='layer':
            for k,n in [('attention','attention.output'),('ffn','ffn.output'),('streams','layer.streams')]:
                self.vector(i,n,row[k])
        elif kind=='golden':
            self.vector(45,'final.norm',row['normalized'])
        else:
            raise ValueError('unknown reference stage')


def run_admitted_reference(store,output_dir):
    fd=os.open(Path(output_dir),os.O_RDONLY|os.O_NOFOLLOW|os.O_DIRECTORY)
    try:
        sink=Output(fd)
        with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
            logits,win,runner,margin=cold_forward(store,154820,sink)
        for shard in store.fds:
            store.check_witness(shard)
        require(len(sink.routes)==42 and [x['layer'] for x in sink.routes]==list(range(3,45)) and
                logits.shape==(154880,),'complete reference graph')
        sink.write('logits.f32',np.asarray(logits,dtype='<f4').tobytes())
        rep=dict(schema='studio017-reference/1',input_id=154820,token_id=win,runner_up=runner,
                 margin=margin,layer_count=45,position=0,generated_token_count=1,
                 routes=sink.routes,files=dict(sink.written))
        sink.write('report.json',(json.dumps(rep,sort_keys=True,separators=(',',':'),
                                            allow_nan=False)+'\n').encode('ascii'))
        os.fsync(fd)
        return rep
    finally:
        os.close(fd)
