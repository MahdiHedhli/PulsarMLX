"""Shape-aware comparisons and exact intended-mechanism classification."""
import math
class ComparisonError(AssertionError):pass
class HarnessFailure(AssertionError):pass
def shape(x):
    if type(x) is not list:return ()
    children=[shape(v) for v in x]
    if children and any(s!=children[0] for s in children):raise ComparisonError('RECTANGULAR_SHAPE_REQUIRED')
    return (len(x),)+(children[0] if children else ())
def flat(x):return [v for row in x for v in flat(row)] if type(x) is list else [x]
def rows(x):return [x] if type(x[0]) is not list else [v for r in x for v in rows(r)]
def close(actual,expected,atol,rtol,code):
    if shape(actual)!=shape(expected):raise ComparisonError(code+': shape')
    a,b=flat(actual),flat(expected)
    if len(a)!=len(b) or not all(type(v) in (float,int) and math.isfinite(v) for v in a+b):raise ComparisonError(code+': nonfinite/type/count')
    differences=[abs(x-y) for x,y in zip(a,b)]
    if any(d>atol+rtol*abs(y) for d,y in zip(differences,b)):raise ComparisonError(code+': numerical difference')
    return {'count':len(a),'max_abs':max(differences,default=0),'rmse':math.sqrt(sum(d*d for d in differences)/len(a)) if a else 0}
def compare_router(ids,scores,reference,atol=4e-5,rtol=4e-6,wrong_id_association=False):
    wanted=tuple(reference['output_shape'])
    if shape(ids)!=wanted or shape(scores)!=wanted:raise ComparisonError('ROUTER_OUTPUT_MISMATCH: shape')
    comparisons=[]
    for actual_ids,actual_scores,expected in zip(rows(ids),rows(scores),reference['rows']):
        if not all(type(i) is int for i in actual_ids) or len(set(actual_ids))!=len(actual_ids) or set(actual_ids)!=set(expected['selected_ids']):raise ComparisonError('ROUTER_OUTPUT_MISMATCH: expert identities')
        lookup=actual_ids[1:]+actual_ids[:1] if wrong_id_association else actual_ids
        values=[expected['scores_by_id'][str(i)] for i in lookup]
        comparisons.append(close(actual_scores,values,atol,rtol,'ROUTER_OUTPUT_MISMATCH'))
    return comparisons
def classify(operation,spec):
    try:operation()
    except Exception as exc:
        name=type(exc).__module__+'.'+type(exc).__name__;message=str(exc)
        intended=name==spec['exception_type'] and all(t in message for t in spec['message_contains'])
        return {'outcome':'INTENDED_REJECTION' if intended else 'HARNESS_FAILURE','exception_type':name,'message':message,'expected_type':spec['exception_type'],'expected_message_contains':spec['message_contains'],'boundary':spec['boundary']}
    return {'outcome':'SURVIVOR','expected_type':spec['exception_type'],'expected_message_contains':spec['message_contains'],'boundary':spec['boundary']}
