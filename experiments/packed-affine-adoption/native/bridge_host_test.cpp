// Host-only C ABI: no MLX implementation, frameworks, native libraries or child.
// Compile against the actual pinned public C headers, then include production core.
#include <mlx/c/array.h>
#include <mlx/c/device.h>
#include <mlx/c/error.h>
#include <mlx/c/memory.h>
#include <mlx/c/ops.h>
#include <mlx/c/stream.h>
#include <algorithm>
#include <cassert>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>
#ifndef PA_CORE_INCLUDE
#define PA_CORE_INCLUDE "adoption_bridge_core.h"
#endif
#include PA_CORE_INCLUDE

namespace fake {
struct Storage {std::vector<unsigned char> bytes;void* borrowed=nullptr;void* token=nullptr;void(*done)(void*)=nullptr;~Storage(){if(done)done(token);}};
struct Array {std::shared_ptr<Storage> storage;std::vector<int> shape;std::vector<size_t> strides;size_t offset=0;mlx_dtype dtype;};
std::map<void*,std::unique_ptr<Array>> arrays;
std::vector<std::string> calls;
std::string fault_op,fault_kind;int fault_n=1,seen=0;
mlx_error_handler_func handler=nullptr;void* handler_data=nullptr;
size_t creates=0,frees=0;int callbacks=0;
void callback(void*){++callbacks;}
size_t width(mlx_dtype d){return d==MLX_BFLOAT16 || d==MLX_FLOAT16?2:4;}
Array& get(mlx_array a){assert(a.ctx && arrays.count(a.ctx));return *arrays.at(a.ctx);}
std::string enter(const char* name){calls.emplace_back(name);if(fault_op==name && ++seen==fault_n)return fault_kind;return {};}
mlx_array make(const int* dims,size_t count,mlx_dtype dt,const void* data=nullptr){
 auto a=std::make_unique<Array>();a->dtype=dt;a->shape.assign(dims,dims+count);a->strides.resize(count);size_t size=1;
 for(size_t i=count;i>0;--i){a->strides[i-1]=size;size*=dims[i-1];}
 a->storage=std::make_shared<Storage>();a->storage->bytes.resize(size*width(dt));
 if(data)std::memcpy(a->storage->bytes.data(),data,a->storage->bytes.size());
 void* key=a.get();arrays.emplace(key,std::move(a));++creates;return {key};
}
int complete(const std::string& fault){
 if(fault=="callback"){handler("fake ABI error callback",handler_data);return 0;}
 if(fault=="throw")throw std::runtime_error("fake producer exception");
 return fault=="partial"?17:0;
}
bool skip(const std::string& fault){return fault=="before" || fault=="empty";}
int skip_status(const std::string& f){return f=="before"?17:0;}
void* data(mlx_array a){auto& x=get(a);return static_cast<unsigned char*>(x.storage->borrowed?x.storage->borrowed:x.storage->bytes.data())+x.offset;}
void fault(const char* op,const std::string& kind,int nth=1){fault_op=op;fault_kind=kind;fault_n=nth;seen=0;}
size_t count(const char* op){return std::count(calls.begin(),calls.end(),op);}
}
extern "C" {
size_t pa_page(){return 4096;}
size_t pa_max_buffer(){return 1<<20;}
void mlx_set_error_handler(mlx_error_handler_func h,void* d,void(*)(void*)){fake::handler=h;fake::handler_data=d;}
mlx_device mlx_device_new_type(mlx_device_type,int){static int d;return {&d};}
int mlx_set_default_device(mlx_device){return 0;}
mlx_stream mlx_stream_new_device(mlx_device){static int s;return {&s};}
int mlx_stream_get_index(int* i,mlx_stream){*i=0;return 0;}
int mlx_device_free(mlx_device){return 0;}
int mlx_stream_free(mlx_stream){return 0;}
int mlx_set_memory_limit(size_t* r,size_t n){assert(n==32*1024*1024);*r=0;return 0;}
int mlx_set_cache_limit(size_t* r,size_t n){assert(n==32*1024*1024);*r=0;return 0;}
int mlx_clear_cache(){return 0;}
int mlx_reset_peak_memory(){return 0;}
int mlx_get_active_memory(size_t* r){*r=0;return 0;}
int mlx_get_cache_memory(size_t* r){*r=0;return 0;}
int mlx_get_peak_memory(size_t* r){*r=0;return 0;}
int mlx_synchronize(mlx_stream){auto f=fake::enter("sync");return f.empty()?0:17;}
mlx_array mlx_array_new(){return {nullptr};} // pinned API's real empty-output contract
mlx_array mlx_array_new_data(const void* data,const int* shape,int n,mlx_dtype d){
 auto f=fake::enter("import");if(fake::skip(f)){fake::handler("fake import refused",fake::handler_data);return {nullptr};}
 auto a=fake::make(shape,n,d,data);if(!f.empty())fake::handler("fake partial import",fake::handler_data);return a;
}
mlx_array mlx_array_new_data_managed_payload(void* data,const int* shape,int n,mlx_dtype d,void* token,void(*done)(void*)){
 auto a=fake::make(shape,n,d);auto& x=fake::get(a);x.storage->borrowed=data;x.storage->token=token;x.storage->done=done;return a;
}
int mlx_array_free(mlx_array a){auto f=fake::enter("free");if(!f.empty())return 17;assert(fake::arrays.erase(a.ctx)==1);++fake::frees;return 0;}
size_t mlx_array_ndim(mlx_array a){return fake::get(a).shape.size();}
int mlx_array_dim(mlx_array a,int dim){return fake::get(a).shape.at(dim);}
mlx_dtype mlx_array_dtype(mlx_array a){return fake::get(a).dtype;}
const size_t* mlx_array_strides(mlx_array a){return fake::get(a).strides.data();}
size_t mlx_array_nbytes(mlx_array a){auto& x=fake::get(a);size_t n=fake::width(x.dtype);for(int d:x.shape)n*=d;return n;}
const uint32_t* mlx_array_data_uint32(mlx_array a){return static_cast<const uint32_t*>(fake::data(a));}
const float* mlx_array_data_float32(mlx_array a){fake::enter("copy-data");return static_cast<const float*>(fake::data(a));}
int mlx_array_eval(mlx_array){return fake::enter("eval").empty()?0:17;}
int mlx_astype(mlx_array* out,mlx_array a,mlx_dtype d,mlx_stream){
 assert(!out->ctx);auto f=fake::enter("cast");if(fake::skip(f))return fake::skip_status(f);
 auto& x=fake::get(a);*out=fake::make(x.shape.data(),x.shape.size(),d);return fake::complete(f);
}
int mlx_slice(mlx_array* out,mlx_array a,const int* start,size_t,const int* stop,size_t,const int*,size_t,mlx_stream){
 assert(!out->ctx);auto f=fake::enter("slice");if(fake::skip(f))return fake::skip_status(f);
 auto& x=fake::get(a);int n=*stop-*start;*out=fake::make(&n,1,x.dtype);auto& y=fake::get(*out);y.storage=x.storage;y.offset=x.offset+*start*4;return fake::complete(f);
}
int mlx_reshape(mlx_array* out,mlx_array a,const int* shape,size_t n,mlx_stream){
 assert(!out->ctx);auto f=fake::enter("reshape");if(fake::skip(f))return fake::skip_status(f);
 auto& x=fake::get(a);*out=fake::make(shape,n,x.dtype);auto& y=fake::get(*out);y.storage=x.storage;y.offset=x.offset;return fake::complete(f);
}
int mlx_quantized_matmul(mlx_array* out,mlx_array x,mlx_array w,mlx_array,mlx_array,bool,mlx_optional_int,mlx_optional_int,const char*,mlx_stream){
 assert(!out->ctx);auto f=fake::enter("qmm");if(fake::skip(f))return fake::skip_status(f);
 int shape[]={fake::get(x).shape[0],fake::get(w).shape[0]};*out=fake::make(shape,2,MLX_FLOAT32);return fake::complete(f);
}
}

int main(int argc,char** argv){
 assert(argc==3);std::string test=argv[1];
 int fd=open(argv[2],O_CREAT|O_EXCL|O_WRONLY,0600);assert(fd>=0);
#ifndef PA_OLD_CORE
 assert(pa_diagnostic_enable(fd)==0);
#endif
 alignas(4096) unsigned char weights[4096]{};uint16_t scales[8]{},biases[8]{};float input[64]{},output[4]{};
 void* c=pa_open();assert(c);
 auto prepare=[&](bool adopted){return pa_prepare(c,0,weights,scales,biases,0,4,64,4,adopted,true,0);};
 auto project=[&]{return pa_project(c,0,1,4,64,4,output);};
#ifdef PA_OLD_CORE
 int status=prepare(false);std::cout<<"old copied status="<<status<<" casts="<<fake::count("cast")<<"\n";
 // The same success expectation used below fails on immutable old source.
 return status==0 && fake::count("cast")==2?0:42;
#else
 using namespace pa;
 auto snapshot=[&]{uint64_t v[40];char error[256];assert(pa_diagnostic_snapshot(v,40,error,256)==0);return std::vector<uint64_t>(v,v+40);};
 auto suppressed=[&]{auto n=fake::calls.size();size_t counts[9]{};assert(project()!=0);assert(pa_retire(c,counts)!=0);assert(pa_close(c)!=0);assert(fake::calls.size()==n);};
 if(test=="copied" || test=="adopted"){
  bool adopted=test=="adopted";
  if(adopted)assert(pa_register(c,weights,sizeof(weights),nullptr,fake::callback,false)==0);
  assert(prepare(adopted)==0);assert(fake::count("cast")==2);assert(fake::count("free")==static_cast<size_t>(adopted?3:2));
  assert(fake::callbacks==0);auto s=snapshot();assert(s[24]==static_cast<uint64_t>(adopted?7:5));assert(s[26]==static_cast<uint64_t>(adopted?4:3));
  assert(pa_input(c,0,input,1,64)==0);size_t begin=fake::calls.size();assert(project()==0);
  std::vector<std::string> expected={"qmm","eval","sync","copy-data","free"};
  assert(std::vector<std::string>(fake::calls.begin()+begin,fake::calls.end())==expected);
  s=snapshot();assert(s[13]==1 && s[14]==1 && s[15]==1 && s[16]==1);
  size_t counts[9]{};assert(pa_retire(c,counts)==0);assert(counts[0]==counts[1] && counts[2]==0);
  for(size_t i:{3,5,7})assert(counts[i]==counts[i+1]);assert(fake::callbacks==int(adopted));
  assert(fake::arrays.empty());assert(pa_close(c)==0);s=snapshot();assert(s[18]==1 && s[19]==1 && s[20]==1);
 }else if(test=="reuse" || test=="duplicate"){
  assert(prepare(false)==0);auto ctx=static_cast<Context*>(c);auto n=fake::calls.size();auto count=ctx->created;
  if(test=="reuse")assert(!produce(ctx,ctx->w[0],View,Prepare,ImportWeight,[&]{assert(false);return 0;}));
  else assert(!account(ctx,ctx->w[0],View,Prepare,ImportWeight));
  assert(ctx->created==count && fake::calls.size()==n);assert(trace.refusal==(test=="reuse"?NonemptyDestination:DuplicateHandle));suppressed();
 }else if(test=="error-bound"){
  std::string text(400,'x');handler(text.c_str(),nullptr);handler("second",nullptr);
  uint64_t v[40];char error[256];assert(pa_diagnostic_snapshot(v,40,error,256)==0);
  assert(v[9]==2 && v[11]==1 && v[12]==1 && std::strlen(error)==255 && error[0]=='x');suppressed();
 }else if(test=="evidence"){
  close(fd);assert(prepare(false)!=0);assert(trace.refusal==EvidenceWrite);suppressed();
 }else{
  const auto split=test.find(':');assert(split!=std::string::npos);std::string op=test.substr(0,split),kind=test.substr(split+1);
  Stage stage=Begin;bool adopted=op=="slice" || op=="reshape";int status=0;size_t before_creates=0;
  if(adopted){assert(pa_register(c,weights,sizeof(weights),nullptr,fake::callback,false)==0);stage=op=="slice"?Slice:Reshape;fake::fault(op.c_str(),kind);status=prepare(true);}
  else if(op=="import" || op=="import-scales" || op=="import-biases"){
   int nth=op=="import"?1:op=="import-scales"?2:3;stage=nth==1?ImportWeight:nth==2?ImportScales:ImportBiases;
   fake::fault("import",kind,nth);status=prepare(false);}
  else if(op=="cast" || op=="cast-bias"){stage=op=="cast"?CastScales:CastBiases;fake::fault("cast",kind,op=="cast"?1:2);status=prepare(false);}
  else{assert(prepare(false)==0);
   if(op=="input"){stage=ImportInput;fake::fault("import",kind);status=pa_input(c,0,input,1,64);}
   else {assert(pa_input(c,0,input,1,64)==0);before_creates=fake::creates;
   if(op=="retire"){stage=FreeWeight;fake::fault("free",kind);size_t counts[9]{};status=pa_retire(c,counts);}
   else{stage=op=="qmm"?Qmm:op=="eval"?Evaluate:op=="free-output"?FreeOutput:Synchronize;fake::fault(op=="free-output"?"free":op.c_str(),kind);status=project();}
   }
  }
  assert(status!=0);assert(trace.failed_stage==stage);assert(fake::creates==static_cast<Context*>(c)->created);
  if(op=="qmm"){
   assert(trace.qmm_enter==1 && trace.qmm_return==static_cast<uint64_t>(kind!="throw"));
   assert(trace.eval_attempt==0 && fake::count("copy-data")==0);
   assert(fake::creates-before_creates==static_cast<size_t>(kind!="before" && kind!="empty"));
  }
  if(kind=="empty")assert(trace.refusal==EmptyResult);
  if(kind=="callback")assert(trace.refusal==ErrorCallback && trace.status==0 && trace.status_known);
  if(kind=="throw")assert(trace.refusal==Exception && !trace.status_known && first_error_category==2);
  if(op=="retire")assert(trace.retire_enter==1 && trace.retire_complete==0);
  suppressed();
 }
 std::cout<<"PASS host-only "<<test<<" creates="<<fake::creates<<" frees="<<fake::frees<<"\n";
 close(fd);return 0;
#endif
}
