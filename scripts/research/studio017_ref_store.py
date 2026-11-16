"""Independent CPU reader for the cold text reference. No executable entry point.

Caller supplies already-admitted read-only shard fds and their *verified* header
descriptors. No user-controlled checkpoint filename lookup or whole-shard mapping.
Rows decode from original uint32 affine codes (little-endian, LSB first). Packing
and arithmetic do not import the Rust candidate or any MLX package.
"""
import fcntl
import math
import os
import stat

import numpy as np


class Refusal(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise Refusal(why)


def finite(a):
    require(np.isfinite(a).all(), 'nonfinite reference intermediate')
    return a


def bf(x):
    """Round represented values to BF16 nearest, ties even (F32 carrier)."""
    a = np.asarray(x, dtype='<f4')
    finite(a)
    u = a.view('<u4')
    y = ((u + ((u >> 16) & 1) + np.uint32(0x7fff)) & np.uint32(0xffff0000)).view('<f4')
    return finite(y)


def _shape(s):
    require(isinstance(s,(list,tuple)) and 0<len(s)<=4 and
            all(type(i) is int and 0<i<2**32 for i in s), 'shape')
    return tuple(s)


TYPES = {'BF16': '<u2', 'U32': '<u4', 'F32': '<f4'}
MAX_READ = 8 * 1024**2
TILE = 16


class Store:
    """tensor descriptor = (admitted shard-id, absolute offset, dtype, shape).
    witnesses[shard-id]=(device,inode,size,mtime_ns,ctime_ns); the launcher binds
    these to publisher content, complete validated headers and frozen inventory.
    Closing fds and attesting first/last source witnesses are launcher duties.
    """
    def __init__(self, fds, tensors, witnesses):
        self.fds, self.tensors, self.witnesses = dict(fds), dict(tensors), dict(witnesses)
        require(0 < len(self.fds)<=18 and set(self.fds)==set(self.witnesses),'shards')
        for key,fd in self.fds.items():
            st=os.fstat(fd)
            require(stat.S_ISREG(st.st_mode) and (fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE)==os.O_RDONLY,
                    'ordinary readonly shard')
            self.check_witness(key)
        for key,(part,off,dtype,shape) in self.tensors.items():
            require(part in self.fds and type(off) is int and off>=8 and dtype in TYPES,'tensor descriptor')
            length=math.prod(_shape(shape))*np.dtype(TYPES[dtype]).itemsize
            require(off+length<=self.witnesses[part][2],'tensor extent')

    def check_witness(self,key):
        st=os.fstat(self.fds[key])
        require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==tuple(self.witnesses[key]),
                'original shard changed')

    def raw(self,name,shape,dtype,start,count):
        shape=_shape(shape)
        require(name in self.tensors,'missing tensor '+name)
        part,base,dt,got=self.tensors[name]
        require(dt==dtype and tuple(got)==shape,'recipe/shape mismatch '+name)
        size=np.dtype(TYPES[dtype]).itemsize
        require(type(start) is int and type(count) is int and start>=0 and count>0 and
                start+count<=math.prod(shape) and count*size<=MAX_READ,'read bounds')
        self.check_witness(part)
        b=os.pread(self.fds[part],count*size,base+start*size)
        require(len(b)==count*size,'short shard read')
        a=np.frombuffer(b,dtype=TYPES[dtype])
        if dtype=='BF16':
            a=(a.astype('<u4') << 16).view('<f4')
        return finite(a)

    def dense(self,name,shape,dtype='BF16'):
        # Largest non-quantized matrix on this checkpoint: router 288 x 4096.
        return self.raw(name,shape,dtype,0,math.prod(shape)).reshape(shape)

    def tile(self,prefix,width,outputs,first,count,bits,group=None):
        require(type(width) is int and width%64==0 and 0<width<=16384 and
                type(outputs) is int and 0<outputs<=154880 and
                bits in (4,8) and 0<=first<outputs and 1<=count<=TILE and
                first+count<=outputs,'affine tile')
        planes=() if group is None else (group[0],)
        if group is not None:
            require(len(group)==2 and all(type(v) is int for v in group) and
                    group[0] in (64,288) and 0<=group[1]<group[0],'plane')
        start=(0 if group is None else group[1]*outputs)+first
        pack=32//bits
        words=self.raw(prefix+'.weight',planes+(outputs,width//pack),'U32',
                       start*(width//pack),count*(width//pack)).reshape(count,-1,1)
        shifts=np.arange(pack,dtype=np.uint32)*bits
        q=((words>>shifts)&((1<<bits)-1)).reshape(count,width//64,64).astype(np.float64)
        for op,name in [('scale','scales'),('bias','biases')]:
            a=self.raw(prefix+'.'+name,planes+(outputs,width//64),'BF16',
                       start*(width//64),count*(width//64)).reshape(count,-1,1)
            if op=='scale':
                np.multiply(q,a,out=q)
            else:
                np.add(q,a,out=q)
        return finite(q.reshape(count,width))

    def projection(self,prefix,x,outputs,group=None,bits=8):
        x=finite(np.asarray(x,dtype=np.float64))
        require(x.ndim==1,'projection vector')
        v=np.empty(outputs,dtype=np.float32)
        for first in range(0,outputs,TILE):
            n=min(TILE,outputs-first)
            # Binary64 ideal dot, then the semantic BF16 projection boundary.
            vals=self.tile(prefix,len(x),outputs,first,n,bits,group)@x
            v[first:first+n]=bf(vals)
        return finite(v)

    def embedding(self,prefix,token,width,vocab):
        return bf(self.tile(prefix,width,vocab,token,1,8)[0])
