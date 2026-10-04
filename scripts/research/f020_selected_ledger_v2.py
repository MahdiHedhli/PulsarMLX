#!/usr/bin/env python3
"""Fixed private one-attempt authority; no reset, deletion, or caller root option."""
import json
import os
from pathlib import Path
import pwd
import stat
import f020_selected_authority_v2 as A
from f020_selected_process_v2 import private_json

RELATIVE_ROOT=Path('Library/Application Support/PulsarMLX-handoff/20261004-real-expert-numerical-execution/native-attempt-04/real-ledgers')


def root():
    # OS account database home; changing HOME or cap.out cannot move authority.
    return Path(pwd.getpwuid(os.getuid()).pw_dir)/RELATIVE_ROOT


def directory(descriptor,binding):
    identity={k:descriptor[k] for k in ('commit','contract_sha256')}
    identity['snapshot_sha256']=binding['snapshot_sha256']
    return root()/A.sha(A.canonical(identity))


def capability_sha(cap):
    issued={k:v for k,v in cap.items() if k!='pre_admission'}
    raw=(json.dumps(issued,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
    return A.sha(raw)


def private_directory(path):
    s=path.lstat()
    A.require(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and s.st_mode&0o077==0,'private ledger directory')


def issue(cap,descriptor,binding):
    parent=root();parent.mkdir(mode=0o700,parents=True,exist_ok=True);private_directory(parent)
    path=directory(descriptor,binding);path.mkdir(mode=0o700,exist_ok=False)
    record={'schema':'pulsarmlx.selected-real-attempt/2','capability_sha256':capability_sha(cap),
            'commit':descriptor['commit'],'contract_sha256':descriptor['contract_sha256'],
            'snapshot_sha256':binding['snapshot_sha256']}
    private_json(path/'ledger.json',record)
    return record


def verify(cap,descriptor,binding):
    private_directory(root());path=directory(descriptor,binding);private_directory(path)
    raw=A.bounded(path/'ledger.json',private=True);record=A.strict(raw)
    A.require(record['schema']=='pulsarmlx.selected-real-attempt/2' and record['capability_sha256']==capability_sha(cap)
              and record['commit']==descriptor['commit'] and record['contract_sha256']==descriptor['contract_sha256']
              and record['snapshot_sha256']==binding['snapshot_sha256'],'issued real capability ledger')
    return path,record,A.sha(raw)


def begin_reference(cap,descriptor,binding):
    path,record,digest=verify(cap,descriptor,binding)
    A.require(not (path/'native-start.json').exists(),'no previous native attempt')
    private_json(path/'reference-start.json',{'schema':'pulsarmlx.selected-real-start/2','phase':'reference',
        'ledger_sha256':digest,'capability_sha256':record['capability_sha256']})
