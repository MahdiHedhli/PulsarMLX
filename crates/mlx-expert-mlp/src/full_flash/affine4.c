/* Correctness path for directly packed affine-4 projection. The pinned generic
 * BF16 vector primitive rounds partial bias sums in BF16 (quantized.h load_vector).
 * Model input, scales, biases and output here are BF16; the MAC accumulator
 * is float, just as in the original primitive. No parameter or dense repack.
 * One output row per work item. No custom scheduling or performance claim. */
#include "mlx/c/mlx.h"
#include <stdint.h>
#include <string.h>
/* s is borrowed from the caller's live, same-thread NativeContext. Never retain
 * or free it. Sequential affine4 and 8-bit operations share its ordering; the
 * existing eval + synchronize below completes successful host readback. */
int studio017_affine4(const uint16_t *x,const void *words,const void *scales,const void *biases,int cols,int rows,uint16_t *dst,mlx_stream s){
 if(!x||!words||!scales||!biases||!dst||!s.ctx||cols<64||cols>4096||cols%64||rows<1||rows>64)return 1;
 /* Query only; this temporary device handle is not the caller-owned device. */
 mlx_device d={0};mlx_device_type type=MLX_CPU;
 int check=mlx_stream_get_device(&d,s);
 if(!check&&d.ctx)check=mlx_device_get_type(&type,d);
 if(!d.ctx)check=2;
 if(d.ctx&&mlx_device_free(d))check=4;
 if(check)return check;
 if(type!=MLX_GPU)return 1;
 int rc=0;int packed[2]={rows,cols/8},meta[2]={rows,cols/64};
 mlx_array args[4]={mlx_array_new_data(x,&cols,1,MLX_BFLOAT16),mlx_array_new_data(words,packed,2,MLX_UINT32),mlx_array_new_data(scales,meta,2,MLX_BFLOAT16),mlx_array_new_data(biases,meta,2,MLX_BFLOAT16)};
 const char* ins[4]={"act","packed","scale","bias"},*outs[1]={"answer"};
 mlx_vector_string in=mlx_vector_string_new_data(ins,4),out=mlx_vector_string_new_data(outs,1);
 mlx_vector_array inputs=mlx_vector_array_new_data(args,4),vals=mlx_vector_array_new();
 mlx_fast_metal_kernel_config c=mlx_fast_metal_kernel_config_new();
 const char *body="uint r=thread_position_in_grid.x; float v[8]={0.0f};"
 "for(int j=0;j<act_shape[0];j+=8){uint word=packed[r*(act_shape[0]/8)+j/8];"
 "float sc=float(scale[r*(act_shape[0]/64)+j/64]);float bi=float(bias[r*(act_shape[0]/64)+j/64]);"
 "for(int k=0;k<8;++k){float w=fma(float((word>>(4*k))&15u),sc,bi);v[k]=fma(float(act[j+k]),w,v[k]);}}"
 "answer[r]=bfloat16_t(((v[0]+v[4])+(v[2]+v[6]))+((v[1]+v[5])+(v[3]+v[7])));";
 mlx_fast_metal_kernel kernel=mlx_fast_metal_kernel_new("studio017_affine4_dot",in,out,body,"",true,false);
 mlx_array val=mlx_array_new(),bits=mlx_array_new();
 if(!s.ctx||!in.ctx||!out.ctx||!inputs.ctx||!vals.ctx||!c.ctx||!kernel.ctx)rc=2;
 for(int i=0;i<4;i++)if(!args[i].ctx)rc=2;
 if(!rc)rc=mlx_fast_metal_kernel_config_add_output_arg(c,&rows,1,MLX_BFLOAT16);
 if(!rc)rc=mlx_fast_metal_kernel_config_set_grid(c,rows,1,1);
 if(!rc)rc=mlx_fast_metal_kernel_config_set_thread_group(c,rows<32?rows:32,1,1);
 if(!rc)rc=mlx_fast_metal_kernel_apply(&vals,kernel,inputs,c,s);
 if(!rc && mlx_vector_array_size(vals)!=1)rc=3;
 if(!rc)rc=mlx_vector_array_get(&val,vals,0);
 if(!rc && (mlx_array_size(val)!=(size_t)rows||mlx_array_dtype(val)!=MLX_BFLOAT16))rc=3;
 if(!rc)rc=mlx_view(&bits,val,MLX_UINT16,s);
 if(!rc)rc=mlx_array_eval(bits);
 if(!rc)rc=mlx_synchronize(s);
 if(!rc){const uint16_t *p=mlx_array_data_uint16(bits);if(!p)rc=3;else memcpy(dst,p,rows*sizeof(*dst));}
 if(mlx_array_free(bits))rc=4;
 if(mlx_array_free(val))rc=4;
 mlx_fast_metal_kernel_free(kernel);mlx_fast_metal_kernel_config_free(c);
 if(mlx_vector_array_free(vals))rc=4;
 if(mlx_vector_array_free(inputs))rc=4;
 if(mlx_vector_string_free(in))rc=4;
 if(mlx_vector_string_free(out))rc=4;
 for(int i=0;i<4;i++)if(mlx_array_free(args[i]))rc=4;
 return rc;
}
