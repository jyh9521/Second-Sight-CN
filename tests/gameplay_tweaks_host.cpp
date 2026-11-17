#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include "../src/gameplay_tweaks_sites.h"

int wmain(int argc,wchar_t** argv) {
    if(argc!=2) return 1;
    using namespace gameplay_tweaks;
    bool previous=false;
    if(keyEdge(previous,true,false) || keyEdge(previous,true,true) ||
       keyEdge(previous,false,true) || !keyEdge(previous,true,true) ||
       keyEdge(previous,true,true) || keyEdge(previous,false,true) ||
       !keyEdge(previous,true,true)) return 2;
    for(const auto& site:sites) {
        const uintptr_t target=0x10001000;
        const auto bytes=encoding(site,target);
        uint32_t displacement=0;
        for(size_t i=0;i<4;++i) displacement|=static_cast<uint32_t>(bytes[i+1])<<(i*8);
        if(bytes[0]!=site.opcode || site.va+5+displacement!=target) return 3;
        for(size_t i=5;i<site.size;++i) if(bytes[i]!=0x90) return 4;
    }
    const HMODULE dll=LoadLibraryW(argv[1]);
    if(!dll) return 5;
    using Init=void(__cdecl*)();
    using Status=int(__cdecl*)();
    const auto init=reinterpret_cast<Init>(reinterpret_cast<void*>(GetProcAddress(dll,"InitializeASI")));
    const auto status=reinterpret_cast<Status>(reinterpret_cast<void*>(GetProcAddress(dll,"GameplayTweaksStatus")));
    if(!init || !status || status()!=0) return 6;
    init();
    if(status()!=2) return 7;
    init();
    if(status()!=2 || !FreeLibrary(dll)) return 8;
    puts("TWEAKS HOST PASS: F1 edge/focus, branch encoding and wrong-host rejection; game not launched");
    return 0;
}
