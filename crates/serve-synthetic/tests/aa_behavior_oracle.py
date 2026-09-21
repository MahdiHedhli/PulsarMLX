#!/usr/bin/env python3
"""Precommitted behavioral expectations; never inspect target source text."""
import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import threading

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class Stream:
    def __init__(self,admitted=True,failure=None,close_error=False):
        self.admission_gate=threading.Event();self.closed=threading.Event();self.failure=failure;self.close_error=close_error
        if admitted:self.admission_gate.set()
    def __iter__(self):
        if self.failure:raise self.failure
        if not self.admission_gate.wait(1):raise RuntimeError('fake admission stalled')
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(role='assistant'))])
        if not self.closed.wait(1):raise RuntimeError('fake close stalled')
    def close(self):
        self.closed.set()
        if self.close_error:raise RuntimeError('fake close failure')

def busy(sdk,status=429,code='server_busy',kind='rate_limit_error',cls=None):
    response=sdk.httpx.Response(status,request=sdk.httpx.Request('POST','http://127.0.0.1:1/v1/chat/completions'))
    return (cls or sdk.openai.RateLimitError)('synthetic oracle',response=response,body={'error':{'code':code,'type':kind}})

def expect_error(call,code,marker):
    try:call()
    except AssertionError as error:assert str(error)==code,marker
    else:raise AssertionError(marker)

class StubHolder:
    def __init__(self,sdk):self.sdk=sdk;self.admitted=False;self.release=threading.Event();self.events=[]
    def await_admission(self):self.admitted=True;self.events.append('admission')
    def ensure_active(self):
        if not self.admitted or self.release.is_set():raise self.sdk.InvalidContentionExperiment('HOLDER_RELEASED')
    def note(self,event):self.events.append(event)

def execute(case,sdk,membership):
    if case in ['omitted_admission','premature_release','genuine_busy','success_while_held','early_release']:
        holder=StubHolder(sdk)
        def contender():raise busy(sdk)
        if case=='success_while_held':
            expect_error(lambda:sdk.perform_contention(holder,lambda:None),'CONTENDER_SUCCEEDED_WHILE_HELD','AA_SUCCESS_WHILE_HELD_ACCEPTED');return
        if case=='early_release':
            holder.release.set();expect_error(lambda:sdk.perform_contention(holder,contender),'HOLDER_RELEASED','AA_EARLY_RELEASE_ACCEPTED');return
        marker='AA_ADMISSION_WAIT_OMITTED' if case=='omitted_admission' else 'AA_HOLDER_RELEASED_BEFORE_CONTENDER'
        try:sdk.perform_contention(holder,contender)
        except AssertionError:raise AssertionError(marker) from None
        assert holder.events==['admission','contender_started','contender_response'],marker
        return
    if case in ['weakened_busy','wrong_status','wrong_code','wrong_class']:
        variants={'weakened_busy':(busy(sdk,kind='server_error'),'CONTENDER_WRONG_BUSY_TYPE','AA_WRONG_BUSY_TYPE_ACCEPTED'),'wrong_status':(busy(sdk,status=503),'CONTENDER_WRONG_BUSY_STATUS','AA_WRONG_BUSY_STATUS_ACCEPTED'),'wrong_code':(busy(sdk,code='other'),'CONTENDER_WRONG_BUSY_CODE','AA_WRONG_BUSY_CODE_ACCEPTED'),'wrong_class':(busy(sdk,cls=sdk.openai.InternalServerError),'CONTENDER_WRONG_ERROR_CLASS','AA_WRONG_ERROR_CLASS_ACCEPTED')}
        error,code,marker=variants[case];expect_error(lambda:sdk.validate_busy_error(error),code,marker);return
    if case=='metadata_failure_absence':
        def runner(*args,**kwargs):return SimpleNamespace(returncode=17,stdout='{}')
        try:membership.verify_production_workspace_membership(runner)
        except RuntimeError as error:assert str(error)=='WORKSPACE_METADATA_FAILED','AA_METADATA_FAILURE_ACCEPTED'
        else:raise AssertionError('AA_METADATA_FAILURE_ACCEPTED')
        return
    if case in ['swallowed_failure','lost_finally','failure_before_admission','failure_after_admission','delayed_admission','cancellation','close_error','lease_expired']:
        stream=Stream(admitted=case!='delayed_admission',failure=RuntimeError('fake holder failure') if case in ['swallowed_failure','lost_finally','failure_before_admission'] else None,close_error=case in ['lost_finally','close_error'])
        if case=='failure_after_admission':
            class AfterStream(Stream):
                def __iter__(self):
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(role='assistant'))])
                    raise RuntimeError('fake failure after admission')
            stream=AfterStream()
        sdk.chat=lambda *args,**kwargs:stream
        holder=sdk.ContentionHolder(object());holder.start()
        try:
            if case=='delayed_admission':
                assert holder.started.wait(.5),'AA_DELAY_NOT_STARTED';assert not holder.admitted.wait(.02),'AA_DELAY_FALSE_ADMISSION'
                expect_error(lambda:holder.await_admission(.01),'holder did not acknowledge admission','AA_DELAY_FALSE_ADMISSION')
                stream.admission_gate.set();holder.await_admission(.5)
            elif case in ['cancellation','close_error','lease_expired']:
                holder.await_admission(.5)
                if case=='lease_expired':
                    sdk.time=SimpleNamespace(monotonic=lambda:holder.request_started+3)
                    expect_error(holder.ensure_active,'HOLDER_LEASE_WINDOW_EXPIRED','AA_EXPIRED_LEASE_ACCEPTED')
            else:
                holder.thread.join(1);assert not holder.thread.is_alive(),'AA_HOLDER_THREAD_NOT_JOINED'
                assert isinstance(holder.failure,RuntimeError),'AA_HOLDER_FAILURE_SWALLOWED'
                assert holder.finished.is_set(),'AA_FINALLY_SIGNAL_LOST'
                if case in ['failure_before_admission','failure_after_admission']:
                    phase='before' if case=='failure_before_admission' else 'after'
                    expect_error(lambda:holder.await_admission(.01),'holder failed '+phase+' admission: RuntimeError','AA_HOLDER_FAILURE_SWALLOWED')
                return
        finally:
            if holder.thread.is_alive():
                try:holder.close()
                except AssertionError as error:
                    if case!='close_error':raise
                    assert str(error)=='holder failed: RuntimeError','AA_CLOSE_ERROR_HIDDEN'
        assert holder.finished.is_set(),'AA_FINALLY_SIGNAL_LOST';assert stream.closed.is_set(),'AA_CANCEL_NOT_CLOSED';assert not holder.thread.is_alive(),'AA_HOLDER_THREAD_NOT_JOINED'
        if case=='close_error':assert isinstance(holder.failure,RuntimeError),'AA_CLOSE_ERROR_HIDDEN'
        return
    raise ValueError('unknown behavioral case')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--client',type=Path,required=True);parser.add_argument('--membership',type=Path,required=True);parser.add_argument('--case',required=True);args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parent));execute(args.case,load('aa_sdk',args.client),load('aa_membership',args.membership));print('AA_ORACLE_PASS '+args.case)
if __name__=='__main__':main()
