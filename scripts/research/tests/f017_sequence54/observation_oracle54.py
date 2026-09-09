"""Independent transcript oracle for S54; imports no producer or reducer."""
import hashlib
import json
import os
from pathlib import Path
import stat
FIELDS = ('attempts', 'requested_bytes', 'successful_returns', 'error_returns',
          'short_returns', 'zero_returns', 'returned_bytes')
PURPOSES = ('FORMAT_PROBE', 'NUMERICAL_PAYLOAD')

def expected_rows(transcript):
    rows = [dict(shard_ordinal=s, purpose=p, **dict.fromkeys(FIELDS, 0))
            for s in range(2, 7) for p in PURPOSES]
    keyed = {(r['shard_ordinal'], r['purpose']): r for r in rows}
    for call in transcript:
        r = keyed[(call['shard_ordinal'], call['purpose'])]
        assert type(call['requested_bytes']) is int and call['requested_bytes'] >= 0
        r['attempts'] += 1
        r['requested_bytes'] += call['requested_bytes']
        if call['outcome'] == 'ERROR':
            r['error_returns'] += 1
        else:
            assert call['outcome'] == 'RETURN'
            n = call['returned_bytes']
            assert type(n) is int and 0 <= n <= call['requested_bytes']
            r['successful_returns'] += 1
            r['returned_bytes'] += n
            r['short_returns'] += int(n < call['requested_bytes'])
            r['zero_returns'] += int(n == 0)
    return rows

def require_complete(observation, transcript, expected):
    assert observation['role'] == 'PRIMARY'
    for key in ('package_attempt_id', 'consumer_event_id', 'producer_measurement_sha256'):
        assert observation[key] == expected[key]
    assert observation['vocabulary_sha256'] == '9974e6531377b16398fc65d433e923789c757b21c3223d2454bd83bf0297ff43'
    assert observation['completeness'] == 'COMPLETE'
    assert observation['unknown_suffix'] is False
    assert observation['measurement_failure'] is None
    actual = observation['totals']
    assert type(actual) is list and len(actual) == 10
    assert actual == expected_rows(transcript)
    for row in actual:
        assert set(row) == set(FIELDS) | {'shard_ordinal', 'purpose'}
        for key in FIELDS:
            assert type(row[key]) is int and row[key] >= 0
    assert observation['validated_prefix_counters'] == actual
    assert observation['last_durable_boundary'] is not None
    assert observation['receipt_sha256'] is not None
    assert observation['terminal_sha256'] is not None
    return True

def require_incomplete(observation):
    assert observation['completeness'] == 'INCOMPLETE'
    assert observation['totals'] is None
    assert observation['unknown_suffix'] is True
    assert observation['measurement_failure'] is not None
    return True

BINDINGS=('role','package_attempt_id','consumer_event_id','producer_measurement_sha256',
          'vocabulary_sha256','measurement_implementation_sha256','descriptor_set_sha256')
FILES=('f017_primary_read_observation_v1.py','f017_corrected_oracle_primary_target_source_v10.py',
       'f017_corrected_oracle_primary_target_source_v11.py','f017_corrected_oracle_primary_wrapper_v11.py')

def canon(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def read_canonical(path):
    st=path.stat(follow_symlinks=False)
    assert stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid() and st.st_size<=32768
    raw=path.read_bytes()
    def unique(pairs):
        result={}
        for k,v in pairs:
            assert k not in result
            result[k]=v
        return result
    value=json.loads(raw,object_pairs_hook=unique)
    assert canon(value)==raw
    return value,hashlib.sha256(raw).hexdigest()

def implementation_binding(code_view):
    parent=Path(code_view)/'scripts/research'
    return hashlib.sha256(canon({name:hashlib.sha256((parent/name).read_bytes()).hexdigest() for name in FILES})).hexdigest()

def verify_durable(directory,attachment,transcript,expected,code_view,outcome='RETURNED',stage='COMPLETE',phases=()):
    """Read actual raw chain independently; never call producer reader/reducer."""
    require_complete(attachment,transcript,expected)
    directory=Path(directory)/'primary-read-observations'
    binding=dict(role='PRIMARY',**{key:expected[key] for key in ('package_attempt_id','consumer_event_id','producer_measurement_sha256','descriptor_set_sha256')},
        vocabulary_sha256='9974e6531377b16398fc65d433e923789c757b21c3223d2454bd83bf0297ff43',
        measurement_implementation_sha256=implementation_binding(code_view))
    assert all(attachment[k]==v for k,v in binding.items())
    names=sorted(p.name for p in directory.iterdir())
    record_names=[n for n in names if n.startswith('record-')]
    assert record_names==['record-'+str(i).zfill(8)+'.json' for i in range(1,len(record_names)+1)]
    assert set(names)==set(record_names)|{'observation-receipt.json','observation-terminal.json'}
    previous=None;last=None;completed=0;pending=None;finished=False;observed_phases=[]
    for sequence,name in enumerate(record_names,1):
        rec,digest=read_canonical(directory/name)
        assert set(rec)==set(BINDINGS)|{'schema','sequence','previous_sha256','boundary','counters','pending'}
        assert rec['schema']=='pulsarmlx.f017.primary-read-observation-record/1.0.0'
        assert type(rec['sequence']) is int and rec['sequence']==sequence
        assert rec['previous_sha256']==previous and not finished
        assert all(rec[k]==v for k,v in binding.items())
        boundary=rec['boundary']
        if sequence==1:
            assert boundary=='OWNER_STARTED' and rec['pending'] is None and completed==0
        elif boundary=='READ_INTENT':
            assert pending is None and completed<len(transcript)
            call=transcript[completed]
            pending={k:call[k] for k in ('shard_ordinal','purpose','requested_bytes')}
            assert canon(rec['pending'])==canon(pending)
        elif boundary in ('READ_RETURN','READ_ERROR'):
            assert pending is not None
            call=transcript[completed]
            assert boundary==('READ_ERROR' if call['outcome']=='ERROR' else 'READ_RETURN')
            completed+=1;pending=None
        else:
            assert boundary in ('PHASE_CORE','PHASE_CORE_COMPLETE','PHASE_BANK','OWNER_FINISHED')
            assert pending is None
            if boundary.startswith('PHASE_'):observed_phases.append(boundary)
            if boundary=='OWNER_FINISHED':
                assert pending is None and completed==len(transcript)
                finished=True
        assert canon(rec['pending'])==canon(pending)
        assert canon(rec['counters'])==canon(expected_rows(transcript[:completed]))
        previous=digest;last=dict(sequence=sequence,sha256=digest,boundary=boundary)
    assert finished and completed==len(transcript) and canon(attachment['last_durable_boundary'])==canon(last)
    assert tuple(observed_phases)==tuple(phases)
    receipt,rh=read_canonical(directory/'observation-receipt.json')
    terminal,th=read_canonical(directory/'observation-terminal.json')
    assert set(receipt)==set(BINDINGS)|{'schema','numerical_outcome','diagnostic_stage','completeness','unknown_suffix','measurement_failure','last_durable_boundary','totals','validated_prefix_counters'}
    assert set(terminal)==set(BINDINGS)|{'schema','receipt_sha256','last_durable_boundary','completeness'}
    assert receipt['schema']=='pulsarmlx.f017.primary-read-observation-receipt/1.0.0'
    assert terminal['schema']=='pulsarmlx.f017.primary-read-observation-terminal/1.0.0'
    assert all(receipt[k]==v and terminal[k]==v for k,v in binding.items())
    assert receipt['numerical_outcome']==outcome and receipt['diagnostic_stage']==stage
    assert receipt['completeness']==terminal['completeness']=='COMPLETE'
    assert receipt['unknown_suffix'] is False and receipt['measurement_failure'] is None
    assert canon(receipt['last_durable_boundary'])==canon(terminal['last_durable_boundary'])==canon(last)
    assert canon(receipt['totals'])==canon(receipt['validated_prefix_counters'])==canon(expected_rows(transcript))
    assert rh==terminal['receipt_sha256']==attachment['receipt_sha256'] and th==attachment['terminal_sha256']
    return dict(result='PASS',records=len(record_names),resolved_api_calls=completed,receipt_sha256=rh,terminal_sha256=th)

def verify_prefix(directory,attachment,transcript,expected,code_view,pending_intent=None):
    """Validate claimed incomplete prefix against independent actual API calls.

    This never treats a visible last file as proof that its fsync/readback
    succeeded. The caller separately requires the owner attachment and bounds
    standalone-reader prefix length by that known owner-confirmed boundary.
    """
    require_incomplete(attachment)
    last=attachment['last_durable_boundary']
    if last is None:
        assert attachment['validated_prefix_counters']==[]
        return dict(result='PASS',resolved_api_calls=0,prefix='ABSENT_UNKNOWN')
    directory=Path(directory)/'primary-read-observations'
    binding=dict(role='PRIMARY',**{key:expected[key] for key in ('package_attempt_id','consumer_event_id','producer_measurement_sha256','descriptor_set_sha256')},
        vocabulary_sha256='9974e6531377b16398fc65d433e923789c757b21c3223d2454bd83bf0297ff43',
        measurement_implementation_sha256=implementation_binding(code_view))
    assert all(attachment[k]==v for k,v in binding.items())
    assert type(last['sequence']) is int and last['sequence']>0
    previous=None;completed=0;pending=None;final=None
    for seq in range(1,last['sequence']+1):
        rec,digest=read_canonical(directory/('record-'+str(seq).zfill(8)+'.json'))
        assert set(rec)==set(BINDINGS)|{'schema','sequence','previous_sha256','boundary','counters','pending'}
        assert rec['schema']=='pulsarmlx.f017.primary-read-observation-record/1.0.0'
        assert type(rec['sequence']) is int and rec['sequence']==seq and rec['previous_sha256']==previous
        assert all(rec[k]==v for k,v in binding.items())
        boundary=rec['boundary']
        if seq==1:assert boundary=='OWNER_STARTED' and rec['pending'] is None
        elif boundary=='READ_INTENT':
            assert pending is None
            call=transcript[completed] if completed<len(transcript) else pending_intent
            assert call is not None
            pending={k:call[k] for k in ('shard_ordinal','purpose','requested_bytes')}
        elif boundary in ('READ_RETURN','READ_ERROR'):
            assert pending is not None and completed<len(transcript)
            call=transcript[completed]
            assert boundary==('READ_ERROR' if call['outcome']=='ERROR' else 'READ_RETURN')
            completed+=1;pending=None
        else:
            assert boundary in ('PHASE_CORE','PHASE_CORE_COMPLETE','PHASE_BANK','OWNER_FINISHED') and pending is None
        assert canon(rec['pending'])==canon(pending)
        assert canon(rec['counters'])==canon(expected_rows(transcript[:completed]))
        previous=digest;final=dict(sequence=seq,sha256=digest,boundary=boundary)
    assert canon(last)==canon(final)
    assert canon(attachment['validated_prefix_counters'])==canon(expected_rows(transcript[:completed]))
    return dict(result='PASS',resolved_api_calls=completed,prefix='EXACT_CLAIMED_PREFIX_UNKNOWN_SUFFIX')
