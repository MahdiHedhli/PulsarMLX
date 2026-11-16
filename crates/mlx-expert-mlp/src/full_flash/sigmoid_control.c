/* Synthetic, test-only; copied BF16 arrays. May compile under the opt-in research
 * feature and link into tests, but not called by any production entry point. */
#include "mlx/c/mlx.h"
#include <stdint.h>
#include <string.h>
int studio017_synthetic_silu_bits(uint16_t input, uint16_t *sig_bits, uint16_t *out_bits) {
  if (!sig_bits || !out_bits) return 1;
  int shape=1, rc=1;
  mlx_device d=mlx_device_new_type(MLX_GPU,0);
  if(!d.ctx) return 1;
  mlx_stream s=mlx_stream_new_device(d);
  mlx_array x=mlx_array_new(),sig=mlx_array_new(),out=mlx_array_new(), xs=mlx_array_new(), xo=mlx_array_new();
  if (!s.ctx) goto cleanup;
  x=mlx_array_new_data(&input,&shape,1,MLX_BFLOAT16);
  if(!x.ctx || mlx_sigmoid(&sig,x,s) || mlx_multiply(&out,x,sig,s) ||
     mlx_array_eval(out) || mlx_array_eval(sig) || mlx_synchronize(s)) goto cleanup;
  if(mlx_array_dtype(out)!=MLX_BFLOAT16 || mlx_array_dtype(sig)!=MLX_BFLOAT16)goto cleanup;
  if(mlx_view(&xs,sig,MLX_UINT16,s)||mlx_view(&xo,out,MLX_UINT16,s)||mlx_array_eval(xs)||mlx_array_eval(xo)||mlx_synchronize(s))goto cleanup;
  const void *sb=mlx_array_data_uint16(xs), *ob=mlx_array_data_uint16(xo);
  if(!sb || !ob)goto cleanup;
  memcpy(sig_bits,sb,2);memcpy(out_bits,ob,2);rc=0;
cleanup:
  if(mlx_array_free(xo))rc=2;
  if(mlx_array_free(xs))rc=2;
  if(mlx_array_free(out))rc=2;
  if(mlx_array_free(sig))rc=2;
  if(mlx_array_free(x))rc=2;
  if(s.ctx && mlx_stream_free(s))rc=2;
  if(mlx_device_free(d))rc=2;
  return rc;
}
