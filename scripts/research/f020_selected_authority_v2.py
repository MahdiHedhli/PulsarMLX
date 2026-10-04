#!/usr/bin/env python3
"""Exact-version source/build review validation; no model or numerical operations."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SCHEMA = 'pulsarmlx.selected-execution-review/2'
MAX_DOCUMENT = 16*1024*1024


def require(ok, message):
    if not ok:
        raise ValueError('AUTHORITY: '+message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'duplicate JSON key')
        out[k]=v
    return out


def strict(raw):
    def invalid(_):raise ValueError('AUTHORITY: nonfinite JSON')
    require(len(raw)<=MAX_DOCUMENT,'document budget')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)


def bounded(path, maximum=MAX_DOCUMENT, private=False):
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as f:
        a=os.fstat(f.fileno())
        require(stat.S_ISREG(a.st_mode) and a.st_size<=maximum,'bounded regular file')
        if private:
            require(a.st_uid==os.getuid() and not a.st_mode&0o077,'private owner/mode')
        raw=f.read(maximum+1)
        b=os.fstat(f.fileno())
        require(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k) for k in
            ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode')),'descriptor mutation')
        return raw


def file_sha(path, maximum):
    # Streaming hash for executable/native library provenance, not model data.
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as f:
        a=os.fstat(f.fileno())
        require(stat.S_ISREG(a.st_mode) and 0<a.st_size<=maximum,'hash file bound')
        h=hashlib.sha256();count=0
        while True:
            raw=f.read(256*1024)
            if not raw:break
            count+=len(raw);require(count<=maximum,'hash growth');h.update(raw)
        b=os.fstat(f.fileno())
        require(count==a.st_size and all(getattr(a,k)==getattr(b,k) for k in
            ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')),'hash descriptor mutation')
        return h.hexdigest()


def confined(repo,relative):
    p=Path(relative)
    require(not p.is_absolute() and p.parts and all(v not in ('..','.') for v in p.parts),'source path')
    result=repo/p
    require(result.resolve().is_relative_to(repo.resolve()),'source escaped repository')
    return result


def provider_verdict(raw):
    provider=strict(raw)
    require(provider.get('type')=='result' and provider.get('subtype')=='success'
            and provider.get('is_error') is False,'invalid provider response')
    models=provider.get('modelUsage')
    require(type(models) is dict and set(models)=={'claude-opus-5-5'},'actual reviewer model')
    usage=models['claude-opus-5-5']
    require(type(usage) is dict and type(usage.get('outputTokens')) is int and usage['outputTokens']>0,'model usage evidence')
    result=provider.get('result');require(type(result) is str,'provider result')
    result=result.strip()
    if result.startswith('```json\n') and result.endswith('\n```'):result=result[8:-4]
    verdict=strict(result.encode())
    require(verdict.get('schema')==SCHEMA and verdict.get('decision')=='ACCEPT'
            and type(verdict.get('blockers')) is int and verdict['blockers']==0,'final ACCEPT/zero blockers required')
    require(type(verdict.get('assessed')) is dict,'assessed descriptor')
    return verdict


def check_documents(capsule_raw,review_raw,expected_capsule_sha,expected_review_sha):
    """Pure parser validation, separately testable without any authority issuance."""
    require(sha(capsule_raw)==expected_capsule_sha and sha(review_raw)==expected_review_sha,'raw review/capsule digest')
    capsule=strict(capsule_raw)
    require(capsule.get('schema')==SCHEMA and capsule.get('purpose')=='FINAL_EXECUTION_REVIEW','not final execution review')
    d=capsule.get('descriptor');require(type(d) is dict,'descriptor')
    require(d.get('pre_review_selected_numerical_observations')==0
            and type(d.get('pre_review_selected_numerical_observations')) is int,'pre-review observation boundary')
    verdict=provider_verdict(review_raw)
    require(verdict['assessed']==d,'exact assessed version/build')
    population=capsule.get('synthetic_population')
    require(type(population) is dict and type(population.get('text')) is str,'reviewed synthetic population')
    require(sha(population['text'].encode())==population.get('sha256')==d.get('population_sha256'),
            'reviewed synthetic population digest')
    files=capsule.get('source_files');require(type(files) is dict and bool(files),'complete source capsule')
    require(set(files)==set(d.get('source_sha256',{})),'source file coverage')
    for name,record in files.items():
        require(type(record) is dict and type(record.get('text')) is str,'source text')
        require(sha(record['text'].encode())==record.get('sha256')==d['source_sha256'][name],'source bytes/hash')
    require(sha(canonical(d['source_sha256']))==d.get('package_sha256'),'source package digest')
    for key in ('commit','tree','executable_sha256','contract_sha256','population_sha256','input_sha256','build'):
        require(key in d,'missing descriptor '+key)
    return d


def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()


def verify_current(repo,capsule_path,review_path,capsule_sha,review_sha,executable,contract,population,input_path):
    """No caller-supplied pass flag; hashes bound to actual raw provider/capsule."""
    d=check_documents(bounded(capsule_path),bounded(review_path),capsule_sha,review_sha)
    A_build=d['build']
    require(sys.flags.optimize==A_build['interpreter_optimize']==0,'interpreter optimization mode')
    require(sys.version==A_build['interpreter_version'],'interpreter version')
    require(file_sha(Path(sys._base_executable).resolve(),128*1024*1024)==A_build['interpreter_sha256'],'interpreter executable')
    repo=Path(repo).resolve()
    require(git(repo,'rev-parse','HEAD')==d['commit'] and git(repo,'rev-parse','HEAD^{tree}')==d['tree'],'current source version')
    require(git(repo,'status','--porcelain')=='','clean exact source')
    for name,want in d['source_sha256'].items():
        require(sha(bounded(confined(repo,name)))==want,'current source digest '+name)
        require(git(repo,'ls-files','--error-unmatch','--',name)==name,'uncommitted package file')
    require(file_sha(Path(executable).resolve(),256*1024*1024)==d['executable_sha256'],'current executable')
    require(sha(bounded(contract))==d['contract_sha256'],'contract binding')
    require(sha(bounded(population))==d['population_sha256'],'population binding')
    require(sha(bounded(input_path,16384))==d['input_sha256'],'original input binding')
    return d
