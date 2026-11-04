// Production core shared verbatim by the platform wrapper and host C ABI tests.
#pragma once
#include <mlx/c/array.h>
#include <mlx/c/device.h>
#include <mlx/c/error.h>
#include <mlx/c/memory.h>
#include <mlx/c/ops.h>
#include <mlx/c/stream.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <unistd.h>
extern "C" size_t pa_page();
extern "C" size_t pa_max_buffer();
namespace pa {
enum Function : uint64_t { None, Open, Register, DropSlot, Input, Prepare, Project,
                          CopyControl, Memory, ResetPeak, Retire, Close, Sync };
enum Stage : uint64_t { Begin, Device, Stream, StreamIndex, MemoryLimit, CacheLimit,
  ClearCache, ResetPeakStage, Synchronize, ImportParent, ParentIdentity, ImportWeight,
  Slice, Reshape, ViewEval, ViewIdentity, ImportScales, ImportBiases, CastScales,
  CastBiases, FreeRawScales, FreeRawBiases, ImportInput, Shape, Qmm, Evaluate,
  CopyOutput, FreeOutput, FreeFlat, FreeWeight, FreeScales, FreeBiases, FreeInput,
  FreeParent, FreeStream, FreeDevice, ActiveMemory, CacheMemory, PeakMemory, CopyImport,
  CopyIdentity, CopyFree, End };
enum Refusal : uint64_t { NoRefusal, InvalidInput, PriorFailure, NonemptyDestination,
  DuplicateHandle, AccountingFull, EmptyResult, NativeStatus, ErrorCallback,
  Exception, UnknownHandle, EvidenceWrite, InvalidResult };
enum Category { Other, Parent, View, Output };
static std::atomic<uint64_t> errors{0};
// First writer owns this bounded buffer. Readers never touch an in-flight write.
// No allocation, lock, native/pool call, exception or unbounded string scan.
static std::atomic<unsigned> error_state{0};
static char first_error[256]{};
static uint64_t first_error_category=0,error_truncated=0;
static void capture_error(const char* text,uint64_t category) noexcept {
  unsigned expected=0;
  if(!error_state.compare_exchange_strong(expected,1))return;
  size_t i=0;
  if(text){for(;i<255 && text[i];++i)first_error[i]=text[i];error_truncated=(i==255 && text[i]!=0);}
  first_error[i]=0;first_error_category=category;
  error_state.store(2,std::memory_order_release);
}
static void handler(const char* text,void*) noexcept {errors.fetch_add(1);capture_error(text,1);}
struct Trace {
  bool enabled=false;int fd=-1;bool write_failed=false;
  uint64_t function=0,stage=0,phase=0,refusal=0,failed_function=0,failed_stage=0;
  int status=0;bool status_known=false;
  uint64_t qmm_enter=0,qmm_return=0,eval_attempt=0,eval_complete=0,sync_complete=0;
  uint64_t retire_enter=0,retire_complete=0,close_complete=0,records=0;
};
static Trace trace;
struct Handle {void* ctx=nullptr;Category category=Other;};
struct Context {
  mlx_device device{nullptr};mlx_stream stream{nullptr};mlx_array parent{nullptr};
  mlx_array w[2]{{nullptr},{nullptr}},s[2]{{nullptr},{nullptr}},b[2]{{nullptr},{nullptr}},x[2]{{nullptr},{nullptr}};
  Handle handles[32]{};
  size_t live=0,created=0,freed=0,pc=0,pf=0,vc=0,vf=0,oc=0,of=0;
  int stream_id=-1;bool adopted=false,failed=false;
};
static Context* active=nullptr; // single owner; snapshot runs on the owner thread
static void record(Function fn,Stage st,unsigned phase,int status=0,bool known=false) noexcept {
  if(!trace.enabled)return;
  trace.function=fn;trace.stage=st;trace.phase=phase;trace.status=status;trace.status_known=known;
  if(trace.records++>=1024){trace.write_failed=true;return;}
  char line[192];int n=std::snprintf(line,sizeof(line),
    "{\"function\":%llu,\"stage\":%llu,\"phase\":%u,\"mlx_status\":%d,\"mlx_status_known\":%s,\"bridge_refusal\":%llu}\n",
    static_cast<unsigned long long>(fn),static_cast<unsigned long long>(st),phase,status,
    known?"true":"false",static_cast<unsigned long long>(trace.refusal));
  if(n<=0 || n>=static_cast<int>(sizeof(line)) || trace.fd<0 ||
     ::write(trace.fd,line,static_cast<size_t>(n))!=n)trace.write_failed=true;
}
static bool refuse(Context* c,Function fn,Stage st,Refusal reason) noexcept {
  if(c)c->failed=true;
  if(trace.enabled && !trace.refusal){trace.refusal=reason;trace.failed_function=fn;trace.failed_stage=st;
    const bool actual_return=trace.function==fn && trace.stage==st && trace.phase==2;
    record(fn,st,3,trace.status,actual_return && trace.status_known);}
  return false;
}
static bool ready(Context* c,Function fn,Stage st) noexcept {
  if(!c || c->failed || errors.load())return refuse(c,fn,st,PriorFailure);
  if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  return true;
}
static bool account(Context* c,mlx_array a,Category cat,Function fn,Stage st) noexcept {
  if(!a.ctx)return true; // empty placeholders are not live allocations
  for(auto &h:c->handles)if(h.ctx==a.ctx)return refuse(c,fn,st,DuplicateHandle);
  for(auto &h:c->handles)if(!h.ctx){h={a.ctx,cat};++c->live;++c->created;
    if(cat==Parent)++c->pc;else if(cat==View)++c->vc;else if(cat==Output)++c->oc;return true;}
  return refuse(c,fn,st,AccountingFull);
}
template<class F> static bool call(Context* c,Function fn,Stage st,F operation) noexcept {
  if(!ready(c,fn,st))return false;
  record(fn,st,1);if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  int status;
  try{status=operation();}
  catch(const std::exception& e){capture_error(e.what(),2);record(fn,st,2);return refuse(c,fn,st,Exception);}
  catch(...){capture_error("non-standard C++ exception",3);record(fn,st,2);return refuse(c,fn,st,Exception);}
  record(fn,st,2,status,true);
  if(status)return refuse(c,fn,st,NativeStatus);
  if(errors.load())return refuse(c,fn,st,ErrorCallback);
  if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  return true;
}
template<class F> static bool inspect(Context* c,Function fn,Stage st,F query) noexcept {
  if(!ready(c,fn,st))return false;
  record(fn,st,1);if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  bool valid=false;
  try{valid=query();}
  catch(const std::exception& e){capture_error(e.what(),2);record(fn,st,2);return refuse(c,fn,st,Exception);}
  catch(...){capture_error("non-standard C++ exception",3);record(fn,st,2);return refuse(c,fn,st,Exception);}
  record(fn,st,2);
  if(errors.load())return refuse(c,fn,st,ErrorCallback);
  if(!valid)return refuse(c,fn,st,InvalidResult);
  if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  return true;
}
template<class F> static bool produce(Context* c,mlx_array& out,Category cat,Function fn,Stage st,F operation,bool has_status=true) noexcept {
  if(!ready(c,fn,st))return false;
  if(out.ctx)return refuse(c,fn,st,NonemptyDestination);
  record(fn,st,1);if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  int status=0;bool returned=false;
  try{status=operation();returned=true;}
  catch(const std::exception& e){capture_error(e.what(),2);}
  catch(...){capture_error("non-standard C++ exception",3);}
  // Partial handles remain accounted even on error/exception. No guessed cleanup.
  bool counted=account(c,out,cat,fn,st);record(fn,st,2,status,returned && has_status);
  if(!counted)return false;
  if(!returned)return refuse(c,fn,st,Exception);
  if(status)return refuse(c,fn,st,NativeStatus);
  if(errors.load())return refuse(c,fn,st,ErrorCallback);
  if(!out.ctx)return refuse(c,fn,st,EmptyResult);
  if(trace.write_failed)return refuse(c,fn,st,EvidenceWrite);
  return true;
}
static bool release(Context* c,mlx_array& a,Function fn,Stage st) noexcept {
  if(!ready(c,fn,st))return false;
  if(!a.ctx)return true;
  Handle* found=nullptr;for(auto &h:c->handles)if(h.ctx==a.ctx)found=&h;
  if(!found)return refuse(c,fn,st,UnknownHandle);
  if(!call(c,fn,st,[&]{return mlx_array_free(a);}))return false;
  if(found->category==Parent)++c->pf;else if(found->category==View)++c->vf;else if(found->category==Output)++c->of;
  found->ctx=nullptr;a.ctx=nullptr;--c->live;++c->freed;return true;
}
static bool sync(Context* c,Function fn) noexcept {
  if(!call(c,fn,Synchronize,[&]{return mlx_synchronize(c->stream);}))return false;
  if(trace.enabled)++trace.sync_complete;return true;
}
static bool drop_slot(Context* c,size_t slot,Function fn) noexcept {
  if(slot>=2)return refuse(c,fn,Begin,InvalidInput);
  return sync(c,fn) && release(c,c->w[slot],fn,FreeWeight) && release(c,c->s[slot],fn,FreeScales) &&
    release(c,c->b[slot],fn,FreeBiases) && release(c,c->x[slot],fn,FreeInput);
}
}
// One diagnostic file, borrowed until final snapshot; timing routes never enable it.
extern "C" int pa_diagnostic_enable(int fd) noexcept {
  if(pa::active || pa::trace.enabled || fd<0 || pa::errors.load())return 1;
  pa::trace.enabled=true;pa::trace.fd=fd;return 0;
}
extern "C" int pa_diagnostic_snapshot(uint64_t* out,size_t count,char* error,size_t cap) noexcept {
  if(!out || count!=40 || !error || cap!=256)return 1;
  using namespace pa;std::memset(out,0,40*sizeof(uint64_t));std::memset(error,0,cap);
  out[0]=trace.enabled;out[1]=trace.function;out[2]=trace.stage;out[3]=trace.phase;
  out[4]=trace.status_known;out[5]=static_cast<uint64_t>(static_cast<int64_t>(trace.status));
  out[6]=trace.refusal;out[7]=trace.failed_function;out[8]=trace.failed_stage;out[9]=errors.load();
  out[10]=error_state.load(std::memory_order_acquire);
  if(out[10]==2){std::memcpy(error,first_error,256);out[11]=first_error_category;out[12]=error_truncated;}
  out[13]=trace.qmm_enter;out[14]=trace.qmm_return;out[15]=trace.eval_attempt;out[16]=trace.eval_complete;
  out[17]=trace.sync_complete;out[18]=trace.retire_enter;out[19]=trace.retire_complete;out[20]=trace.close_complete;
  out[21]=active!=nullptr;out[22]=trace.write_failed;out[23]=trace.records;
  if(active){const auto c=active;out[24]=c->created;out[25]=c->freed;out[26]=c->live;
    out[27]=c->pc;out[28]=c->pf;out[29]=c->vc;out[30]=c->vf;out[31]=c->oc;out[32]=c->of;
    out[33]=c->parent.ctx!=nullptr;out[34]=c->failed;
    for(size_t i=0;i<2;++i)out[35+i]=static_cast<uint64_t>(c->w[i].ctx!=nullptr) |
      (static_cast<uint64_t>(c->s[i].ctx!=nullptr)<<1) | (static_cast<uint64_t>(c->b[i].ctx!=nullptr)<<2) |
      (static_cast<uint64_t>(c->x[i].ctx!=nullptr)<<3);}
  return 0; // no native APIs or cleanup
}
extern "C" void* pa_open() noexcept {
  using namespace pa;if(active || errors.load() || trace.refusal)return nullptr;
  try{mlx_set_error_handler(handler,nullptr,nullptr);active=new Context;auto c=active;
    if(!inspect(c,Open,Device,[&]{c->device=mlx_device_new_type(MLX_GPU,0);return c->device.ctx!=nullptr;}) ||
       !call(c,Open,Device,[&]{return mlx_set_default_device(c->device);}) ||
       !inspect(c,Open,Stream,[&]{c->stream=mlx_stream_new_device(c->device);return c->stream.ctx!=nullptr;}) ||
       !call(c,Open,StreamIndex,[&]{return mlx_stream_get_index(&c->stream_id,c->stream);}))return nullptr;
    size_t old=0;
    if(!call(c,Open,MemoryLimit,[&]{return mlx_set_memory_limit(&old,32*1024*1024);}) ||
       !call(c,Open,CacheLimit,[&]{return mlx_set_cache_limit(&old,32*1024*1024);}) ||
       !call(c,Open,ClearCache,[]{return mlx_clear_cache();}) ||
       !call(c,Open,ResetPeakStage,[]{return mlx_reset_peak_memory();}))return nullptr;
    return c;
  }catch(const std::exception& e){capture_error(e.what(),2);refuse(active,Open,Begin,Exception);return nullptr;}
   catch(...){capture_error("non-standard C++ exception",3);refuse(active,Open,Begin,Exception);return nullptr;}
}
extern "C" int pa_stream(void* p){return static_cast<pa::Context*>(p)->stream_id;}
extern "C" int pa_sync(void* p){return pa::sync(static_cast<pa::Context*>(p),pa::Sync)?0:1;}
extern "C" int pa_register(void* p,void* bytes,size_t length,void* token,void(*callback)(void*),bool raw_bad_length) noexcept {
  using namespace pa;auto c=static_cast<Context*>(p);size_t page=pa_page();
  if(!ready(c,Register,Begin))return 1;
  if(c->parent.ctx || !page || !bytes || reinterpret_cast<uintptr_t>(bytes)%page || length%page ||
     length>pa_max_buffer() || length/4>INT32_MAX || length<4){refuse(c,Register,Begin,InvalidInput);return 2;}
  int n=static_cast<int>(length/4)-(raw_bad_length?1:0);
  if(!produce(c,c->parent,Parent,Register,ImportParent,[&]{c->parent=mlx_array_new_data_managed_payload(bytes,&n,1,MLX_UINT32,token,callback);return 0;},false))return 3;
  if(!inspect(c,Register,ParentIdentity,[&]{c->adopted=mlx_array_data_uint32(c->parent)==bytes;return c->adopted;}))return 4;
  return 0;
}
extern "C" int pa_drop_slot(void* p,size_t slot){return pa::drop_slot(static_cast<pa::Context*>(p),slot,pa::DropSlot)?0:1;}
extern "C" int pa_input(void* p,size_t slot,const void* data,int m,int k){
  using namespace pa;auto c=static_cast<Context*>(p);
  if(slot>=2 || m<=0 || k<=0 || !data){refuse(c,Input,Begin,InvalidInput);return 1;}
  int shape[2]={m,k};return produce(c,c->x[slot],Other,Input,ImportInput,[&]{c->x[slot]=mlx_array_new_data(data,shape,2,MLX_FLOAT32);return 0;},false)?0:1;
}
extern "C" int pa_prepare(void* p,size_t slot,const void* w,const void* s,const void* b,
    size_t offset,int n,int k,int bits,bool adopted,bool diagnostic,int metadata) noexcept {
  using namespace pa;auto c=static_cast<Context*>(p);
  if(slot>=2 || n<=0 || k<=0 || (bits!=4 && bits!=8) || k%64 || k>INT32_MAX/8 || !w || !s || !b || (metadata!=0 && metadata!=1)){
    refuse(c,Prepare,Begin,InvalidInput);return 1;}
  if(!drop_slot(c,slot,Prepare))return 1;
  int shape[2]={n,k*bits/32},meta[2]={n,k/64};
  if(adopted){size_t length=static_cast<size_t>(n)*static_cast<size_t>(shape[1]);
    if(!c->adopted || offset%4 || offset/4>INT32_MAX || length>static_cast<size_t>(INT32_MAX)-offset/4 ||
       !inspect(c,Prepare,Shape,[&]{auto bytes=mlx_array_nbytes(c->parent);return offset<=bytes && length<=(bytes-offset)/4;})){
      refuse(c,Prepare,Shape,InvalidInput);return 2;}
    int begin=static_cast<int>(offset/4),end=begin+static_cast<int>(length),stride=1;mlx_array flat{nullptr};
    if(!produce(c,flat,View,Prepare,Slice,[&]{return mlx_slice(&flat,c->parent,&begin,1,&end,1,&stride,1,c->stream);}))return 3;
    if(!produce(c,c->w[slot],View,Prepare,Reshape,[&]{return mlx_reshape(&c->w[slot],flat,shape,2,c->stream);}) ||
       !release(c,flat,Prepare,FreeFlat))return 3;
    if(diagnostic){
      if(!call(c,Prepare,ViewEval,[&]{return mlx_array_eval(c->w[slot]);}) || !sync(c,Prepare))return 3;
      if(!inspect(c,Prepare,ViewIdentity,[&]{const auto ptr=mlx_array_data_uint32(c->w[slot]);const auto strides=mlx_array_strides(c->w[slot]);
        return ptr && strides && ptr==w && strides[0]==static_cast<size_t>(shape[1]) && strides[1]==1 &&
          mlx_array_ndim(c->w[slot])==2 && mlx_array_dim(c->w[slot],0)==n && mlx_array_dim(c->w[slot],1)==shape[1] &&
          mlx_array_dtype(c->w[slot])==MLX_UINT32;}))return 4;}
  }else if(!produce(c,c->w[slot],View,Prepare,ImportWeight,[&]{c->w[slot]=mlx_array_new_data(w,shape,2,MLX_UINT32);return 0;},false))return 3;
  const mlx_dtype dt=metadata==0?MLX_BFLOAT16:MLX_FLOAT16;mlx_array rs{nullptr},rb{nullptr};
  if(!produce(c,rs,Other,Prepare,ImportScales,[&]{rs=mlx_array_new_data(s,meta,2,dt);return 0;},false) ||
     !produce(c,rb,Other,Prepare,ImportBiases,[&]{rb=mlx_array_new_data(b,meta,2,dt);return 0;},false) ||
     !produce(c,c->s[slot],Other,Prepare,CastScales,[&]{return mlx_astype(&c->s[slot],rs,MLX_FLOAT32,c->stream);}) ||
     !produce(c,c->b[slot],Other,Prepare,CastBiases,[&]{return mlx_astype(&c->b[slot],rb,MLX_FLOAT32,c->stream);}) ||
     !release(c,rs,Prepare,FreeRawScales) || !release(c,rb,Prepare,FreeRawBiases))return 3;
  return 0;
}
extern "C" int pa_project(void* p,size_t slot,int m,int n,int k,int bits,float* output) noexcept {
  using namespace pa;auto c=static_cast<Context*>(p);if(!ready(c,Project,Begin))return 1;
  if(slot>=2 || m<=0 || n<=0 || k<=0 || (bits!=4 && bits!=8) || k>INT32_MAX/8 || !output ||
     !c->w[slot].ctx || !c->s[slot].ctx || !c->b[slot].ctx || !c->x[slot].ctx){refuse(c,Project,Begin,InvalidInput);return 1;}
  if(!inspect(c,Project,Shape,[&]{return mlx_array_ndim(c->w[slot])==2 && mlx_array_dim(c->w[slot],0)==n && mlx_array_dim(c->w[slot],1)==k*bits/32;}))return 2;
  mlx_array out{nullptr};
  if(!produce(c,out,Output,Project,Qmm,[&]{if(trace.enabled)++trace.qmm_enter;
    int status=mlx_quantized_matmul(&out,c->x[slot],c->w[slot],c->s[slot],c->b[slot],true,{64,true},{bits,true},"affine",c->stream);
    if(trace.enabled)++trace.qmm_return;return status;}))return 3;
  if(trace.enabled)++trace.eval_attempt;
  if(!call(c,Project,Evaluate,[&]{return mlx_array_eval(out);}))return 3;
  if(trace.enabled)++trace.eval_complete;
  if(!sync(c,Project))return 3;
  if(!inspect(c,Project,CopyOutput,[&]{const float* data=mlx_array_data_float32(out);
    if(!data || errors.load() || mlx_array_ndim(out)!=2 || mlx_array_dim(out,0)!=m || mlx_array_dim(out,1)!=n)return false;
    std::memcpy(output,data,static_cast<size_t>(m)*n*4);return true;}))return 4;
  return release(c,out,Project,FreeOutput)?0:3;
}
extern "C" int pa_copy_control(void* p,const void* source,size_t bytes){
  using namespace pa;auto c=static_cast<Context*>(p);
  if(bytes%4 || bytes/4>INT32_MAX || !source){refuse(c,CopyControl,Begin,InvalidInput);return 2;}
  int shape=static_cast<int>(bytes/4);mlx_array a{nullptr};
  if(!produce(c,a,Other,CopyControl,CopyImport,[&]{a=mlx_array_new_data(source,&shape,1,MLX_UINT32);return 0;},false))return 3;
  return inspect(c,CopyControl,CopyIdentity,[&]{return mlx_array_data_uint32(a)!=source;}) &&
    release(c,a,CopyControl,CopyFree) && sync(c,CopyControl) && call(c,CopyControl,ClearCache,[]{return mlx_clear_cache();}) &&
    call(c,CopyControl,ResetPeakStage,[]{return mlx_reset_peak_memory();}) ? 0:1;
}
extern "C" int pa_memory(void* p,size_t* out){using namespace pa;auto c=static_cast<Context*>(p);
  return out && call(c,Memory,ActiveMemory,[&]{return mlx_get_active_memory(out);}) &&
    call(c,Memory,CacheMemory,[&]{return mlx_get_cache_memory(out+1);}) && call(c,Memory,PeakMemory,[&]{return mlx_get_peak_memory(out+2);}) ? 0:1;}
extern "C" int pa_reset_peak(){return pa::call(pa::active,pa::ResetPeak,pa::ResetPeakStage,[]{return mlx_reset_peak_memory();})?0:1;}
extern "C" int pa_retire(void* p,size_t* counts){using namespace pa;auto c=static_cast<Context*>(p);
  if(!ready(c,Retire,Begin) || !counts)return 1;
  if(trace.enabled)++trace.retire_enter;
  if(!sync(c,Retire) || !drop_slot(c,0,Retire) || !drop_slot(c,1,Retire) || !release(c,c->parent,Retire,FreeParent))return 1;
  counts[0]=c->created;counts[1]=c->freed;counts[2]=c->live;counts[3]=c->pc;counts[4]=c->pf;
  counts[5]=c->vc;counts[6]=c->vf;counts[7]=c->oc;counts[8]=c->of;
  if(c->live){refuse(c,Retire,End,UnknownHandle);return 1;}
  if(trace.enabled)++trace.retire_complete;return 0;
}
extern "C" int pa_close(void* p){using namespace pa;auto c=static_cast<Context*>(p);
  if(!ready(c,Close,Begin) || c->live || !sync(c,Close))return 1;
  if(!call(c,Close,FreeStream,[&]{return mlx_stream_free(c->stream);}) || !call(c,Close,FreeDevice,[&]{return mlx_device_free(c->device);}) ||
     !call(c,Close,ClearCache,[]{return mlx_clear_cache();}))return 1;
  if(trace.enabled)++trace.close_complete;active=nullptr;delete c;return 0;
}
