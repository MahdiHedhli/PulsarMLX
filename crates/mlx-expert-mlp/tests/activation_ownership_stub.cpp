// Protocol/lifetime test only. CPU stand-in values are not native observations
// or any numerical oracle. No MLX library is linked into this executable.
#include "mlx/c/mlx.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <set>
#include <vector>

namespace {
struct A {std::vector<float> v;std::vector<int> shape;bool evaluated=false;};
std::set<void*> arrays;int devices=0,streams=0,operations=0,fail_at=0;
A* get(mlx_array a){assert(a.ctx && arrays.count(a.ctx));return static_cast<A*>(a.ctx);}
mlx_array make(std::vector<float> v,std::vector<int> s){auto *a=new A{v,s,false};arrays.insert(a);return {a};}
int finish(mlx_array *out,std::vector<float> v,std::vector<int> shape){assert(!out->ctx);*out=make(v,shape);return ++operations==fail_at ? 1 : 0;}
int binary(mlx_array *out,mlx_array x,mlx_array y,int op){auto *a=get(x),*b=get(y);std::vector<float> v(a->v.size());
 for(size_t i=0;i<v.size();++i){const float q=b->v[b->v.size()==1?0:i];v[i]=op==0?std::fmin(a->v[i],q):op==1?std::fmax(a->v[i],q):a->v[i]*q;}
 return finish(out,v,a->shape);}
}
extern "C" {
mlx_device mlx_device_new(){return {nullptr};}
mlx_device mlx_device_new_type(mlx_device_type type,int){assert(type==MLX_GPU);devices++;return {new int(1)};}
int mlx_device_free(mlx_device d){if(d.ctx){delete static_cast<int*>(d.ctx);devices--;}return 0;}
int mlx_device_get_type(mlx_device_type *t,mlx_device d){assert(d.ctx);*t=MLX_GPU;return 0;}
mlx_stream mlx_stream_new_device(mlx_device d){assert(d.ctx);streams++;return {new int(1)};}
int mlx_stream_get_device(mlx_device *d,mlx_stream s){assert(s.ctx && !d->ctx);*d=mlx_device_new_type(MLX_GPU,0);return 0;}
int mlx_stream_free(mlx_stream s){if(s.ctx){delete static_cast<int*>(s.ctx);streams--;}return 0;}
int mlx_synchronize(mlx_stream s){assert(s.ctx);return 0;}
int mlx_metal_is_available(bool *b){*b=true;return 0;}
mlx_array mlx_array_new(){return {nullptr};}
mlx_array mlx_array_new_data(const void *p,const int *shape,int ndim,mlx_dtype dtype){assert(dtype==MLX_FLOAT32);size_t n=1;for(int i=0;i<ndim;i++)n*=shape[i];return make(std::vector<float>(static_cast<const float*>(p),static_cast<const float*>(p)+n),std::vector<int>(shape,shape+ndim));}
mlx_array mlx_array_new_float32(float x){return make({x},{});}
int mlx_array_free(mlx_array a){if(a.ctx){assert(arrays.erase(a.ctx)==1);delete static_cast<A*>(a.ctx);}return 0;}
int mlx_array_eval(mlx_array a){get(a)->evaluated=true;return 0;}
mlx_dtype mlx_array_dtype(mlx_array a){get(a);return MLX_FLOAT32;}
size_t mlx_array_ndim(mlx_array a){return get(a)->shape.size();}
size_t mlx_array_size(mlx_array a){return get(a)->v.size();}
const int *mlx_array_shape(mlx_array a){return get(a)->shape.data();}
const float *mlx_array_data_float32(mlx_array a){auto *p=get(a);assert(p->evaluated);return p->v.data();}
int mlx_minimum(mlx_array *out,mlx_array a,mlx_array b,mlx_stream){return binary(out,a,b,0);}
int mlx_maximum(mlx_array *out,mlx_array a,mlx_array b,mlx_stream){return binary(out,a,b,1);}
int mlx_multiply(mlx_array *out,mlx_array a,mlx_array b,mlx_stream){return binary(out,a,b,2);}
int mlx_sigmoid(mlx_array *out,mlx_array a,mlx_stream){auto *p=get(a);auto v=p->v;for(float &x:v)x=1/(1+std::exp(-x));return finish(out,v,p->shape);}
int mlx_clip(mlx_array *out,mlx_array a,mlx_array lo,mlx_array hi,mlx_stream){auto *p=get(a);auto v=p->v;const float l=get(lo)->v[0],h=get(hi)->v[0];for(float &x:v)x=std::fmin(std::fmax(x,l),h);return finish(out,v,p->shape);}
int pulsar_mlp_activation(const float*,const float*,int,int,float*,uint32_t*,uint32_t*,uint64_t*,int);
}
int main(){
 float gate[64],up[64],out[64];uint32_t gc[64],uc[64];uint64_t stats[8];
 for(int i=0;i<64;i++){gate[i]=i%2?15:-3;up[i]=i%2?-15:15;}
 for(int mode=0;mode<=4;mode++){
  operations=0;fail_at=0;
  const int rc=pulsar_mlp_activation(gate,up,1,64,out,gc,uc,stats,mode);
  assert(rc==0);assert(arrays.empty() && !devices && !streams);
  assert(stats[0]==2 && stats[2]==9 && stats[3]==4 && stats[4]==13 && stats[5]==1 && stats[6]==9 && stats[7]==0);
 }
 // Simulate a nonzero status AFTER allocating an operation result; cleanup
 // must free that actual filled slot and every earlier slot, including empties.
 for(int failure=1;failure<=5;failure++){
  operations=0;fail_at=failure;
  assert(pulsar_mlp_activation(gate,up,1,64,out,gc,uc,stats,0)!=0);
  assert(arrays.empty() && !devices && !streams);
 }
 std::puts("HOST_STUB_OWNERSHIP_PASS:5modes,5partial-result-failures; no MLX linked");
}
