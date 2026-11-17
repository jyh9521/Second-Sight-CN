// Locale-neutral, independent GOG/FusionFix startup compatibility adapter.
// Only user-started game's InitializeASI writes its own image; no game launching.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <cstdio>
#include <string>
#include <vector>
#include <stdexcept>
#include "startup_compat.hpp"

static HMODULE module;
static LONG initialized;
static int status;
static float overlayAspect=4.0f/3.0f;
static std::wstring directory;
static constexpr char exeHash[]="4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda";
static constexpr char fusionHash[]="939d0bbc6dacca73b4323fa018ba11d04a87dde5073e795b5914db85d6158430";

static void log(const char* message) {
    FILE* file=nullptr;
    if(_wfopen_s(&file,(directory+L"SecondSight.Compatibility.log").c_str(),L"ab")==0) {
        fprintf(file,"%s\r\n",message);fclose(file);
    }
}
static std::string fileHash(const wchar_t* path) {
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if(file==INVALID_HANDLE_VALUE) return {};
    HCRYPTPROV provider=0;HCRYPTHASH hash=0;
    bool ok=CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) &&
            CryptCreateHash(provider,CALG_SHA_256,0,0,&hash);
    unsigned char buffer[65536];DWORD count=0;
    while(ok) {
        ok=ReadFile(file,buffer,sizeof(buffer),&count,nullptr)!=FALSE;
        if(!ok || !count) break;
        ok=CryptHashData(hash,buffer,count,0)!=FALSE;
    }
    unsigned char digest[32]{};DWORD length=sizeof(digest);
    ok=ok && CryptGetHashParam(hash,HP_HASHVAL,digest,&length,0);
    if(hash) CryptDestroyHash(hash);
    if(provider) CryptReleaseContext(provider,0);
    CloseHandle(file);
    if(!ok) return {};
    char text[65]{};
    for(size_t i=0;i<32;++i) sprintf_s(text+i*2,3,"%02x",digest[i]);
    return text;
}
extern "C" __declspec(dllexport) void __cdecl InitializeASI() {
    if(InterlockedCompareExchange(&initialized,1,0)) return;
    wchar_t own[MAX_PATH]{},exe[MAX_PATH]{};
    GetModuleFileNameW(module,own,MAX_PATH);
    directory=own;directory=directory.substr(0,directory.find_last_of(L"\\/")+1);
    GetModuleFileNameW(nullptr,exe,MAX_PATH);
    if(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr))!=0x400000 || fileHash(exe)!=exeHash) {
        status=2;log("COMPAT IDENTITY REJECTED; no game-memory access or writes");return;
    }
    if(fileHash((directory+L"SecondSight.FusionFix.asi").c_str())!=fusionHash ||
       GetModuleHandleW(L"SecondSight.FusionFix.asi")) {
        status=3;log("COMPAT DEPENDENCY/ORDER REJECTED; no writes; load adapter before FusionFix");return;
    }
    auto image=reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    auto dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(image);
    auto nt=reinterpret_cast<const IMAGE_NT_HEADERS32*>(image+dos->e_lfanew);
    size_t size=nt->OptionalHeader.SizeOfImage;
    uint32_t overlay=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(&overlayAspect));
    if(!StartupCompat::Matches(image,size,overlay,false)) {
        status=3;log("COMPAT SITE CONFLICT; no writes");return;
    }
    auto sites=StartupCompat::Sites(overlay);
    DWORD protection[4]{};size_t prepared=0;
    for(;prepared<sites.size();++prepared) {
        const auto& site=sites[prepared];
        if(!VirtualProtect(image+site.rva,site.size,PAGE_EXECUTE_READWRITE,&protection[prepared])) break;
    }
    if(prepared!=sites.size()) {
        while(prepared) { --prepared;DWORD ignored=0;VirtualProtect(image+sites[prepared].rva,sites[prepared].size,protection[prepared],&ignored); }
        status=3;log("COMPAT PROTECTION REJECTED; no bytes changed");return;
    }
    bool ok=StartupCompat::Apply(image,size,overlay);
    if(ok && !FlushInstructionCache(GetCurrentProcess(),image,size)) {
        StartupCompat::Apply(image,size,overlay,true);FlushInstructionCache(GetCurrentProcess(),image,size);ok=false;
    }
    bool protectedAgain=true;
    for(size_t i=0;i<sites.size();++i) {
        DWORD ignored=0;
        protectedAgain=VirtualProtect(image+sites[i].rva,sites[i].size,protection[i],&ignored)!=FALSE && protectedAgain;
    }
    status=ok&&protectedAgain?1:3;
    log(status==1?"COMPAT APPLIED: 4 sites, 22 bytes; private overlay scalar; disk EXE/FusionFix unchanged; runtime acceptance pending":
                  "COMPAT APPLY/PROTECTION ERROR; inspect before further testing");
}
extern "C" __declspec(dllexport) int __cdecl CompatibilityStatus() {return status;}
extern "C" __declspec(dllexport) int __cdecl CompatibilitySelfTest() {
    const uint32_t overlay=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(&overlayAspect));
    std::vector<unsigned char> bytes(0x184000,0x5a);
    for(const auto& site:StartupCompat::Sites(overlay)) memcpy(bytes.data()+site.rva,site.before.data(),site.size);
    const auto original=bytes;
    if(!StartupCompat::Apply(bytes.data(),bytes.size(),overlay)) return 1;
    if(!StartupCompat::Matches(bytes.data(),bytes.size(),overlay,true)) return 2;
    const auto modified=bytes;
    if(StartupCompat::Apply(bytes.data(),bytes.size(),overlay) || bytes!=modified) return 3;
    if(!StartupCompat::Apply(bytes.data(),bytes.size(),overlay,true) || bytes!=original) return 4;
    bytes[0xf01cb]^=1;const auto conflict=bytes;
    if(StartupCompat::Apply(bytes.data(),bytes.size(),overlay) || bytes!=conflict) return 5;
    if(StartupCompat::Apply(bytes.data(),3,overlay) || StartupCompat::Apply(bytes.data(),bytes.size(),0)) return 6;
    overlayAspect=16.0f/9.0f;
    if(*reinterpret_cast<const float*>(static_cast<uintptr_t>(overlay))!=overlayAspect) return 7;
    overlayAspect=4.0f/3.0f;return 0;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) {module=instance;DisableThreadLibraryCalls(instance);}
    return TRUE;
}
