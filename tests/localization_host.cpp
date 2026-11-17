#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
int wmain(int argc,wchar_t** argv) {
    if(argc!=3) return 10;
    HMODULE dll=LoadLibraryW(argv[1]); if(!dll) return 11;
    auto test=reinterpret_cast<int(__cdecl*)(const wchar_t*)>(GetProcAddress(dll,"LocalizationSelfTest"));
    auto init=reinterpret_cast<void(__cdecl*)()>(GetProcAddress(dll,"InitializeASI"));
    auto status=reinterpret_cast<int(__cdecl*)()>(GetProcAddress(dll,"LocalizationStatus"));
    if(!test||!init||!status) return 12;
    int result=test(argv[2]); if(result) { printf("SELFTEST FAIL: %d\n",result); return 20+result; }
    init(); init();
    if(status()!=2) { printf("IDENTITY GATE FAIL: %d\n",status()); return 13; }
    puts("HOST PASS: pack; malformed-input rejection; token boundaries; memory rollback; wrong-host gate; no game launched");
    FreeLibrary(dll); return 0;
}
