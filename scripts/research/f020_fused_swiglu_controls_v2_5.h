// Pure bit-policy controls; safe to execute without MLX or Candidate N/B.
#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>
#include <iterator>
inline uint32_t f020_ordered_key(uint32_t b) {
  return (b & 0x80000000u) ? ~b : b ^ 0x80000000u;
}
inline uint32_t f020_from_ordered(uint32_t k) {
  return (k & 0x80000000u) ? k ^ 0x80000000u : ~k;
}
inline bool f020_control_pairs(uint32_t worst, std::vector<uint32_t>& gates,
                               std::vector<uint32_t>& ups) {
  const uint32_t lo=f020_ordered_key(0xc1800000u), hi=f020_ordered_key(0x41800000u);
  const uint32_t key=f020_ordered_key(worst);
  if (key<lo || key>hi) return false;
  const uint32_t fixed[] = {0x80000000u, 0x00000000u, 0x80000001u, 0x00000001u, 0x807fffffu, 0x007fffffu, 0x80800000u, 0x00800000u, 0x80800001u, 0x00800001u, 0xaf800000u, 0x2f800000u, 0xc1800000u, 0xc1200001u, 0xc1200000u, 0xc11fffffu, 0x411fffffu, 0x41200000u, 0x41200001u, 0x41800000u};
  const uint32_t up_bits[] = {0xc1800000u, 0xc1200001u, 0xc1200000u, 0xc11fffffu, 0x80800000u, 0x807fffffu, 0x80000001u, 0x80000000u, 0x00000000u, 0x00000001u, 0x007fffffu, 0x00800000u, 0xaf800000u, 0x2f800000u, 0xbf800000u, 0x3f800000u, 0x411fffffu, 0x41200000u, 0x41200001u, 0x41800000u};
  std::vector<uint32_t> values(std::begin(fixed),std::end(fixed));
  const uint32_t first=std::max(lo,key-2u), last=std::min(hi,key+2u);
  for (uint32_t k=first;k<=last;++k) {
    const uint32_t b=f020_from_ordered(k);
    if (std::find(values.begin(),values.end(),b)==values.end()) values.push_back(b);
  }
  for(uint32_t g:values) for(uint32_t u:up_bits) {gates.push_back(g);ups.push_back(u);}
  return true;
}
