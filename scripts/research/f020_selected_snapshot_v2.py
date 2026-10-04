#!/usr/bin/env python3
"""Independent strict selected snapshot reader for R1. No checkpoint API.

Only the later reviewed capability runner may call this on real content.
Expected bindings must be external to the snapshot. No command-line entrypoint.
"""
import hashlib
import json
import os
import stat
import struct

LENGTHS = (4194304,262144,262144)*3
PAYLOAD = sum(LENGTHS)
MAX_HEADER = 131072
PREFIX = 'language_model.model.layers.3.mlp.switch_mlp.'
MODULES = tuple(PREFIX+s for s in ('gate_proj','up_proj','down_proj'))


def require(ok, why):
    if not ok:
        raise ValueError('R1-SNAPSHOT: '+why)


def keys(value, names):
    require(type(value) is dict and set(value)==set(names.split()), 'strict keys')


def integer(value, expected):
    require(type(value) is int and value==expected, 'integer binding')


def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'duplicate key')
        result[k]=v
    return result


def reject_constant(_):
    raise ValueError('R1-SNAPSHOT: nonfinite JSON')


def decode_header(raw, expected):
    require(len(raw)<=MAX_HEADER,'header bound')
    # Depth scanner prevents stdlib parser recursion pressure before decoding.
    depth=0; quoted=False; escaped=False
    for byte in raw:
        if quoted:
            if escaped: escaped=False
            elif byte==92: escaped=True
            elif byte==34: quoted=False
        elif byte==34: quoted=True
        elif byte in (91,123):
            depth+=1;require(depth<=16,'JSON depth')
        elif byte in (93,125): depth-=1
    h=json.loads(raw,object_pairs_hook=unique,parse_constant=reject_constant)
    keys(h,'schema owned payload_lengths scope')
    require(h['scope']=='selected packed content only; no numerical qualification','snapshot scope')
    require(h['schema']=='pulsarmlx.selected-expert-snapshot/1','schema')
    require(type(h['payload_lengths']) is list and len(h['payload_lengths'])==9,'nine lengths')
    for got,want in zip(h['payload_lengths'],LENGTHS,strict=True):integer(got,want)
    o=h['owned']
    keys(o,'schema plan selected_range_sha256 owned_bytes packed_weights_unchanged native_calls whole_shard_reads whole_shard_hashes scope')
    require(o['schema']=='pulsarmlx.bounded-expert-owned/1','owned schema')
    integer(o['owned_bytes'],PAYLOAD)
    for name in ('native_calls','whole_shard_reads','whole_shard_hashes'):integer(o[name],0)
    require(o['packed_weights_unchanged'] is True,'packed custody')
    require(o['scope']=='host owned range bytes only; no numerical or full-checkpoint qualification','owned scope')
    require(o['selected_range_sha256']==expected['ranges_sha256'],'external nine hashes')
    p=o['plan']
    keys(p,'schema checkpoint metadata_snapshot_sha256 metadata_bytes_read request planes selected_bytes identity_scope')
    require(p['schema']=='pulsarmlx.bounded-expert-plan/1','plan schema')
    require(p['checkpoint']==expected['checkpoint'] and bool(expected['checkpoint']),'checkpoint binding')
    require(p['metadata_snapshot_sha256']==expected['metadata_sha256'],'metadata binding')
    integer(p['metadata_bytes_read'],790848);integer(p['selected_bytes'],PAYLOAD)
    require(p['identity_scope']=='metadata snapshot and selected ranges only; no whole-checkpoint payload identity','source scope')
    q=p['request'];keys(q,'modules expert experts d h bits group_size')
    require(q['modules']==list(MODULES),'modules/layer')
    for name,value in [('expert',0),('experts',288),('d',4096),('h',2048),('group_size',64)]:integer(q[name],value)
    require(type(q['bits']) is list and len(q['bits'])==3,'bits')
    for bits in q['bits']:integer(bits,4)
    require(type(p['planes']) is list and len(p['planes'])==3,'three roles')
    for i,plane in enumerate(p['planes']):
        keys(plane,'role module expert bits group_size resolved_from metadata_dtype logical_shape ranges')
        require(plane['role']==('gate','up','down')[i] and plane['module']==MODULES[i],'role identity')
        for name,value in [('expert',0),('bits',4),('group_size',64)]:integer(plane[name],value)
        require(plane['resolved_from']=='default' and plane['metadata_dtype']=='BF16','recipe')
        shape=[4096,2048] if i==2 else [2048,4096]
        require(type(plane['logical_shape']) is list and len(plane['logical_shape'])==2,'rank')
        for a,b in zip(plane['logical_shape'],shape,strict=True):integer(a,b)
        require(type(plane['ranges']) is list and len(plane['ranges'])==3,'range count')
        for j,r in enumerate(plane['ranges']):
            keys(r,'tensor shard begin len')
            require(r['tensor']==MODULES[i]+'.'+('weight','scales','biases')[j],'tensor identity')
            integer(r['len'],LENGTHS[3*i+j])
            require(type(r['begin']) is int and 0<=r['begin']<=2**64-1-r['len'],'offset overflow')
            require(type(r['shard']) is str and r['shard'] not in ('','.','..') and '/' not in r['shard'],'shard name')
    return h


def read_snapshot(path, expected):
    keys(expected,'snapshot_sha256 snapshot_bytes metadata_sha256 checkpoint ranges_sha256')
    hashes=[expected['snapshot_sha256'],expected['metadata_sha256'],*expected['ranges_sha256']]
    require(len(expected['ranges_sha256'])==9,'expected nine hashes')
    require(all(type(s) is str and len(s)==64 and all(c in '0123456789abcdef' for c in s) for s in hashes),'expected digest syntax')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as file:
        before=os.fstat(file.fileno())
        require(stat.S_ISREG(before.st_mode) and not before.st_mode&0o222,'regular immutable descriptor')
        require(before.st_size==expected['snapshot_bytes'] and 16<before.st_size<=16+MAX_HEADER+PAYLOAD,'file bound')
        prefix=file.read(16)
        require(len(prefix)==16 and prefix[:8]==b'PLSEX001','magic')
        size=struct.unpack_from('<Q',prefix,8)[0]
        require(0<size<=MAX_HEADER and 16+size+PAYLOAD==before.st_size,'framing')
        raw=file.read(size);require(len(raw)==size,'header truncation')
        decode_header(raw,expected)
        digest=hashlib.sha256(prefix+raw);parts=[]
        for n,want in zip(LENGTHS,expected['ranges_sha256'],strict=True):
            part=file.read(n);require(len(part)==n,'payload truncation')
            require(hashlib.sha256(part).hexdigest()==want,'range digest')
            digest.update(part);parts.append(part)
        require(file.read(1)==b'','trailing')
        after=os.fstat(file.fileno())
        require(all(getattr(before,k)==getattr(after,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode')),'descriptor changed')
        require(digest.hexdigest()==expected['snapshot_sha256'],'whole snapshot digest')
    return {role:tuple(parts[3*i:3*i+3]) for i,role in enumerate(('gate','up','down'))}
