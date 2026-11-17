#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <vector>
#include "../src/startup_compat.hpp"

int wmain(int argc,wchar_t** argv) {
    if(argc!=2 && argc!=4) return 1;
    HMODULE module=LoadLibraryW(argv[1]); // Our module only; never a game or third-party DLL.
    if(!module) return 2;
    auto test=reinterpret_cast<int(__cdecl*)()>(GetProcAddress(module,"CompatibilitySelfTest"));
    auto initialize=reinterpret_cast<void(__cdecl*)()>(GetProcAddress(module,"InitializeASI"));
    auto status=reinterpret_cast<int(__cdecl*)()>(GetProcAddress(module,"CompatibilityStatus"));
    if(!test || !initialize || !status || test()!=0) return 3;
    initialize();initialize();
    if(status()!=2) return 4;
    FreeLibrary(module);
    if(argc==4) {
        // Optional recorded image is DATA only: no allocation with execute rights,
        // no game imports, entry point, DLL initialization or proprietary code calls.
        FILE* input=nullptr;
        if(_wfopen_s(&input,argv[2],L"rb") || !input) return 5;
        fseek(input,0,SEEK_END);long length=ftell(input);rewind(input);
        if(length<1 || length>64*1024*1024) {fclose(input);return 6;}
        std::vector<unsigned char> image(static_cast<size_t>(length));
        bool read=fread(image.data(),1,image.size(),input)==image.size();fclose(input);
        if(!read || !StartupCompat::Apply(image.data(),image.size(),0x10002000)) return 7;
        HANDLE output=CreateFileW(argv[3],GENERIC_WRITE,0,nullptr,CREATE_NEW,0,nullptr);
        if(output==INVALID_HANDLE_VALUE) return 8;
        DWORD count=0;
        bool written=WriteFile(output,image.data(),static_cast<DWORD>(image.size()),&count,nullptr) && count==image.size();
        CloseHandle(output);
        if(!written) return 9;
        puts("COMPAT IMAGE PASS: real GOG image treated only as data; four instruction contracts applied; synthetic overlay address");
    }
    puts("COMPAT HOST PASS: four-site atomic guard; own overlay storage; rollback; repeat-call and wrong-host gate; no game launched");
    return 0;
}
