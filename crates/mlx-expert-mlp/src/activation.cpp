// New composition shim, with the qualified F020 operation order unchanged.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <vector>
#include "mlx/c/mlx.h"
#include "f020_fused_swiglu_cpu_guard_v2_4.h"

extern "C" int pulsar_mlp_cpu_guard(uint64_t *fpcr) {
  return fpcr && f020_check_cpu_arithmetic(*fpcr) ? 0 : 79;
}

// mode 0 is the candidate; modes 1..4 are safe-domain mutation controls only.
// Every handle, cleanup status and implicit import is accounted separately.
extern "C" int pulsar_mlp_activation(const float *gate, const float *up, int m, int hsize,
                                      float *out, uint32_t *gate_clamp, uint32_t *up_clamp,
                                      uint64_t *stats, int mode) {
  if (!gate || !up || !out || !stats || !gate_clamp || !up_clamp ||
      m<=0 || hsize<=0 || m>32 || hsize>128 || mode<0 || mode>4) return 64;
  std::memset(stats,0,8*sizeof(uint64_t));
  uint64_t fpcr=0;stats[0]++;
  if (!f020_check_cpu_arithmetic(fpcr)) return 79;
  stats[1]=fpcr;
  for (int i=0;i<m*hsize;++i)
    if (!std::isfinite(gate[i]) || !std::isfinite(up[i]) || std::fabs(gate[i])>16 || std::fabs(up[i])>16) return 78;
  mlx_device dev=mlx_device_new_type(MLX_GPU,0);
  mlx_stream stream=mlx_stream_new_device(dev);
  int rc=(!dev.ctx || !stream.ctx) ? 75 : 0;
  mlx_device sd=mlx_device_new();mlx_device_type dt=MLX_CPU;
  if (!rc) rc=mlx_stream_get_device(&sd,stream);
  if (!rc) rc=mlx_device_get_type(&dt,sd);
  if (dt!=MLX_GPU) rc=75;
  rc|=mlx_device_free(sd);
  bool available=false;if(!rc)rc=mlx_metal_is_available(&available);
  if (!available)rc=75;
  std::vector<mlx_array> arrays;
  auto keep=[&](mlx_array a){arrays.push_back(a);stats[2]++;if(!a.ctx)rc=75;return a;};
  const int shape[2]={m,hsize};
  auto ga=keep(mlx_array_new_data(gate,shape,2,MLX_FLOAT32));
  auto ua=keep(mlx_array_new_data(up,shape,2,MLX_FLOAT32));
  auto ten=keep(mlx_array_new_float32(10));auto negten=keep(mlx_array_new_float32(-10));stats[3]=4;
  auto g=keep(mlx_array_new());auto s=keep(mlx_array_new());auto silu=keep(mlx_array_new());
  auto clipped=keep(mlx_array_new());auto value=keep(mlx_array_new());
  if(!rc) {
    if(mode==1)rc=mlx_clip(&g,ga,negten,ten,stream);
    else if(mode==2){auto one=keep(mlx_array_new_float32(1));stats[3]++;rc=mlx_multiply(&g,ga,one,stream);}
    else rc=mlx_minimum(&g,ga,ten,stream);
    stats[4]++;
  }
  if(!rc){rc=mlx_sigmoid(&s,g,stream);stats[4]++;}
  if(!rc){rc=mlx_multiply(&silu,g,s,stream);stats[4]++;}
  if(!rc){rc=mlx_array_eval(silu);stats[4]++;}
  if(!rc){rc=mlx_synchronize(stream);stats[4]++;}
  if(!rc && (mlx_array_dtype(silu)!=MLX_FLOAT32 || mlx_array_size(silu)!=static_cast<size_t>(m*hsize)))rc=75;
  if(!rc)stats[5]++;
  if(!rc) {
    if(mode==3)rc=mlx_maximum(&clipped,ua,negten,stream);
    else if(mode==4)rc=mlx_minimum(&clipped,ua,ten,stream);
    else rc=mlx_clip(&clipped,ua,negten,ten,stream);
    stats[4]++;
  }
  if(!rc){rc=mlx_multiply(&value,silu,clipped,stream);stats[4]++;}
  if(!rc){rc=mlx_array_eval(value);stats[4]++;}
  if(!rc){rc=mlx_synchronize(stream);stats[4]++;}
  if(!rc) {
    const int *dims=mlx_array_shape(value);
    if(mlx_array_dtype(value)!=MLX_FLOAT32 || mlx_array_ndim(value)!=2 || !dims ||
       dims[0]!=m || dims[1]!=hsize)rc=75;
  }
  if(!rc) {
    const float *v=mlx_array_data_float32(value);
    if(!v)rc=75;
    else for(int i=0;i<m*hsize;++i){if(!std::isfinite(v[i]))rc=75;out[i]=v[i];}
  }
  // Semantic clamp readbacks occur after the qualified h graph is materialized.
  if(!rc){rc=mlx_array_eval(g);stats[4]++;}
  if(!rc){rc=mlx_array_eval(clipped);stats[4]++;}
  if(!rc){rc=mlx_synchronize(stream);stats[4]++;}
  if(!rc) {
    const float *gv=mlx_array_data_float32(g),*uv=mlx_array_data_float32(clipped);
    if(!gv || !uv)rc=75;
    else for(int i=0;i<m*hsize;++i){std::memcpy(gate_clamp+i,gv+i,4);std::memcpy(up_clamp+i,uv+i,4);}
  }
  stats[0]++;if(!f020_check_cpu_arithmetic(fpcr) || fpcr!=stats[1])rc=79;
  rc|=mlx_synchronize(stream);stats[4]++;
  for(auto it=arrays.rbegin();it!=arrays.rend();++it){const int st=mlx_array_free(*it);stats[6]++;if(st)stats[7]++;rc|=st;}
  const int sf=mlx_stream_free(stream),df=mlx_device_free(dev);
  if(sf || df)stats[7]++;
  rc|=sf;rc|=df;
  return rc;
}
