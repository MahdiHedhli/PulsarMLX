"""Independent comparisons and mechanism-specific mutation classification."""
import math
class NumericMismatch(AssertionError):pass
class TemplateMismatch(AssertionError):pass
class HarnessFailure(AssertionError):pass

def flatten(value):
    if isinstance(value,list):
        for item in value:yield from flatten(item)
    else:yield value

def close(actual,expected,atol,rtol,code):
    def shape(x):
        if not isinstance(x,list):return ()
        return (len(x),shape(x[0]) if x else ())
    if shape(actual)!=shape(expected):raise NumericMismatch(code+': shape')
    a,b=list(flatten(actual)),list(flatten(expected))
    if len(a)!=len(b) or any(not math.isfinite(x) for x in a+b):raise NumericMismatch(code+': nonfinite/count')
    errors=[abs(x-y) for x,y in zip(a,b)]
    if any(e>atol+rtol*abs(y) for e,y in zip(errors,b)):raise NumericMismatch(code+': values')
    return {'count':len(a),'max_abs':max(errors,default=0),'rmse':math.sqrt(sum(e*e for e in errors)/max(1,len(errors)))}

def exact(actual,expected,code,template=False):
    if actual!=expected:raise (TemplateMismatch if template else NumericMismatch)(code)

def classify(operation,spec):
    """An unexpected exception is observable failure, never a killed mutant."""
    try:operation()
    except Exception as exc:
        observed=type(exc).__module__+'.'+type(exc).__name__
        message=str(exc)
        match=observed==spec['exception_type'] and all(fragment in message for fragment in spec['message_contains'])
        return {'outcome':'INTENDED_REJECTION' if match else 'HARNESS_FAILURE',
                'exception_type':observed,'message':message,'expected_type':spec['exception_type'],
                'expected_message_contains':spec['message_contains'],'boundary':spec['boundary']}
    return {'outcome':'SURVIVOR','exception_type':None,'message':None,'boundary':spec['boundary']}
