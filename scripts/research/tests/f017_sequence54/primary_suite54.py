"""S54 fixed synthetic producer cases, imported only after current fences.

No producer counters are used to construct the independent boundary transcript.
The raw-file fault injector is a qualification seam, not production capability.
"""
import dataclasses
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

G = dict(layers=1, hidden=4, vocab=9, dense_layers=1, experts=4,
         top_k=2, dense_ffn=6, expert_ffn=4, heads=1, q_rank=4, kv_rank=4,
         qk_nope=4, qk_rope=2, value_dim=4, rms_epsilon=1e-5,
         rope_base=8000000.0, route_scale=2.5)
MEASUREMENT = hashlib.sha256(b'S54 fixed synthetic producer context').hexdigest()

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()

def write_fixture(path, raw):
    assert type(raw) is bytes and len(raw) <= 1048576
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        at = 0
        while at < len(raw):
            n = os.write(fd, raw[at:]); assert n > 0; at += n
        os.fsync(fd)
    finally:
        os.close(fd)

def save_record(path, value):
    raw = canonical(value)
    assert len(raw) <= 32768, 'qualification record overflow'
    write_fixture(path, raw)
    return hashlib.sha256(raw).hexdigest()

def bank_case(c,data):
    # Independent API transcripts are test evidence, not the producer's bounded
    # measurement records. Fixed chunks preserve every call without altering the
    # producer's overflow policy or the 32768-byte control/capture ceiling.
    transcript=data.pop('transcript');chunks=[]
    for offset in range(0,len(transcript),64):
        name='transcript-'+str(offset//64)+'.json'
        rows=transcript[offset:offset+64]
        h=save_record(c.area/name,rows)
        chunks.append(dict(path=name,sha256=h,rows=len(rows)))
    data['transcript_authority']=dict(rows=len(transcript),sha256=hashlib.sha256(canonical(transcript)).hexdigest(),chunks=chunks)
    data['synthetic_context']=dict(c.expected)
    data['context_disposition']='SYNTHETIC_ONLY_NOT_EXECUTION_AUTHORITY'
    h=save_record(c.area/'case-result.json',data)
    return dict(case=data['case'],mode=data['mode'],result=data['result'],
                result_path=data['case']+'/case-result.json',result_sha256=h,
                actual_api_calls=len(transcript))

def identity(fd, ordinal):
    s = os.fstat(fd)
    assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode, size=s.st_size,
                mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns, shard_ordinal=ordinal,
                role='GRAPH_PAYLOAD', lease_id='S54-LEASE-'+str(ordinal))

def basic_records(decode=False, factory=False):
    q8 = b'\x00\x7c'+b'\0'*32
    result = [
        ('a-probe', [1], 3, 'FORMAT_PROBE', 'F32', struct.pack('<f', .5)),
        ('z-probe', [32] if factory else [1], 6, 'FORMAT_PROBE',
         'Q8_0' if factory else 'F32', q8 if factory else struct.pack('<f', -.25)),
        ('v', [32] if decode else [4], 2, 'GRAPH', 'Q8_0' if decode else 'F32',
         q8 if decode else struct.pack('<4f', 1, 2, -3, 4)),
        ('m', [4, 2], 4, 'GRAPH', 'F32', struct.pack('<8f', *range(1, 9))),
        ('e', [4, 2, 2], 5, 'GRAPH', 'F32', struct.pack('<16f', *range(1, 17))),
        ('token_embd.weight', [4, 9], 2, 'GRAPH', 'F32', struct.pack('<36f', *[i/10 for i in range(36)])),
    ]
    return result

def numerical_records(seed):
    # This import is behind the seal and uses the immutable historical fixture.
    import generate_f017_corrected_oracle_fixtures as generator
    case = generator.fixture(seed)
    geometry = case['geometry']; grouped = {}
    for name, values in case['tensors'].items():
        base, mark, expert = name.partition('#')
        grouped.setdefault(base, {})[int(expert) if mark else None] = values
    result = []
    for index, (name, entries) in enumerate(sorted(grouped.items())):
        if name in ('token_embd.weight', 'output.weight'):
            dims = [4, 9]
        elif '_norm.weight' in name or name == 'output_norm.weight' or name.endswith('.bias'):
            dims = [4]
        elif name.endswith(('attn_q_b.weight', 'attn_kv_a_mqa.weight')):
            dims = [4, 6]
        elif name.startswith('blk.0.ffn_') and name.endswith(('gate.weight', 'up.weight')):
            dims = [4, 6]
        elif name == 'blk.0.ffn_down.weight':
            dims = [6, 4]
        else:
            dims = [4, 4]
        if None in entries:
            assert len(entries) == 1
            values = entries[None]
        else:
            assert sorted(entries) == list(range(len(entries)))
            dims.append(len(entries))
            values = [v for expert in sorted(entries) for v in entries[expert]]
        expected_count = 1
        for n in dims: expected_count *= n
        assert len(values) == expected_count, name
        result.append((name, dims, 2+index%5, 'GRAPH', 'F32', struct.pack('<'+'f'*len(values), *values)))
    result += [('a-probe', [1], 3, 'FORMAT_PROBE', 'F32', struct.pack('<f', .5)),
               ('z-probe', [1], 6, 'FORMAT_PROBE', 'F32', struct.pack('<f', -.25))]
    return result, geometry, case['token'], case['position']

class Case:
    def __init__(self, area, label, code_view, records, geometry=None, token=0, position=0):
        self.area = area/label; self.area.mkdir(mode=0o700)
        self.observations = self.area/'observations'; self.observations.mkdir(mode=0o700)
        self.transcript=[]; self.fds=[]; self.ranges=[]; self.original=os.pread; self.fault=None
        identity_suffix=hashlib.sha256(str(self.area).encode()).hexdigest()[:16].upper()
        # Case labels are display identifiers, not production identity grammar.
        # Keep their spelling in evidence; use one explicit synthetic-ID projection.
        identity_label=label.replace('_','-')
        assert identity_label and all(ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for ch in identity_label)
        self.ids = dict(package_attempt_id='S54-PACKAGE-'+identity_label+'-'+identity_suffix,
                        consumer_event_id='S54-PRIMARY-'+identity_label+'-'+identity_suffix,
                        producer_measurement_sha256=MEASUREMENT)
        assert all(len(self.ids[key])<=128 for key in ('package_attempt_id','consumer_event_id'))
        self.authority = dict(self.ids, authorization_id='S54-AUTHORITY-'+identity_label+'-'+identity_suffix,
                              durable_start_sha256='1'*64, access_census_sha256='2'*64)
        shards={s:bytearray() for s in range(2,7)}; catalog_records=[]
        for name, dims, shard, purpose, fmt, raw in records:
            offset=len(shards[shard]); shards[shard].extend(raw)
            catalog_records.append(dict(name=name, dims=dims, shard_ordinal=shard,
              purpose=purpose, format=fmt, byte_offset=offset, byte_length=len(raw)))
            self.ranges.append((shard, offset, offset+len(raw), 'FORMAT_PROBE' if purpose=='FORMAT_PROBE' else 'NUMERICAL_PAYLOAD', name))
        self.shard_sizes=[]
        try:
            for shard, data in shards.items():
                raw=bytes(data) or b'\0'*4
                p=self.area/('shard-'+str(shard)+'.bin'); write_fixture(p,raw)
                self.fds.append(os.open(p,os.O_RDONLY|os.O_NOFOLLOW));self.shard_sizes.append(len(raw))
            self.identities=[identity(fd,s) for s,fd in enumerate(self.fds,2)]
            self.expected=dict(self.ids,descriptor_set_sha256=hashlib.sha256(canonical(self.identities)).hexdigest())
            self.code_view=code_view
            self.by_fd={fd:s for s,fd in enumerate(self.fds,2)}
            document=dict(schema='pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0',
                geometry=geometry or G,token=token,position=position,records=catalog_records)
            raw=canonical(document);catalog=self.area/'catalog.json';write_fixture(catalog,raw)
            core=Path(code_view)/'scripts/research/f017_corrected_oracle_primary_numerics_v3.py'
            self.candidate=dict(active_generation='V11',primary_numerical_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                package_attempt_id=self.ids['package_attempt_id'],primary_event_id=self.ids['consumer_event_id'],
                tensor_catalog_path=str(catalog),tensor_catalog_sha256=hashlib.sha256(raw).hexdigest(),
                shards=[dict(size_bytes=0)]+[dict(size_bytes=n) for n in self.shard_sizes])
            os.pread=self.pread
        except BaseException:
            self.close();raise
    def pread(self,fd,size,offset):
        shard=self.by_fd[fd]
        matches=[r for r in self.ranges if r[0]==shard and r[1]<=offset and offset+size<=r[2]]
        assert len(matches)==1, 'independent range attribution'
        r=matches[0]
        row=dict(shard_ordinal=shard,purpose=r[3],record=r[4],offset=offset,requested_bytes=size)
        self.transcript.append(row)
        try:
            if self.fault=='ERROR' and r[4]=='v': raise OSError(errno.EIO,'S54 synthetic API error')
            raw=self.original(fd,size,offset)
            if self.fault=='SHORT' and r[4]=='v': raw=raw[:max(1,len(raw)//2)]
            if self.fault=='ZERO' and r[4]=='v': raw=b''
        except OSError as error:
            row.update(outcome='ERROR',errno=error.errno);raise
        row.update(outcome='RETURN',returned_bytes=len(raw));return raw
    def close(self):
        os.pread=self.original
        for fd in self.fds:os.close(fd)
        self.fds=[]

def outcome(call):
    try:return dict(kind='RETURN',value=call())
    except Exception as e:return dict(kind='RAISED',type=type(e).__name__,message=str(e)),e

def output_snapshot(value):
    return dict(hidden=value.final_hidden_payload.hex(),normalized=value.final_normalized_payload.hex(),
        logits=value.full_logits_payload.hex(),captures=[dataclasses.asdict(c) for c in value.layer_captures],
        selected_token=value.selected_token,top=[dataclasses.asdict(t) for t in value.top_32],
        margin_f64_bits=struct.pack('<d',value.top_1_margin).hex(),tie_rule=value.tie_rule,
        core_execution_count=value.core_execution_count)

# Fixed test bodies and independent assertions are appended before their batch
# plan is frozen. Nothing in this module is run by the unconfined parent.

def measured_source(c, module, observation_module):
    if observation_module is None:
        source, geometry, token, position = module.source_from_inherited_descriptors(c.candidate,c.identities,c.fds)
        return source, geometry, token, position, None
    owner=observation_module._start_primary_observation(c.candidate,c.identities,c.observations,c.authority)
    source,geometry,token,position=module.source_from_inherited_descriptors(
        c.candidate,c.identities,c.fds,_observation_owner=owner)
    return source,geometry,token,position,owner

def completed(c, owner, module, result='RETURNED', stage='COMPLETE'):
    import observation_oracle54 as oracle
    attachment=module._finish_primary_observation(owner,result,stage)
    oracle.require_complete(attachment,c.transcript,c.ids)
    readback=module._read_primary_observation(c.observations,c.expected)
    oracle.require_complete(readback,c.transcript,c.ids)
    assert attachment==readback
    oracle.verify_durable(c.observations,attachment,c.transcript,c.expected,c.code_view,result,stage)
    return attachment

def basic_case(area,label,code_view,mode,observation_module):
    import f017_corrected_oracle_primary_target_source_v11 as target
    c=Case(area,label,code_view,basic_records(decode=mode=='DECODE'))
    try:
        source,g,t,p,owner=measured_source(c,target,observation_module)
        before=len(c.transcript);values=None;error=None
        if mode in ('SHORT','ZERO','ERROR'): c.fault=mode
        if mode=='IDENTITY':source.handles[2][0]['mtime_ns']+=1
        if mode=='BOUNDS':source.records['v']['byte_length']=4
        try:
            if mode=='FULL':
                values=[source.vector('v',4),source.matrix('m',2,4).row(0),
                        source.matrix('m',2,4).row(1),source.expert('e',1,2,4).row(1)]
                assert values==[[1.,2.,-3.,4.],[1.,2.,3.,4.],[5.,6.,7.,8.],[13.,14.,15.,16.]]
            else:values=source.vector('v',32 if mode=='DECODE' else 4)
        except Exception as e:error={'type':type(e).__name__,'message':str(e)}
        expected_errors={'SHORT':('ValueError','primary descriptor short read'),
            'ZERO':('ValueError','primary descriptor short read'),'ERROR':('OSError','[Errno 5] S54 synthetic API error'),
            'IDENTITY':('ValueError','primary inherited descriptor identity'),
            'BOUNDS':('ValueError','primary tensor bounds'),
            'DECODE':('ValueError','non-finite quantization scale')}
        if mode=='FULL':assert error is None
        else:assert error==dict(zip(('type','message'),expected_errors[mode])),error
        entered=len(c.transcript)-before
        assert entered==(0 if mode in ('IDENTITY','BOUNDS') else 4 if mode=='FULL' else 1)
        attachment=completed(c,owner,observation_module,'RAISED' if error else 'RETURNED') if observation_module else None
        data=dict(case=label,mode=mode,result='PASS',transcript=c.transcript,values=values,
                  stop=error,boundary_delta=entered,old_logical_tensor_reads=source.tensor_reads,
                  path_reopen_count=source.path_reopen_count,observation=attachment)
        return bank_case(c,data)
    finally:c.close()

def wrapper_case(area,label,code_view,mode,observation_module,seed=None):
    import f017_corrected_oracle_primary_wrapper_v11 as wrapper
    import f017_corrected_oracle_primary_numerics_v3 as core
    if seed:
        records,g,t,p=numerical_records(seed)
    else:records,g,t,p=basic_records(factory=mode=='FACTORY'),G,0,0
    c=Case(area,label,code_view,records,g,t,p)
    original=core.execute_outputs;execution_count=0;snapshot=None;error=None;exception=None
    def observe_core(*args,**kwargs):
        nonlocal execution_count,snapshot
        execution_count+=1
        output=original(*args,**kwargs)
        snapshot=output_snapshot(output)
        return output
    try:
        core.execute_outputs=observe_core
        try:
            wrapper._qualification_execute_target_and_bank(c.candidate,c.identities,c.fds,c.observations,**c.authority)
        except Exception as e:
            exception=e;error={'type':type(e).__name__,'message':str(e)}
        assert error is not None,'tiny wrapper cannot bank full result'
        expected={'FACTORY':('ValueError','non-finite quantization scale'),
            'CORE':('ValueError','primary tensor missing: blk.0.attn_norm.weight'),
            'BANK':('ResultEnvelopeError','numerical output payload binding')}[mode]
        assert error==dict(zip(('type','message'),expected)),error
        assert execution_count==(0 if mode=='FACTORY' else 1)
        assert (snapshot is not None)==(mode=='BANK')
        attachment=None
        if observation_module:
            import observation_oracle54 as oracle
            attachment=getattr(exception,'primary_read_observation',None)
            assert attachment is not None,'exception lost observation prefix'
            oracle.require_complete(attachment,c.transcript,c.ids)
            persisted=observation_module._read_primary_observation(c.observations,c.expected)
            oracle.require_complete(persisted,c.transcript,c.ids)
            assert attachment==persisted
            phases={'FACTORY':(),'CORE':('PHASE_CORE',),'BANK':('PHASE_CORE','PHASE_CORE_COMPLETE','PHASE_BANK')}[mode]
            oracle.verify_durable(c.observations,attachment,c.transcript,c.expected,c.code_view,'RAISED',mode,phases)
        assert len(c.transcript)>0
        data=dict(case=label,mode=mode,seed=seed,result='PASS',transcript=c.transcript,
          values=snapshot,stop=error,core_execution_count=execution_count,
          observation=attachment,full_result_success='NOT_QUALIFIED_EXPECTED_TINY_GEOMETRY_REFUSAL')
        return bank_case(c,data)
    finally:
        core.execute_outputs=original;c.close()

BASIC_MODES=('FULL','SHORT','ZERO','ERROR','IDENTITY','BOUNDS','DECODE')

def run(case_id,work_dir,code_view):
    root=Path(work_dir)
    assert root.resolve()==root and root.is_dir()
    assert case_id in ('BASIC_BASELINE','BASIC_SUCCESSOR','WRAPPER_BASELINE','WRAPPER_SUCCESSOR','FAULTS_SUCCESSOR')
    measured=case_id.endswith('SUCCESSOR')
    observation_module=None
    if measured:
        import f017_primary_read_observation_v1 as observation_module
    area=root/case_id;area.mkdir(mode=0o700)
    results=[]
    if case_id.startswith('BASIC_'):
        for mode in BASIC_MODES:
            results.append(basic_case(area,mode,code_view,mode,observation_module))
    elif case_id.startswith('WRAPPER_'):
        for mode,seed in (('FACTORY',None),('CORE',None),('BANK',18101),('BANK',18102)):
            label=mode+('-'+str(seed) if seed else '')
            results.append(wrapper_case(area,label,code_view,mode,observation_module,seed))
    else:
        import primary_faults54
        results=primary_faults54.run(area,code_view)
    summary=dict(schema='f017.sequence54.fixed-primary-suite/1',result='PASS',case_id=case_id,
      cases=results,distinct_cases=len(results),actual_api_calls=sum(r['actual_api_calls'] for r in results),
      observation_scope='PRIMARY_API_ONLY' if measured else 'IMMUTABLE_BASELINE_COMPARISON',
      checkpoint_access=0,retained_event06_access=0,native_work=0,full_result_success='NOT_QUALIFIED')
    h=save_record(area/'suite-result.json',summary)
    return dict(result='PASS',case_id=case_id,distinct_cases=len(results),actual_api_calls=summary['actual_api_calls'],
                artifact=case_id+'/suite-result.json',artifact_sha256=h)
