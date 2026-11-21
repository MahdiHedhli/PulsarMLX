/* Small native primitives missing from the existing affine wrapper.
 * Synchronous copied inputs/outputs on the caller-owned, same-thread GPU stream. */
#include "mlx/c/mlx.h"
#include <stdint.h>
#include <string.h>
int studio017_limits(void){
 size_t prev=0,read=0;
 return mlx_set_cache_limit(&prev,0) || mlx_set_memory_limit(&prev,512UL<<20) ||
        mlx_get_memory_limit(&read) || read!=(512UL<<20);
}
int studio017_aux(const float *x,const float *weights,int n,int k,int is_rank,
                  float *floats,uint32_t *ids,mlx_stream s) {
 if(!x || !s.ctx || (is_rank ? (!ids || weights || n!=288 || k!=8):(!weights || !floats || n!=4096 || k!=288)))return 1;
 /* Borrow s without retaining/freeing it. Only this queried device is temporary.
  * Success eval/sync below is unchanged; failed calls can leave pending work. */
 mlx_device d={0};mlx_device_type type=MLX_CPU;
 int check=mlx_stream_get_device(&d,s);
 if(!check&&d.ctx)check=mlx_device_get_type(&type,d);
 if(!d.ctx)check=2;
 if(d.ctx&&mlx_device_free(d))check=4;
 if(check)return check;
 if(type!=MLX_GPU)return 1;
 int fail=0;
 mlx_array a=mlx_array_new(),b=mlx_array_new(),out=mlx_array_new();
 if(!fail){
   a=mlx_array_new_data(x,&n,1,MLX_FLOAT32);fail=!a.ctx;
 }
 if(!fail && is_rank)fail=mlx_argpartition_axis(&out,a,k-1,0,s);
 if(!fail && !is_rank){
   int sh[2]={k,n};b=mlx_array_new_data(weights,sh,2,MLX_FLOAT32);fail=!b.ctx;
   if(!fail)fail=mlx_matmul(&out,b,a,s);
 }
 if(!fail)fail=mlx_array_eval(out)||mlx_synchronize(s);
 if(!fail && is_rank){
   if(mlx_array_dtype(out)!=MLX_UINT32 || mlx_array_size(out)!=(size_t)n)fail=3;
   else {const uint32_t *p=mlx_array_data_uint32(out);if(!p)fail=3;else memcpy(ids,p,k*sizeof(*p));}
 }
 if(!fail && !is_rank){
   if(mlx_array_dtype(out)!=MLX_FLOAT32 || mlx_array_size(out)!=(size_t)k)fail=3;
   else {const float *p=mlx_array_data_float32(out);if(!p)fail=3;else memcpy(floats,p,k*sizeof(*p));}
 }
 if(mlx_array_free(out))fail=4;
 if(mlx_array_free(b))fail=4;
 if(mlx_array_free(a))fail=4;
 return fail;
}
