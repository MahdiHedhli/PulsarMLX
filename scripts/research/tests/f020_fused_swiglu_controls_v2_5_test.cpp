#include <cstdio>
#include <cstdlib>
#include "../f020_fused_swiglu_controls_v2_5.h"
int main(int argc,char**argv) {
  if(argc!=2) return 64;
  char* end=nullptr;
  unsigned long v=std::strtoul(argv[1],&end,16);
  if(*end || v>0xffffffffUL) return 64;
  std::vector<uint32_t> gates,ups;
  if(!f020_control_pairs(static_cast<uint32_t>(v),gates,ups)) return 65;
  for(size_t i=0;i<gates.size();++i) std::printf("%08x %08x\n",gates[i],ups[i]);
}
