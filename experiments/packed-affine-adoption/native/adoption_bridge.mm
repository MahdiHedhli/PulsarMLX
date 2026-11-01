// Private experiment ABI. Source pins and patches are inherited unchanged.
#import <Metal/Metal.h>
#include <mlx/c/array.h>
#include <mlx/c/device.h>
#include <mlx/c/error.h>
#include <mlx/c/memory.h>
#include <mlx/c/ops.h>
#include <mlx/c/stream.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <unistd.h>

static std::atomic<uint64_t> errors{0};
static void handler(const char*, void*) noexcept { errors.fetch_add(1); }
static bool ok(int s) { return s==0 && errors.load()==0; }
struct Context {
  mlx_device device{nullptr}; mlx_stream stream{nullptr}; mlx_array parent{nullptr};
  mlx_array w[2]{{nullptr},{nullptr}}, s[2]{{nullptr},{nullptr}}, b[2]{{nullptr},{nullptr}}, x[2]{{nullptr},{nullptr}};
  size_t live=0, created=0, freed=0, pc=0, pf=0, vc=0, vf=0, oc=0, of=0; int stream_id=-1; bool adopted=false;
};
static bool release(Context* c, mlx_array& a) {
  if (!a.ctx) return true;
  if (!ok(mlx_array_free(a))) return false;
  a.ctx=nullptr; --c->live; ++c->freed; return true;
}
static bool accept(Context* c, mlx_array& a) {
  // Count any nonempty handle, including an error result, before returning.
  if(a.ctx){++c->live;++c->created;}
  return a.ctx && errors.load()==0;
}
extern "C" size_t pa_page() { return static_cast<size_t>(sysconf(_SC_PAGESIZE)); }
extern "C" size_t pa_max_buffer() { @autoreleasepool { id<MTLDevice> d=MTLCreateSystemDefaultDevice();return d ? d.maxBufferLength : 0; } }
extern "C" void* pa_open() noexcept {
  try {
    mlx_set_error_handler(handler,nullptr,nullptr);
    auto c=new Context;
    c->device=mlx_device_new_type(MLX_GPU,0);
    if(!c->device.ctx || !ok(mlx_set_default_device(c->device))) return nullptr;
    c->stream=mlx_stream_new_device(c->device);
    size_t old=0;
    if(!c->stream.ctx || !ok(mlx_stream_get_index(&c->stream_id,c->stream)) ||
       !ok(mlx_set_memory_limit(&old,32*1024*1024)) || !ok(mlx_set_cache_limit(&old,32*1024*1024)) ||
       !ok(mlx_clear_cache()) || !ok(mlx_reset_peak_memory())) return nullptr;
    return c;
  } catch(...) { return nullptr; }
}
extern "C" int pa_stream(void* p) {return static_cast<Context*>(p)->stream_id;}
extern "C" int pa_sync(void* p) {return ok(mlx_synchronize(static_cast<Context*>(p)->stream))?0:1;}
extern "C" int pa_register(void* p, void* bytes, size_t length, void* token, void(*callback)(void*), bool raw_bad_length) noexcept {
  try {
    auto c=static_cast<Context*>(p);const size_t page=pa_page();
    if(c->parent.ctx || !page || reinterpret_cast<uintptr_t>(bytes)%page || length%page || length>pa_max_buffer() || length/4>INT32_MAX) return 2;
    int n=static_cast<int>(length/4)-(raw_bad_length?1:0);
    c->parent=mlx_array_new_data_managed_payload(bytes,&n,1,MLX_UINT32,token,callback);
    if(c->parent.ctx)++c->pc;
    if(!accept(c,c->parent))return 3;
    c->adopted=mlx_array_data_uint32(c->parent)==bytes && errors.load()==0;
    return c->adopted?0:4;
  } catch(...) {return 5;}
}
extern "C" int pa_drop_slot(void* p, size_t slot) {
  auto c=static_cast<Context*>(p);if(slot>=2 || pa_sync(p))return 1;
  const bool view=c->w[slot].ctx;
  if(!release(c,c->w[slot]))return 1;
  if(view)++c->vf;
  return release(c,c->s[slot]) && release(c,c->b[slot]) && release(c,c->x[slot]) ? 0:1;
}
extern "C" int pa_input(void* p, size_t slot, const void* data, int m, int k) {
  auto c=static_cast<Context*>(p);if(slot>=2||m<=0||k<=0||c->x[slot].ctx)return 1;
  int shape[2]={m,k};c->x[slot]=mlx_array_new_data(data,shape,2,MLX_FLOAT32);
  return accept(c,c->x[slot])?0:1;
}
extern "C" int pa_prepare(void* p, size_t slot, const void* w, const void* s, const void* b,
    size_t offset, int n, int k, int bits, bool adopted, bool diagnostic, int metadata) noexcept {
  try {
    auto c=static_cast<Context*>(p);
    if(slot>=2 || n<=0 || k<=0 || (bits!=4 && bits!=8) || k%64 || pa_drop_slot(p,slot))return 1;
    int shape[2]={n,k*bits/32};int meta[2]={n,k/64};
    if(adopted){
      if(!c->adopted || offset%4 || offset/4>INT32_MAX ||
         offset+static_cast<size_t>(n)*k*bits/8>mlx_array_nbytes(c->parent))return 2;
      int begin=static_cast<int>(offset/4),end=begin+n*shape[1],stride=1;
      mlx_array flat=mlx_array_new(); if(flat.ctx)++c->vc; if(!accept(c,flat))return 3;
      int st=mlx_slice(&flat,c->parent,&begin,1,&end,1,&stride,1,c->stream);
      c->w[slot]=mlx_array_new();if(c->w[slot].ctx)++c->vc;if(!accept(c,c->w[slot]) || !ok(st))return 3;
      st=mlx_reshape(&c->w[slot],flat,shape,2,c->stream);
      if(!ok(st) || !release(c,flat))return 3;++c->vf;
      if(diagnostic){
        if(!ok(mlx_array_eval(c->w[slot])) || pa_sync(p))return 3;
        const auto ptr=mlx_array_data_uint32(c->w[slot]);const auto strides=mlx_array_strides(c->w[slot]);
        if(!ptr || !strides || ptr!=w || strides[0]!=static_cast<size_t>(shape[1]) || strides[1]!=1 ||
           mlx_array_ndim(c->w[slot])!=2 || mlx_array_dim(c->w[slot],0)!=n || mlx_array_dim(c->w[slot],1)!=shape[1] || mlx_array_dtype(c->w[slot])!=MLX_UINT32 || errors.load())return 4;
      }
    } else {c->w[slot]=mlx_array_new_data(w,shape,2,MLX_UINT32);if(c->w[slot].ctx)++c->vc;if(!accept(c,c->w[slot]))return 3;}
    const mlx_dtype dt=metadata==0?MLX_BFLOAT16:MLX_FLOAT16;
    mlx_array rs=mlx_array_new_data(s,meta,2,dt),rb=mlx_array_new_data(b,meta,2,dt);
    const bool have_s=accept(c,rs),have_b=accept(c,rb);if(!have_s||!have_b)return 3;
    c->s[slot]=mlx_array_new();c->b[slot]=mlx_array_new();const bool os=accept(c,c->s[slot]),ob=accept(c,c->b[slot]);if(!os||!ob)return 3;
    if(!ok(mlx_astype(&c->s[slot],rs,MLX_FLOAT32,c->stream)) || !ok(mlx_astype(&c->b[slot],rb,MLX_FLOAT32,c->stream)))return 3;
    if(!release(c,rs)||!release(c,rb))return 3;
    return 0;
  } catch(...) {return 6;}
}
extern "C" int pa_project(void* p, size_t slot, int m, int n, int k, int bits, float* output) noexcept {
  try {
    auto c=static_cast<Context*>(p);if(slot>=2||!c->w[slot].ctx||!c->s[slot].ctx||!c->b[slot].ctx)return 1;
    if(mlx_array_ndim(c->w[slot])!=2||mlx_array_dim(c->w[slot],0)!=n||mlx_array_dim(c->w[slot],1)!=k*bits/32)return 2;
    if(!c->x[slot].ctx)return 3;mlx_array out=mlx_array_new();
    if(out.ctx)++c->oc;
    if(!accept(c,out))return 3;
    if(!ok(mlx_quantized_matmul(&out,c->x[slot],c->w[slot],c->s[slot],c->b[slot],true,{64,true},{bits,true},"affine",c->stream)) || !ok(mlx_array_eval(out)) || pa_sync(p))return 3;
    const float* data=mlx_array_data_float32(out);
    if(!data||errors.load()||mlx_array_ndim(out)!=2||mlx_array_dim(out,0)!=m||mlx_array_dim(out,1)!=n)return 4;
    std::memcpy(output,data,static_cast<size_t>(m)*n*4);
    if(!release(c,out))return 3;++c->of;
    return 0;
  } catch(...) {return 6;}
}
extern "C" int pa_copy_control(void* p, const void* source, size_t bytes) {
  auto c=static_cast<Context*>(p);if(bytes%4||bytes/4>INT32_MAX)return 2;
  int shape=static_cast<int>(bytes/4);auto a=mlx_array_new_data(source,&shape,1,MLX_UINT32);
  if(!accept(c,a))return 3;bool copied=mlx_array_data_uint32(a)!=source && errors.load()==0;
  return release(c,a) && copied && !pa_sync(p) && ok(mlx_clear_cache()) && ok(mlx_reset_peak_memory()) ? 0:1;
}
extern "C" int pa_memory(void*, size_t* out) {return ok(mlx_get_active_memory(out))&&ok(mlx_get_cache_memory(out+1))&&ok(mlx_get_peak_memory(out+2))?0:1;}
extern "C" int pa_reset_peak() {return ok(mlx_reset_peak_memory())?0:1;}
extern "C" int pa_retire(void* p, size_t* counts) {
  auto c=static_cast<Context*>(p);const bool parent=c->parent.ctx;
  if(pa_sync(p)||pa_drop_slot(p,0)||pa_drop_slot(p,1)||!release(c,c->parent))return 1;
  if(parent)++c->pf;
  counts[0]=c->created;counts[1]=c->freed;counts[2]=c->live;
  counts[3]=c->pc;counts[4]=c->pf;counts[5]=c->vc;counts[6]=c->vf;counts[7]=c->oc;counts[8]=c->of;
  return c->live==0?0:1;
}
extern "C" int pa_close(void* p) {
  auto c=static_cast<Context*>(p);if(c->live || pa_sync(p))return 1;
  if(!ok(mlx_stream_free(c->stream))||!ok(mlx_device_free(c->device))||!ok(mlx_clear_cache()))return 1;
  delete c;return 0;
}
