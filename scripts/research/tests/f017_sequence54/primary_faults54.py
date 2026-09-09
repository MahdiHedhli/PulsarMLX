"""Fixed S54 measurement fault campaign; all project imports occur post-seal.

Faults alter test API/measurement I/O outcomes, never supply producer counters.
No production storage capability, numerical patch, or replay is introduced.
"""
import errno
import hashlib
import json
import os
from pathlib import Path

def clone(value):return json.loads(json.dumps(value))

def fault_case(area,label,view):
    import primary_suite54 as suite
    import observation_oracle54 as oracle
    import f017_primary_read_observation_v1 as obs
    import f017_corrected_oracle_primary_target_source_v11 as target
    c=suite.Case(area,label,view,suite.basic_records())
    owner=None;saved={};faults=[];other_owner=None
    try:
        source,g,t,p,owner=suite.measured_source(c,target,obs)
        before=len(c.transcript)
        # Establish the healthy measured prefix before injecting a selected fault.
        # A pre-existing invalid owner must never count as exercising that edge.
        assert owner.failure is None and owner.directory_fd is not None and not owner.finished
        assert source._observation_owner is owner and before==2
        assert owner.last is not None and owner.last['boundary']=='READ_RETURN'
        if label=='MISSING_OWNER':source._observation_owner=None
        elif label=='DELETED_OWNER':del source._observation_owner
        elif label=='INVALID_OWNER':source._observation_owner=object()
        elif label=='OWNER_SPLICE':
            other_dir=c.area/'other-observations';other_dir.mkdir(mode=0o700)
            other_ids=dict(c.authority,package_attempt_id=c.ids['package_attempt_id']+'-OTHER',
                consumer_event_id=c.ids['consumer_event_id']+'-OTHER')
            other_candidate=dict(c.candidate,package_attempt_id=other_ids['package_attempt_id'],
                primary_event_id=other_ids['consumer_event_id'])
            other_owner=obs._start_primary_observation(other_candidate,c.identities,other_dir,other_ids)
            source._observation_owner=other_owner
        elif label=='RECORD_SPLICE':source.records['v']=dict(source.records['v'])
        elif label=='PURPOSE_SPLICE':source.records['v']['purpose']='FORMAT_PROBE'
        elif label=='LOST_COMPLETION':
            saved['return']=target.historical._read_return
            def lose(*args):faults.append('RETURN_TRANSPORT_INTERRUPTED')
            target.historical._read_return=lose
        elif label=='PENDING_BEFORE_CALL':
            record=source.records['v'];ident=source.handles[2][0]
            obs._read_intent(owner,source,record,ident,16)
        else:
            saved['bank']=obs._bank_record;saved['encode']=obs._encode_record
            def bank(fd,leaf,value):
                selected=(leaf=='observation-receipt.json' if label.startswith('RECEIPT_') else
                          leaf=='observation-terminal.json' if label.startswith('TERMINAL_') else
                          value.get('boundary')=='READ_RETURN' if label in ('RETURN_WRITE','OVERFLOW','RETURN_FSYNC','RETURN_READBACK') else
                          value.get('boundary')=='READ_INTENT')
                if not selected or faults:return saved['bank'](fd,leaf,value)
                faults.append(label)
                if label in ('INTENT_WRITE','RETURN_WRITE','RECEIPT_WRITE','TERMINAL_WRITE'):
                    raise OSError(errno.EIO,'S54 fixed measurement writer fault')
                original_write=obs.os.write;original_sync=obs.os.fsync;original_read=obs._read_record
                original_open=obs.os.open
                def short_write(out,data):
                    original_write(out,bytes(data[:1]));return 0
                def sync_fail(out):raise OSError(errno.EIO,'S54 fsync fault')
                def read_fail(d,l):raise OSError(errno.EIO,'S54 descriptor-relative readback fault')
                def open_fail(path,*args,**kwargs):
                    if path==leaf and kwargs.get('dir_fd')==fd:raise OSError(errno.EIO,'S54 exclusive open fault')
                    return original_open(path,*args,**kwargs)
                def overflow(v):return saved['encode']({**v,'synthetic_overflow_probe':'x'*32768})
                try:
                    if label=='SHORT_WRITE':obs.os.write=short_write
                    elif label in ('FSYNC','RETURN_FSYNC','RECEIPT_FSYNC','TERMINAL_FSYNC'):obs.os.fsync=sync_fail
                    elif label in ('READBACK','RETURN_READBACK'):obs._read_record=read_fail
                    elif label=='OPEN_FAIL':obs.os.open=open_fail
                    elif label=='OVERFLOW':obs._encode_record=overflow
                    else:raise AssertionError('unregistered fixed persistence fault')
                    return saved['bank'](fd,leaf,value)
                finally:
                    obs.os.write=original_write;obs.os.fsync=original_sync;obs._read_record=original_read
                    obs.os.open=original_open;obs._encode_record=saved['encode']
            obs._bank_record=bank
        if label=='PENDING_BEFORE_CALL':
            value=None;assert len(c.transcript)==before
        else:
            value=source.vector('v',4)
            assert value==[1.,2.,-3.,4.] and len(c.transcript)==before+1
        original_attachment=None;original_readback=None
        if label in ('MISSING_OWNER','DELETED_OWNER','INVALID_OWNER','OWNER_SPLICE'):
            # Finalize the owning durable prefix separately, then inspect the
            # actual invalid source owner. Neither may be labeled exact totals.
            original_attachment=obs._finish_primary_observation(owner,'RETURNED','COMPLETE')
            oracle.require_incomplete(original_attachment)
            oracle.verify_prefix(c.observations,original_attachment,c.transcript,c.expected,view)
            original_readback=obs._read_primary_observation(c.observations,c.expected)
            oracle.require_incomplete(original_readback)
            oracle.verify_prefix(c.observations,original_readback,c.transcript,c.expected,view)
            assert original_readback['last_durable_boundary']==original_attachment['last_durable_boundary']
            attachment=obs._finish_primary_observation(getattr(source,'_observation_owner',None),'RETURNED','COMPLETE')
            oracle.require_incomplete(source.primary_read_observation)
        else:attachment=obs._finish_primary_observation(owner,'RETURNED','COMPLETE')
        oracle.require_incomplete(attachment)
        pending_intent=dict(shard_ordinal=2,purpose='NUMERICAL_PAYLOAD',requested_bytes=16) if label=='PENDING_BEFORE_CALL' else None
        if label not in ('MISSING_OWNER','DELETED_OWNER','INVALID_OWNER','OWNER_SPLICE'):
            oracle.verify_prefix(c.observations,attachment,c.transcript,c.expected,view,pending_intent)
            readback=obs._read_primary_observation(c.observations,c.expected)
            if label=='TERMINAL_FSYNC':
                # Visible complete bytes cannot reveal that terminal fsync failed.
                # The original owner remains INCOMPLETE and is never upgraded.
                oracle.verify_durable(c.observations,readback,c.transcript,c.expected,view)
            else:
                oracle.require_incomplete(readback)
                oracle.verify_prefix(c.observations,readback,c.transcript,c.expected,view,pending_intent)
                a=attachment['last_durable_boundary'];r=readback['last_durable_boundary']
                assert r is None or (a is not None and r['sequence']<=a['sequence'])
        else:readback=None
        assert label in ('MISSING_OWNER','DELETED_OWNER','INVALID_OWNER','OWNER_SPLICE','RECORD_SPLICE','PURPOSE_SPLICE','PENDING_BEFORE_CALL') or len(faults)==1
        return suite.bank_case(c,dict(case=label,mode='MEASUREMENT_FAULT',result='PASS',transcript=c.transcript,
          values=value,stop=None,boundary_delta=len(c.transcript)-before,observation=attachment,
          readback=readback,original_owner_attachment=original_attachment,original_owner_readback=original_readback,injected_edge=faults,
          durability_qualification='INCOMPLETE_OWNER_NEVER_UPGRADED',unknown_suffix='REQUIRED_NO_ZERO_FILL'))
    except BaseException as error:
        # Preserve actual test-memory transcript on a failing qualification case;
        # this is failed test evidence, never producer authority or a PASS.
        try:
            suite.bank_case(c,dict(case=label,mode='MEASUREMENT_FAULT_FAILURE',result='FAIL',
                transcript=list(c.transcript),values=None,
                stop=dict(type=type(error).__name__,message=str(error)),
                observation=None if owner is None else owner.attachment(),
                injected_edge=list(faults),qualification='FAILED_PARTIAL_NOT_QUALIFIED'))
        except Exception as banking_error:
            error.add_note('Failed-test evidence banking also failed: '+type(banking_error).__name__+':'+str(banking_error))
        raise
    finally:
        if 'bank' in saved:obs._bank_record=saved['bank'];obs._encode_record=saved['encode']
        if 'return' in saved:target.historical._read_return=saved['return']
        if owner is not None and not owner.finished:obs._finish_primary_observation(owner,'RAISED','COMPLETE')
        if other_owner is not None and not other_owner.finished:obs._finish_primary_observation(other_owner,'RAISED','COMPLETE')
        c.close()

def rewrite(path,value):
    import primary_suite54 as suite
    raw=suite.canonical(value);assert len(raw)<=32768
    fd=os.open(path,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
    try:
        at=0
        while at<len(raw):at+=os.write(fd,raw[at:])
        os.fsync(fd)
    finally:os.close(fd)
    return hashlib.sha256(raw).hexdigest()

def rejected(call):
    try:call()
    except (AssertionError,ValueError,TypeError,KeyError,IndexError,FileNotFoundError):return True
    return False

def wrapper_owner_case(area,label,view):
    import primary_suite54 as suite
    import observation_oracle54 as oracle
    import f017_corrected_oracle_primary_wrapper_v11 as wrapper
    c=suite.Case(area,label,view,suite.basic_records(factory=True))
    original=wrapper._start_primary_observation;exception=None
    try:
        def absent(*args):return None if label=='WRAPPER_MISSING_OWNER' else object()
        wrapper._start_primary_observation=absent
        try:wrapper._qualification_execute_target_and_bank(c.candidate,c.identities,c.fds,c.observations,**c.authority)
        except Exception as e:exception=e
        assert type(exception) is ValueError and str(exception)=='non-finite quantization scale'
        assert len(c.transcript)==2
        attachment=getattr(exception,'primary_read_observation',None)
        assert attachment is not None
        oracle.require_incomplete(attachment)
        assert attachment['last_durable_boundary'] is None and attachment['validated_prefix_counters']==[]
        assert list(c.observations.iterdir())==[]
        return suite.bank_case(c,dict(case=label,mode='WRAPPER_OWNER_FAILURE',result='PASS',
            transcript=c.transcript,values=None,stop=dict(type='ValueError',message=str(exception)),
            observation=attachment,core_execution_count=0,full_result_success='NOT_QUALIFIED'))
    finally:wrapper._start_primary_observation=original;c.close()

def corruption_case(area,label,view):
    import primary_suite54 as suite
    import observation_oracle54 as oracle
    import f017_primary_read_observation_v1 as obs
    import f017_corrected_oracle_primary_target_source_v11 as target
    c=suite.Case(area,label,view,suite.basic_records());owner=None
    try:
        source,g,t,p,owner=suite.measured_source(c,target,obs)
        value=source.vector('v',4)
        attachment=suite.completed(c,owner,obs)
        directory=c.observations/'primary-read-observations'
        original=clone(attachment);expected=clone(c.expected)
        if label in ('DROP_COUNT','DOUBLE_COUNT','WRONG_SHARD','WRONG_PURPOSE','WRONG_ROLE','CROSS_ATTEMPT','LOST_PREFIX','FALSE_COMPLETE','BOOL_COUNTER'):
            mutant=clone(attachment)
            if label=='DROP_COUNT':mutant['totals'][1]['attempts']-=1
            elif label=='DOUBLE_COUNT':mutant['totals'][1]['attempts']+=1
            elif label=='WRONG_SHARD':mutant['totals'][1]['shard_ordinal']=4
            elif label=='WRONG_PURPOSE':mutant['totals'][1]['purpose']='FORMAT_PROBE'
            elif label=='WRONG_ROLE':mutant['role']='SECONDARY'
            elif label=='CROSS_ATTEMPT':mutant['consumer_event_id']='S54-ANOTHER-ATTEMPT'
            elif label=='LOST_PREFIX':mutant['last_durable_boundary']=None
            elif label=='FALSE_COMPLETE':mutant['unknown_suffix']=True
            elif label=='BOOL_COUNTER':mutant['totals'][1]['attempts']=True
            assert rejected(lambda:oracle.verify_durable(c.observations,mutant,c.transcript,c.expected,view))
            readback=None
        else:
            records=sorted(directory.glob('record-*.json'))
            if label=='TORN_TAIL':
                fd=os.open(records[-1],os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
                try:os.write(fd,b'{"torn":');os.fsync(fd)
                finally:os.close(fd)
            elif label=='ORPHAN_RECORD':
                suite.write_fixture(directory/('record-'+str(len(records)+2).zfill(8)+'.json'),records[-1].read_bytes())
            elif label=='GAP_RECORD':
                # Rename a graph-owned synthetic observation to evidence the
                # hole while preserving its exact original bytes.
                os.rename(records[2],directory/'saved-gap-record.json')
            elif label=='DESCRIPTOR_BINDING':expected['descriptor_set_sha256']='3'*64
            elif label=='BOOL_RECEIPT':
                path=directory/'observation-receipt.json';body=json.loads(path.read_bytes())
                body['totals'][1]['attempts']=True
                digest=rewrite(path,body)
                tp=directory/'observation-terminal.json';terminal=json.loads(tp.read_bytes())
                terminal['receipt_sha256']=digest;rewrite(tp,terminal)
            elif label in ('WRONG_STAGE','WRONG_OUTCOME'):
                path=directory/'observation-receipt.json';body=json.loads(path.read_bytes())
                body['diagnostic_stage' if label=='WRONG_STAGE' else 'numerical_outcome']='BANK' if label=='WRONG_STAGE' else 'RAISED'
                digest=rewrite(path,body)
                tp=directory/'observation-terminal.json';terminal=json.loads(tp.read_bytes())
                terminal['receipt_sha256']=digest;terminal_digest=rewrite(tp,terminal)
                original.update(receipt_sha256=digest,terminal_sha256=terminal_digest)
            elif label=='CROSS_PACKAGE_RECORD':
                rec=json.loads(records[2].read_bytes());rec['package_attempt_id']='S54-OTHER-PACKAGE';rewrite(records[2],rec)
            else:raise AssertionError('fixed mutation unavailable')
            readback=obs._read_primary_observation(c.observations,expected)
            if label not in ('WRONG_STAGE','WRONG_OUTCOME'):oracle.require_incomplete(readback)
            assert rejected(lambda:oracle.verify_durable(c.observations,original,c.transcript,expected,view))
        return suite.bank_case(c,dict(case=label,mode='COUNTER_OR_DURABLE_MUTATION',result='PASS',transcript=c.transcript,
          values=value,stop=None,observation=original,mutant_rejected=True,readback=readback))
    finally:
        if owner is not None and not owner.finished:obs._finish_primary_observation(owner,'RAISED','COMPLETE')
        c.close()

FAULTS=('INTENT_WRITE','RETURN_WRITE','RECEIPT_WRITE','TERMINAL_WRITE','OPEN_FAIL','SHORT_WRITE',
        'FSYNC','READBACK','RETURN_FSYNC','RETURN_READBACK','RECEIPT_FSYNC','TERMINAL_FSYNC',
        'OVERFLOW','LOST_COMPLETION','PENDING_BEFORE_CALL','MISSING_OWNER','DELETED_OWNER','INVALID_OWNER','OWNER_SPLICE','RECORD_SPLICE','PURPOSE_SPLICE')
MUTANTS=('DROP_COUNT','DOUBLE_COUNT','WRONG_SHARD','WRONG_PURPOSE','WRONG_ROLE','CROSS_ATTEMPT',
         'LOST_PREFIX','FALSE_COMPLETE','BOOL_COUNTER','TORN_TAIL','ORPHAN_RECORD','GAP_RECORD','DESCRIPTOR_BINDING','BOOL_RECEIPT','CROSS_PACKAGE_RECORD',
         'WRONG_STAGE','WRONG_OUTCOME')

def run(area,view):
    result=[]
    for label in FAULTS:result.append(fault_case(area,label,view))
    for label in ('WRAPPER_MISSING_OWNER','WRAPPER_INVALID_OWNER'):result.append(wrapper_owner_case(area,label,view))
    for label in MUTANTS:result.append(corruption_case(area,label,view))
    return result
