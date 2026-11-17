#pragma once
#include <array>
#include <cstdint>
#include <cstring>

// Exact supported GOG image only. These are instruction contracts expected by
// the pinned FusionFix, not a general game-version or binary conversion tool.
namespace StartupCompat {
struct Site { uint32_t rva; size_t size; std::array<unsigned char,6> before,after; };
inline std::array<Site,4> Sites(uint32_t overlay) {
    std::array<Site,4> sites{{
        {0x171b9,5,{0xe9,0x14,0xb7,0xfe,0xff},{0x83,0xf8,0x55,0x7f,0x15}},
        {0x4975b,6,{0xe9,0xe4,0x93,0xfb,0xff,0x90},{0xd8,0x0d,0x70,0xcc,0x7c,0}},
        {0x18392f,5,{0xe9,0x84,0xf2,0xe7,0xff},{0x68,0xab,0xaa,0xaa,0x3f}},
        {0xf01cb,6,{0xe9,0x15,0x2a,0xf1,0xff,0x90},{0xd8,0x0d,0,0,0,0}}
    }};
    // Private persistent storage: never redirect FF writes into a shared GOG scalar.
    memcpy(sites[3].after.data()+2,&overlay,sizeof(overlay));
    return sites;
}
inline bool Matches(const unsigned char* image,size_t size,uint32_t overlay,bool modified) {
    if(!image || !overlay) return false;
    for(const auto& site:Sites(overlay)) {
        if(site.rva>size || site.size>size-site.rva) return false;
        const auto& expected=modified?site.after:site.before;
        if(memcmp(image+site.rva,expected.data(),site.size)) return false;
    }
    return true;
}
// Shared by the real initializer and offline host. All sites must match before
// any write; the caller owns protection changes and the target buffer.
inline bool Apply(unsigned char* image,size_t size,uint32_t overlay,bool restore=false) {
    if(!Matches(image,size,overlay,restore)) return false;
    for(const auto& site:Sites(overlay)) {
        const auto& bytes=restore?site.before:site.after;
        memcpy(image+site.rva,bytes.data(),site.size);
    }
    return true;
}
}
