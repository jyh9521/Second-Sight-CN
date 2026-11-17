// Independent x86 localization adapter. No FusionFix implementation is copied.
// Only InitializeASI installs hooks; DllMain never initializes or launches a game.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <stdexcept>
#include "text_transport.h"

static HMODULE module;
static LONG initialized;
static int status; // 0 not called; 1 installed; 2 identity rejected; 3 validation rejected
static std::wstring directory;
static constexpr char expectedExe[] = "4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda";
static constexpr unsigned char marker = 0x1f;
struct Text { uint32_t index; std::string source, target; };
struct Resource { std::string name; std::vector<unsigned char> bytes; };
struct Pack { std::vector<Text> bs, pda; std::vector<Resource> resources; };
static Pack pack;

static void log(const char* message) {
    FILE* file = nullptr;
    if (_wfopen_s(&file, (directory+L"SecondSight.Localization.log").c_str(), L"ab") == 0) {
        fprintf(file, "%s\r\n", message); fclose(file);
    }
}
static std::vector<unsigned char> readFile(const std::wstring& path) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (file == INVALID_HANDLE_VALUE) throw std::runtime_error("file open failed");
    LARGE_INTEGER length{};
    if (!GetFileSizeEx(file, &length) || length.QuadPart < 1 || length.QuadPart > 32*1024*1024) {
        CloseHandle(file); throw std::runtime_error("file size rejected");
    }
    std::vector<unsigned char> bytes(static_cast<size_t>(length.QuadPart));
    DWORD got = 0;
    bool ok = ReadFile(file, bytes.data(), static_cast<DWORD>(bytes.size()), &got, nullptr) && got == bytes.size();
    CloseHandle(file);
    if (!ok) throw std::runtime_error("file read failed");
    return bytes;
}
static std::string hash(const std::vector<unsigned char>& bytes) {
    HCRYPTPROV provider = 0; HCRYPTHASH handle = 0;
    if (!CryptAcquireContextW(&provider, nullptr, nullptr, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)) return {};
    bool ok = CryptCreateHash(provider, CALG_SHA_256, 0, 0, &handle) &&
        CryptHashData(handle, bytes.data(), static_cast<DWORD>(bytes.size()), 0);
    unsigned char value[32]{}; DWORD size = sizeof(value);
    ok = ok && CryptGetHashParam(handle, HP_HASHVAL, value, &size, 0);
    if (handle) CryptDestroyHash(handle);
    CryptReleaseContext(provider, 0);
    if (!ok) return {};
    char text[65]{};
    for (size_t i=0;i<32;++i) sprintf_s(text+i*2, 3, "%02x", value[i]);
    return text;
}
static bool encoded(const std::string& value) {
    if (value.empty() || value.size() > 4096) return false;
    for (size_t i=0; i<value.size();) {
        auto ch = static_cast<unsigned char>(value[i]);
        if (ch==9 || ch==10 || ch==32) { ++i; continue; }
        if (ch==11 && i+1<value.size() && transport::opcode(value[i+1])) { i+=2; continue; }
        if (ch=='%' && i+1<value.size() && value[i+1]>='1' && value[i+1]<='9') { i+=2; continue; }
        if (ch != marker || i+5>value.size()) return false;
        int n=0;
        for (size_t j=i+1;j<i+5;++j) {
            if (value[j]<'0'||value[j]>'9') return false;
            n=n*10+value[j]-'0';
        }
        if (n>=1536 || (i+5<value.size() && value[i+5]>='0' && value[i+5]<='9')) return false;
        i+=5;
    }
    return true;
}
static Pack parse(const std::vector<unsigned char>& bytes) {
    size_t at=0;
    auto number=[&]() -> uint32_t {
        if (at+4>bytes.size()) throw std::runtime_error("truncated pack");
        uint32_t n; memcpy(&n,bytes.data()+at,4); at+=4; return n;
    };
    auto blob=[&]() -> std::string {
        uint32_t n=number();
        if (n>bytes.size()-at) throw std::runtime_error("invalid pack length");
        std::string s(reinterpret_cast<const char*>(bytes.data()+at),n); at+=n; return s;
    };
    if (number()!=0x31504c53) throw std::runtime_error("invalid pack magic");
    uint32_t bs=number(), pda=number(), resources=number();
    if (!bs || bs>6525 || !pda || pda>512 || resources!=6) throw std::runtime_error("invalid pack counts");
    Pack result;
    auto texts=[&](std::vector<Text>& items,uint32_t count,bool isBs) {
        for (uint32_t i=0;i<count;++i) {
            Text t{number(),blob(),blob()};
            if ((isBs && (t.index==0||t.index>=6526)) ||
                (!isBs && (t.index<32||t.index%4||t.index>79618)) ||
                t.source.empty() || t.source.size()>4096 ||
                t.source.find('\0')!=std::string::npos || !encoded(t.target) || t.target.size()>(isBs?255u:1800u))
                throw std::runtime_error("invalid text record");
            if(transport::budget(t.target)>(isBs?255u:1800u) ||
                (isBs && t.index>=6371 && t.index<=6504 && t.target.size()>27) ||
                (isBs && (t.index==6518 || t.index==6519) && t.target.size()>27))
                throw std::runtime_error("native consumer budget exceeded");
            for (const auto& prior: items) if (prior.index==t.index) throw std::runtime_error("duplicate text ID");
            items.push_back(std::move(t));
        }
    };
    texts(result.bs,bs,true); texts(result.pda,pda,false);
    for (uint32_t i=0;i<resources;++i) {
        auto name=blob(), data=blob();
        if (name!="textures/localization/page"+std::to_string(i)+".dds" || data.size()!=65664 ||
            memcmp(data.data(),"DDS ",4) || memcmp(data.data()+84,"DXT3",4))
            throw std::runtime_error("invalid atlas resource");
        auto dword=[&](size_t offset) { uint32_t value; memcpy(&value,data.data()+offset,4); return value; };
        if(dword(4)!=124 || dword(8)!=0x81007 || dword(12)!=256 || dword(16)!=256 ||
            dword(20)!=65536 || dword(28)!=1 || dword(76)!=32 || dword(80)!=4 || dword(108)!=0x1000)
            throw std::runtime_error("unsupported DDS header");
        result.resources.push_back({name,std::vector<unsigned char>(data.begin(),data.end())});
    }
    if (at!=bytes.size()) throw std::runtime_error("trailing pack data");
    return result;
}
static bool matches(const char* text,const std::string& expected) {
    if (!text) return false;
    MEMORY_BASIC_INFORMATION info{};
    if (!VirtualQuery(text,&info,sizeof(info)) || info.State!=MEM_COMMIT || (info.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return false;
    uintptr_t end=reinterpret_cast<uintptr_t>(info.BaseAddress)+info.RegionSize;
    return reinterpret_cast<uintptr_t>(text)+expected.size()+1 <= end &&
        memcmp(text,expected.c_str(),expected.size()+1)==0;
}
static const Resource* resource(const char* path) {
    if (!path) return nullptr;
    std::string key(path);
    for (char& c:key) { if(c=='\\') c='/'; if(c>='A'&&c<='Z') c=static_cast<char>(c+32); }
    for (const auto& item:pack.resources) if (key==item.name) return &item;
    return nullptr;
}
using SizeFn=int(__cdecl*)(const char*);
using ReadFn=int(__cdecl*)(const char*,void*,int);
using CountFn=int(__cdecl*)(const char*);
using SubstrFn=const char*(__cdecl*)(const char*,int);
static SizeFn originalSize;
static ReadFn originalRead;
static CountFn originalCount;
static SubstrFn originalSubstring;
using ExpandFn=const char*(__cdecl*)(const char*);
static ExpandFn originalExpand;
static std::array<std::string,8> expandedBuffers;
static size_t expandedSlot;
static std::array<std::string,8> pdaBuffers;
static size_t pdaSlot;
static const char* __cdecl expandHook(const char* text) {
    if(!text) return text;
    // Leave unlocalized native text on its original path. Token-only localized
    // text needs no copy into the engine's undocumented global scratch buffer.
    if(!strchr(text,marker)) return originalExpand(text);
    if(!strchr(text,11)) return text;
    try {
        auto& value=expandedBuffers[expandedSlot++ % expandedBuffers.size()];
        value=transport::expand(text,[](const char* token){return originalExpand(token);});
        return value.c_str();
    } catch(...) { log("TEXT expansion rejected; owned buffer limit"); return ""; }
}
static const char* __cdecl pdaExpand(const char* text) {
    try {
        auto& value=pdaBuffers[pdaSlot++ % pdaBuffers.size()];
        const char* expanded=expandHook(text);
        value=expanded?expanded:"";
        if(value.size()>1800) { log("PDA expanded text rejected; 2048-byte line budget"); return ""; }
        return value.c_str();
    } catch(...) { log("PDA expansion failed"); return ""; }
}
// The original 0x580640 takes its sole argument in EAX, not on the stack.
static __declspec(naked) void pdaExpandAdapter() {
    __asm {
        push eax
        call pdaExpand
        add esp,4
        ret
    }
}
static const char* __cdecl pdaWord(char* out,const char* text) {
    if(!text) { out[0]=0; return text; }
    if(strchr(text,marker)) return transport::word(out,text);
    char probe[191];
    const char* end=transport::word(probe,text);
    // Also bound the ASCII suffix after the final translated glyph. Short
    // native words retain the original E/J/K special handling.
    if(end-text==190 && *end && static_cast<signed char>(end[-1])>32)
        return transport::word(out,text);
    return reinterpret_cast<const char*(__cdecl*)(char*,const char*)>(0x580660)(out,text);
}
static const char* __cdecl pdaSkip(const char* text) { return transport::skip(text); }
static int __cdecl sizeHook(const char* name) {
    if(auto r=resource(name)) return static_cast<int>(r->bytes.size());
    return originalSize(name);
}
static int __cdecl readHook(const char* name,void* buffer,int size) {
    if(auto r=resource(name)) {
        if (!buffer || size<0 || static_cast<size_t>(size)>r->bytes.size()) { log("ATLAS read rejected: buffer/size mismatch"); return 0; }
        memcpy(buffer,r->bytes.data(),static_cast<size_t>(size));
        log("ATLAS read served"); return size;
    }
    return originalRead(name,buffer,size);
}
static void __cdecl bsHook() {
    auto table=*reinterpret_cast<char***>(0x90a338);
    size_t count=0;
    if(table) for(const auto& item:pack.bs) if(matches(table[item.index],item.source)) {
        table[item.index]=const_cast<char*>(item.target.c_str()); ++count;
    }
    char line[160]; sprintf_s(line,"BS substituted=%zu expected=%zu",count,pack.bs.size()); log(line);
    reinterpret_cast<void(__cdecl*)()>(0x540680)();
}
static void* __cdecl pdaHook(void* base) {
    void* result=reinterpret_cast<void*(__cdecl*)(void*)>(0x5804e0)(base);
    size_t count=0;
    if(result) for(const auto& item:pack.pda) {
        auto field=reinterpret_cast<char**>(static_cast<unsigned char*>(result)+item.index);
        if(matches(*field,item.source)) { *field=const_cast<char*>(item.target.c_str()); ++count; }
    }
    char line[160]; sprintf_s(line,"PDA substituted=%zu expected=%zu",count,pack.pda.size()); log(line);
    return result;
}
static int __cdecl modeHook(int) {
    auto old=reinterpret_cast<int(__cdecl*)(int)>(0x6103f0)(1);
    reinterpret_cast<int(__cdecl*)(int)>(0x610590)(*reinterpret_cast<int*>(0x9e88a4));
    log("FONT mode=1; descriptor refreshed"); return old;
}
static const char* nextGlyph(const char* p) {
    if(static_cast<unsigned char>(*p)==marker) {
        int n=0;
        for(int i=1;i<=4;++i) { if(p[i]<'0'||p[i]>'9') return p+1; n=n*10+p[i]-'0'; }
        if(n<1536 && !(p[5]>='0'&&p[5]<='9')) return p+5;
    }
    return p+1;
}
static int __cdecl countHook(const char* text) {
    if(!*reinterpret_cast<int*>(0x9e88a0)) return originalCount(text);
    auto p=reinterpret_cast<const char*(__cdecl*)(const char*)>(0x610260)(text);
    int count=0; if(p) while(*p) { p=nextGlyph(p); ++count; } return count;
}
static const char* __cdecl substringHook(const char* text,int count) {
    if(!*reinterpret_cast<int*>(0x9e88a0)) return originalSubstring(text,count);
    auto p=reinterpret_cast<const char*(__cdecl*)(const char*)>(0x610260)(text);
    if(p) while(count>0 && *p) { p=nextGlyph(p); --count; } return p;
}
struct Patch { uintptr_t address; std::vector<unsigned char> before,after; };
static bool write(uintptr_t address,const std::vector<unsigned char>& bytes) {
    DWORD old=0,ignored=0;
    if(!VirtualProtect(reinterpret_cast<void*>(address),bytes.size(),PAGE_EXECUTE_READWRITE,&old)) return false;
    memcpy(reinterpret_cast<void*>(address),bytes.data(),bytes.size());
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(address),bytes.size());
    VirtualProtect(reinterpret_cast<void*>(address),bytes.size(),old,&ignored); return true;
}
static std::vector<unsigned char> branch(uintptr_t from,const void* to,size_t size,unsigned char opcode) {
    std::vector<unsigned char> bytes(size,0x90); bytes[0]=opcode;
    uint32_t relative=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(to)-from-5);
    memcpy(bytes.data()+1,&relative,4); return bytes;
}
static void* trampoline(uintptr_t address,const std::vector<unsigned char>& first) {
    auto buffer=static_cast<unsigned char*>(VirtualAlloc(nullptr,first.size()+5,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!buffer) throw std::runtime_error("trampoline allocation failed");
    memcpy(buffer,first.data(),first.size());
    auto back=branch(reinterpret_cast<uintptr_t>(buffer+first.size()),reinterpret_cast<void*>(address+first.size()),5,0xe9);
    memcpy(buffer+first.size(),back.data(),5);
    DWORD old=0;
    if(!VirtualProtect(buffer,first.size()+5,PAGE_EXECUTE_READ,&old)) {
        VirtualFree(buffer,0,MEM_RELEASE); throw std::runtime_error("trampoline protection failed");
    }
    FlushInstructionCache(GetCurrentProcess(),buffer,first.size()+5); return buffer;
}
static const char* atlasPaths[]={"textures/localization/page0.raw","textures/localization/page1.raw","textures/localization/page2.raw",
    "textures/localization/page3.raw","textures/localization/page4.raw","textures/localization/page5.raw"};
static void install() {
    std::vector<Patch> patches;
    auto call=[&](uintptr_t a,std::initializer_list<unsigned char> b,const void* fn) { patches.push_back({a,b,branch(a,fn,b.size(),0xe8)}); };
    call(0x43e663,{0xe8,0x18,0x20,0x10,0x00},bsHook);
    call(0x583bb5,{0xe8,0x26,0xc9,0xff,0xff},pdaHook);
    call(0x611885,{0xe8,0x66,0xeb,0xff,0xff},modeHook);
    call(0x58074d,{0xe8,0x0e,0xff,0xff,0xff},pdaWord);
    call(0x580832,{0xe8,0xd9,0xfd,0xff,0xff},pdaSkip);
    call(0x580c2a,{0xe8,0x11,0xfa,0xff,0xff},pdaExpandAdapter);
    call(0x580c4c,{0xe8,0xef,0xf9,0xff,0xff},pdaExpandAdapter);
    for(uintptr_t a:{0x610a96,0x6119f3,0x611a59,0x611d1b,0x611d58,0x612561}) patches.push_back({a,{0x3c,0x2c},{0x3c,marker}});
    struct Hook { uintptr_t address; std::vector<unsigned char> before; const void* target; void** original; };
    std::vector<Hook> hooks={
        {0x610260,{0x53,0x8b,0x5c,0x24,0x08},expandHook,reinterpret_cast<void**>(&originalExpand)},
        {0x49ddf0,{0xa1,0xd0,0x0f,0x91,0x00},sizeHook,reinterpret_cast<void**>(&originalSize)},
        {0x49e4e0,{0xa1,0xd0,0x0f,0x91,0x00},readHook,reinterpret_cast<void**>(&originalRead)},
        {0x6119d0,{0x51,0xa1,0xa0,0x88,0x9e,0x00},countHook,reinterpret_cast<void**>(&originalCount)},
        {0x611a30,{0x51,0xa1,0xa0,0x88,0x9e,0x00},substringHook,reinterpret_cast<void**>(&originalSubstring)}};
    for(const auto& h:hooks) patches.push_back({h.address,h.before,branch(h.address,h.target,h.before.size(),0xe9)});
    for(unsigned int i=0;i<6;++i) {
        uintptr_t a=0x8ba860+i*32;
        uint32_t original=0x7de39c-i*28;
        uint32_t replacement=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(atlasPaths[i]));
        std::vector<unsigned char> before(4),after(4);
        memcpy(before.data(),&original,4); memcpy(after.data(),&replacement,4);
        patches.push_back({a,before,after}); patches.push_back({a+4,{0x9f},{0x1f}});
    }
    // All expected bytes are checked before any game-memory write.
    for(const auto& p:patches) if(memcmp(reinterpret_cast<void*>(p.address),p.before.data(),p.before.size())) {
        char message[100]; sprintf_s(message,"HOOK CONFLICT at %08lx; no patches installed",static_cast<unsigned long>(p.address)); log(message);
        throw std::runtime_error("expected original bytes mismatch");
    }
    for(const auto& h:hooks) *h.original=trampoline(h.address,h.before);
    size_t done=0;
    for(const auto& p:patches) {
        if(!write(p.address,p.after)) {
            while(done) { const auto& previous=patches[--done]; write(previous.address,previous.before); }
            throw std::runtime_error("patch failed; previous writes restored");
        }
        ++done;
    }
    log("HOOKS installed; FusionFix TextAtPointer/TextAtValue sites untouched; runtime acceptance pending");
}

extern "C" __declspec(dllexport) void __cdecl InitializeASI() {
    if(InterlockedCompareExchange(&initialized,1,0)) return;
    wchar_t own[MAX_PATH]{}; GetModuleFileNameW(module,own,MAX_PATH);
    directory=own; directory=directory.substr(0,directory.find_last_of(L"\\/")+1);
    try {
        wchar_t exe[MAX_PATH]{}; GetModuleFileNameW(nullptr,exe,MAX_PATH);
        if(reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr))!=0x400000 || hash(readFile(exe))!=expectedExe) {
            status=2; log("IDENTITY REJECTED; no game-memory access or writes"); return;
        }
        pack=parse(readFile(directory+L"localization\\locale.bin"));
        install(); status=1;
    } catch(const std::exception& e) { status=3; log(e.what()); }
}
extern "C" __declspec(dllexport) int __cdecl LocalizationStatus() { return status; }
// Offline harness exercises only owned data/memory, never game addresses.
extern "C" __declspec(dllexport) int __cdecl LocalizationSelfTest(const wchar_t* path) {
    try {
        auto data=readFile(path); auto parsed=parse(data);
        if(parsed.bs.empty()||parsed.pda.empty()) return 1;
        for(const auto& item:parsed.bs) {
            const char* p=item.target.c_str(); while(*p) p=nextGlyph(p);
            if(p!=item.target.c_str()+item.target.size()) return 2;
        }
        auto truncated=data; truncated.pop_back();
        try { parse(truncated); return 3; } catch(const std::exception&) {}
        auto badDds=data;
        const unsigned char magic[]={'D','D','S',' '};
        auto firstDds=std::search(badDds.begin(),badDds.end(),std::begin(magic),std::end(magic));
        if(firstDds==badDds.end()) return 8;
        *(firstDds+16)=1; // width 257 instead of native 256
        try { parse(badDds); return 9; } catch(const std::exception&) {}
        if(encoded(std::string("\x1f")+"00015") || encoded(std::string("\x1f")+"1536")) return 4;
        // Pure owned-buffer checks: never call native addresses from this host.
        if(!encoded(std::string("\x1f")+"0001\vI %1\n") || encoded("\vZ")) return 10;
        if(transport::budget("\vA\vB%1")!=365) return 18;
        const std::string atom=std::string("\x1f")+"0001";
        std::string longPda;
        for(int i=0;i<250;++i) longPda+=atom;
        const char* cursor=longPda.c_str();
        size_t atoms=0;
        char word[202]; memset(word,0x7f,sizeof(word));
        while(*cursor) {
            if(transport::skip(cursor)!=cursor) return 11;
            auto next=transport::word(word,cursor);
            if(next-cursor!=5 || std::string(word)!=atom || word[200]!=0x7f) return 12;
            cursor=next; ++atoms;
        }
        if(atoms!=250) return 13;
        const char* adapterInput=longPda.c_str();
        const char* adapterResult=nullptr;
        __asm {
            mov eax,adapterInput
            call pdaExpandAdapter
            mov adapterResult,eax
        }
        if(!adapterResult || strcmp(adapterResult,longPda.c_str()) || adapterResult==adapterInput) return 17;
        auto expanded=transport::expand((atom+"\vJ\vI"+atom).c_str(),[](const char* token){return token[1]=='J'?"":"'Key'";});
        if(expanded!=atom+"'Key'"+atom) return 14;
        std::string wide(500,'x');
        const char* rest=transport::word(word,wide.c_str());
        if(rest-wide.c_str()!=190 || strlen(word)!=190 || word[200]!=0x7f) return 15;
        // This wrapper branch is entirely owned code; no native fallback call.
        if(pdaWord(word,wide.c_str())!=wide.c_str()+190 || strlen(word)!=190) return 19;
        std::string edge(190,'x');
        if(*transport::word(word,edge.c_str()) || strlen(word)!=190) return 20;
        std::string tooLarge(4096,'x');
        try { transport::expand("\vI",[&](const char*){return tooLarge.c_str();}); return 21; }
        catch(const std::runtime_error&) {}
        for(const auto& item:parsed.pda) {
            auto expandedPda=transport::expand(item.target.c_str(),[](const char*){return "'Synthetic key'";});
            const char* p=expandedPda.c_str();
            while(*p) {
                const char* next=transport::word(word,p);
                if(next<=p || next>expandedPda.c_str()+expandedPda.size() || strlen(word)>190) return 16;
                p=next;
            }
        }
        auto memory=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
        if(!memory) return 5;
        const std::vector<unsigned char> baseline={1,2,3,4,5},modified={5,4,3,2,1};
        bool ok=write(reinterpret_cast<uintptr_t>(memory),baseline) && write(reinterpret_cast<uintptr_t>(memory),modified) &&
            memcmp(memory,modified.data(),5)==0 && write(reinterpret_cast<uintptr_t>(memory),baseline) && memcmp(memory,baseline.data(),5)==0;
        VirtualFree(memory,0,MEM_RELEASE);
        return ok?0:6;
    } catch(...) { return 7; }
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) { module=instance; DisableThreadLibraryCalls(instance); }
    return TRUE;
}
