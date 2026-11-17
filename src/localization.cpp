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
#include "glyph_batch.h"
#include "subtitle_layout.h"
#include "gameplay_captions.h"
#include <intrin.h>
#pragma intrinsic(_ReturnAddress)

static HMODULE module;
static LONG initialized;
static int status; // 0 not called; 1 installed; 2 identity rejected; 3 validation rejected
static std::wstring directory;
static constexpr char expectedExe[] = "4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda";
static constexpr unsigned char marker = 0x1f;
struct Text { uint32_t index; std::string source, target; std::vector<std::string> aliases; };
struct Resource { std::string name; std::vector<unsigned char> bytes; };
struct Pack { std::vector<Text> bs, pda, exe; std::vector<Resource> resources; bool hdAtlas{}; };
struct LiteralContract { uint32_t id; uintptr_t instruction, source; const char* expected; };
static const LiteralContract literalContracts[]={
    {1,0x4b6dd0,0x7daaa8,"Quick scroll"},
    {2,0x576a14,0x7dc280,"Button inoperative"}
};
static Pack pack;
static gameplay_captions::State GameplayCaptionState;

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
        if (ch=='%' && i+1<value.size() && ((value[i+1]>='1' && value[i+1]<='9') || value[i+1]=='s')) { i+=2; continue; }
        if (ch != marker || i+5>value.size()) return false;
        int n=0;
        for (size_t j=i+1;j<i+5;++j) {
            if (value[j]<'0'||value[j]>'9') return false;
            n=n*10+value[j]-'0';
        }
        if (n>=6144 || (i+5<value.size() && value[i+5]>='0' && value[i+5]<='9')) return false;
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
    const uint32_t format=number();
    if (format!=0x31504c53 && format!=0x32504c53 && format!=0x33504c53) throw std::runtime_error("invalid pack magic");
    uint32_t bs=number(), pda=number(), resources=number();
    const uint32_t exeCount=format!=0x31504c53?number():0;
    const uint32_t aliasCount=format==0x33504c53?number():0;
    if(aliasCount>bs*7u) throw std::runtime_error("invalid alias count");
    if (!bs || bs>6525 || !pda || pda>512 || exeCount>2 || (resources!=6 && resources!=7)) throw std::runtime_error("invalid pack counts");
    Pack result;
    auto texts=[&](std::vector<Text>& items,uint32_t count,bool isBs) {
        for (uint32_t i=0;i<count;++i) {
            Text t{number(),blob(),blob(),{}};
            if ((isBs && (t.index==0||t.index>=6526)) ||
                (!isBs && (t.index<32||t.index%4||t.index>79618)) ||
                t.source.empty() || t.source.size()>4096 ||
                t.source.find('\0')!=std::string::npos || !encoded(t.target) || t.target.size()>(isBs?transport::bsLimit(t.index):1800u))
                throw std::runtime_error("invalid text record");
            if(transport::budget(t.target,isBs?t.index:0)>(isBs?transport::bsExpandedLimit(t.index):1800u) ||
                (isBs && (t.index==601 || t.index==5224) && t.target.size()>10) ||
                (isBs && t.index>=6371 && t.index<=6504 && t.target.size()>27) ||
                (isBs && (t.index==6518 || t.index==6519) && t.target.size()>27))
                throw std::runtime_error("native consumer budget exceeded");
            if(t.target.find("%s")!=std::string::npos && (!isBs || t.index!=4511 || t.source!="Mode: %s" ||
                t.target.find("%s",t.target.find("%s")+2)!=std::string::npos))
                throw std::runtime_error("printf source contract mismatch");
            if(isBs && t.index==4511 && t.source=="Mode: %s" && t.target.find("%s")==std::string::npos)
                throw std::runtime_error("missing printf placeholder");
            for (const auto& prior: items) if (prior.index==t.index) throw std::runtime_error("duplicate text ID");
            items.push_back(std::move(t));
        }
    };
    texts(result.bs,bs,true); texts(result.pda,pda,false);
    for(uint32_t i=0;i<exeCount;++i) {
        Text t{number(),blob(),blob(),{}};
        const LiteralContract* contract=nullptr;
        for(const auto& c:literalContracts) if(c.id==t.index) contract=&c;
        if(!contract || t.source!=contract->expected || !encoded(t.target) || t.target.size()>64 ||
            t.target.find_first_of("\v%\t\n")!=std::string::npos)
            throw std::runtime_error("invalid executable text record");
        for(const auto& prior:result.exe) if(prior.index==t.index) throw std::runtime_error("duplicate executable text");
        result.exe.push_back(std::move(t));
    }
    for(uint32_t i=0;i<aliasCount;++i) {
        const uint32_t id=number(); auto source=blob();
        auto item=std::find_if(result.bs.begin(),result.bs.end(),[&](const Text& t){return t.index==id;});
        if(item==result.bs.end() || source.empty() || source.size()>4096 ||
           source.find('\0')!=std::string::npos || item->aliases.size()>=7 || source==item->source ||
           std::find(item->aliases.begin(),item->aliases.end(),source)!=item->aliases.end())
            throw std::runtime_error("invalid BS source alias");
        item->aliases.push_back(std::move(source));
    }
    size_t composedCount=0,composedBytes=8;
    for(const auto& item:result.bs) if(item.index>=3644 && item.index<=3648) { ++composedCount; composedBytes+=item.target.size(); }
    if(composedCount && (composedCount!=5 || composedBytes>4095)) throw std::runtime_error("terminal composition contract mismatch");
    for (uint32_t i=0;i<resources;++i) {
        auto name=blob(), data=blob();
        const bool fontPage=i<6;
        if (i==0) result.hdAtlas=data.size()==128+1024*1024;
        const uint32_t width=fontPage?(result.hdAtlas?1024:512):256, height=fontPage?width:64;
        const std::string expectedName=fontPage?"textures/localization/page"+std::to_string(i)+".dds":"textures/misc/nse_tv/loading.dds";
        if (name!=expectedName || data.size()!=128+width*height ||
            memcmp(data.data(),"DDS ",4) || memcmp(data.data()+84,"DXT3",4))
            throw std::runtime_error("invalid texture resource");
        auto dword=[&](size_t offset) { uint32_t value; memcpy(&value,data.data()+offset,4); return value; };
        if(dword(4)!=124 || dword(8)!=0x81007 || dword(12)!=height || dword(16)!=width ||
            dword(20)!=width*height || dword(28)!=1 || dword(76)!=32 || dword(80)!=4 || dword(108)!=0x1000)
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
static bool matchesText(const char* text,const Text& item) {
    if(matches(text,item.source)) return true;
    for(const auto& alias:item.aliases) if(matches(text,alias)) return true;
    return false;
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
using WrapFn=char*(__cdecl*)(const char*,float);
static WrapFn originalWrap;
static std::array<std::string,8> wrapBuffers;
static size_t wrapSlot;
using ComposeFn=void(__cdecl*)(const uint32_t*,char*,int);
static ComposeFn originalCompose=reinterpret_cast<ComposeFn>(0x5d0580);
static std::array<std::string,8> composedBuffers;
static size_t composedSlot;
// Only this exact terminal record is lifted out of the native 1024-byte caller
// buffer. Its five original IDs and separators are all validated before use.
static const char* __cdecl composeHook(const uint32_t* record,char* destination,int capacity) {
    if(record==reinterpret_cast<const uint32_t*>(0x89363c) && capacity==1024 && record[0]==5) {
        try {
            std::string out;
            auto table=*reinterpret_cast<const char***>(0x90a338);
            bool complete=table!=nullptr;
            for(uint32_t i=0;i<5 && complete;++i) {
                const uint32_t id=3644+i;
                const uint32_t separator=i<4?0x7db74c:0x7ccdf8;
                complete=record[1+i*2]==id && record[2+i*2]==separator;
                const Text* chosen=nullptr;
                for(const auto& item:pack.bs) if(item.index==id) { chosen=&item; break; }
                if(!complete || !chosen || !matchesText(table[id],*chosen)) { complete=false; break; }
                out+=chosen->target;
                if(i<4) out+="\n\n";
                if(out.size()>4095) throw std::runtime_error("terminal owned composition overflow");
            }
            if(complete) { auto& value=composedBuffers[composedSlot++ % composedBuffers.size()]; value=std::move(out); return value.c_str(); }
        } catch(...) { log("TERMINAL composition rejected; original path retained"); }
    }
    originalCompose(record,destination,capacity);
    return destination;
}
// The native call sites immediately use ESI/EDI as their wrap input. These
// cdecl bridges intentionally update that local register, leaving the caller's
// saved register on its stack intact; no other argument/stack shape changes.
static __declspec(naked) void composeToEsi() {
    __asm {
        push dword ptr [esp+12]
        push dword ptr [esp+12]
        push dword ptr [esp+12]
        call composeHook
        add esp,12
        mov esi,eax
        ret
    }
}
static __declspec(naked) void composeToEdi() {
    __asm {
        push dword ptr [esp+12]
        push dword ptr [esp+12]
        push dword ptr [esp+12]
        call composeHook
        add esp,12
        mov edi,eax
        ret
    }
}
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
static char* __cdecl wrapHook(const char* text,float width) {
    const uintptr_t caller=reinterpret_cast<uintptr_t>(_ReturnAddress());
    if(text && transport::longWrapCaller(caller)) {
        for(const auto& item:pack.bs) if(transport::deferred(item.index) && matchesText(text,item)) {
            text=item.target.c_str(); break;
        }
    }
    if(!text || !strchr(text,marker)) return originalWrap(text,width);
    try {
        // Copy before calling measure: measurement expands keys using its own
        // rotating buffers, and notice/mail callers subsequently mutate output.
        const char* expanded=expandHook(text);
        const std::string input=expanded?expanded:"";
        auto& value=wrapBuffers[wrapSlot++ % wrapBuffers.size()];
        value=transport::wrap(input,width,[](const char* word) {
            return reinterpret_cast<float(__cdecl*)(const char*)>(0x611940)(word);
        });
        if(caller==0x62fec7 && value.size()>511) {
            // Never overflow the original HUD's three 512-byte copies. Keep
            // every input character if an extreme width exhausts LF headroom.
            value=transport::hudBody(input,value);
            log("HUD wrap linebreak budget exceeded; full unwrapped input retained");
        }
        return value.data();
    } catch(...) { log("WRAP rejected; owned buffer budget"); static char empty[1]{}; return empty; }
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
    GameplayCaptionState.clear();
    auto table=*reinterpret_cast<char***>(0x90a338);
    size_t count=0;
    if(table) for(const auto& item:pack.bs) if(!transport::deferred(item.index) && matchesText(table[item.index],item)) {
        table[item.index]=const_cast<char*>(item.target.c_str()); ++count;
    }
    size_t deferred=0; for(const auto& item:pack.bs) if(transport::deferred(item.index)) ++deferred;
    char line[160]; sprintf_s(line,"BS substituted=%zu expected-direct=%zu deferred=%zu",count,pack.bs.size()-deferred,deferred); log(line);
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
        if(n<6144 && !(p[5]>='0'&&p[5]<='9')) return p+5;
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
// Independent captions follow actual speech lifetime events, not the native
// optional display bit. Source-bound locale text is the only content source.
extern "C" __declspec(noinline) const char* __cdecl GameplayCaptionLookup(uint32_t bs) {
    auto table=*reinterpret_cast<char***>(0x90a338);
    if(!table) return nullptr;
    for(const auto& item:pack.bs) if(item.index==bs) {
        const char* current=table[bs];
        if(current==item.target.c_str() || matchesText(current,item)) return item.target.c_str();
        return nullptr;
    }
    return nullptr;
}
extern "C" void* GameplayCaptionOriginal=nullptr;
extern "C" __declspec(noinline) void __cdecl GameplayCaptionObserve(uintptr_t owner,int event) {
    if(!owner) return;
    if(event==1 || event==3 || event==4) { GameplayCaptionState.finish(owner); return; }
    // 0=queued, 5=cancel queued, 6=request refused: never end the active voice.
    if(event!=2) return;
    const auto fields=reinterpret_cast<const uint32_t*>(owner);
    const int handle=static_cast<int>(fields[1]);
    const uint32_t bs=fields[2];
    float remaining;
    memcpy(&remaining,fields+6,sizeof(remaining));
    // Match the original dispatcher semantics: real audio waits for readiness;
    // an armed, duration-driven cue need not have an audio handle of its own.
    if(!bs || (handle<=0 && !gameplay_captions::timedCue(handle,fields[18],remaining))) {
        GameplayCaptionState.finish(owner); return;
    }
    const auto old=GameplayCaptionState.find(owner);
    if(old && old->bs==bs && old->handle==handle) return;
    GameplayCaptionState.finish(owner);
    const char* text=GameplayCaptionLookup(bs);
    if(!text || (handle>0 && !reinterpret_cast<int(__cdecl*)(int)>(0x60d8f0)(handle))) return;
    GameplayCaptionState.active(owner,bs,handle,static_cast<int>(fields[4]),text);
}
extern "C" __declspec(naked) void GameplayCaptionEventHook() {
    __asm {
        pushfd
        pushad
        push edx
        push esi
        call GameplayCaptionObserve
        add esp,8
        popad
        popfd
        jmp dword ptr [GameplayCaptionOriginal]
    }
}
extern "C" __declspec(noinline) void __cdecl GameplayCaptionResetHook() {
    GameplayCaptionState.clear();
    reinterpret_cast<void(__cdecl*)()>(0x63f600)();
}
extern "C" __declspec(noinline) void __cdecl GameplayCaptionDrawHook() {
    // This call site is already behind the native HUD/pause gates. A scripted
    // sequence flag is not proof that speech has a separate timed caption;
    // do not suppress missing dialogue merely because such a sequence exists.
    const auto voice=GameplayCaptionState.choose();
    if(!voice) { reinterpret_cast<void(__cdecl*)()>(0x63f830)(); return; }
    if(!reinterpret_cast<int(__cdecl*)()>(0x50bd60)()) return;
    const int width=*reinterpret_cast<int*>(0x872500),height=*reinterpret_cast<int*>(0x872504);
    if(width<=0 || height<=0 || width>16384 || height>16384) return;
    subtitle_layout::Scope scope{};
    subtitle_layout::begin(scope,21);
    const float scale=subtitle_layout::screenScale(height);
    const float available=static_cast<float>(width)-40.0f*scale;
    if(available<=0) { subtitle_layout::end(scope); return; }
    auto wrap=reinterpret_cast<char*(__cdecl*)(const char*,float)>(0x611c70);
    const char* text=wrap(voice->text,available);
    int textWidth=0,textHeight=0;
    reinterpret_cast<void(__cdecl*)(int*,int*,const char*)>(0x611a90)(&textWidth,&textHeight,text);
    // Extremely long entries fit within a bounded part of the viewport without
    // truncating any words. Normal dialogue retains the resolution-scaled size.
    if(textHeight>height/3 && textHeight>0) {
        const float fit=static_cast<float>(height/3)/static_cast<float>(textHeight);
        scope.style.x*=fit; scope.style.y*=fit;
        text=wrap(voice->text,available);
        reinterpret_cast<void(__cdecl*)(int*,int*,const char*)>(0x611a90)(&textWidth,&textHeight,text);
    }
    int x=(width-textWidth)/2,y=height-static_cast<int>(30.0f*scale)-textHeight;
    const auto blend=reinterpret_cast<int(__cdecl*)(int)>(0x40d110);
    const int previous=blend(1);
    // Do not submit the game's textured panel: its side slices show through
    // around an otherwise transparent subtitle. Keep native text submission.
    reinterpret_cast<void(__cdecl*)(int*,int*,const char*,uint32_t)>(0x6132e0)(&x,&y,text,0xffffff80);
    blend(previous);
    subtitle_layout::end(scope);
}
// These three cdecl symbols stay visible in the link MAP for instruction-level
// offline replay. Only the four guarded text sites below can enter them in-game.
static glyph_batch::State textBatch;
extern "C" __declspec(noinline) int __cdecl BeginTextBatchHook(int format,int mode,int count,int texture) {
    const int result=reinterpret_cast<int(__cdecl*)(int,int,int,int)>(0x40ded0)(format,mode,count,texture);
    textBatch.begun(result!=0 && *reinterpret_cast<uint32_t*>(0x8daf6c)==0 &&
                    *reinterpret_cast<uint32_t*>(0x8daf00)!=0);
    return result;
}
extern "C" __declspec(noinline) void __cdecl EndTextBatchHook() {
    textBatch.finish(reinterpret_cast<void(__cdecl*)()>(0x40e100));
}
extern "C" __declspec(noinline) void __cdecl BindTextTextureHook(int texture) {
    textBatch.bind(texture,*reinterpret_cast<uint8_t*>(0x9e88bc),
                   reinterpret_cast<void(__cdecl*)()>(0x40e100),
                   reinterpret_cast<void(__cdecl*)(int)>(0x40fc20));
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
    for(const auto& item:pack.exe) for(const auto& c:literalContracts) if(item.index==c.id) {
        if(!matches(reinterpret_cast<const char*>(c.source),item.source)) throw std::runtime_error("executable text source mismatch");
        std::vector<unsigned char> before(5,0x68),after(5,0x68);
        const uint32_t original=static_cast<uint32_t>(c.source);
        const uint32_t replacement=static_cast<uint32_t>(reinterpret_cast<uintptr_t>(item.target.c_str()));
        memcpy(before.data()+1,&original,4); memcpy(after.data()+1,&replacement,4);
        patches.push_back({c.instruction,before,after});
    }
    auto call=[&](uintptr_t a,std::initializer_list<unsigned char> b,const void* fn) { patches.push_back({a,b,branch(a,fn,b.size(),0xe8)}); };
    // Scope resolution scaling to the timed cutscene subtitle layout only.
    // Measurement, wrapping and drawing share one private style; restore on exit.
    call(0x543031,{0xe8,0x5a,0xd5,0x0c,0x00},subtitle_layout::beginCutscene);
    call(0x63d78a,{0xe8,0xa1,0x20,0x00,0x00},GameplayCaptionDrawHook);
    call(0x63d494,{0xe8,0x67,0x21,0x00,0x00},GameplayCaptionResetHook);
    patches.push_back({0x5431e8,{0xd9,0x05,0xb4,0x74,0x96,0x00},
                       branch(0x5431e8,subtitle_layout::endCutsceneHook,6,0xe9)});
    call(0x610efd,{0xe8,0xce,0xcf,0xdf,0xff},BeginTextBatchHook);
    patches.push_back({0x610fa8,{0xe9,0x53,0xd1,0xdf,0xff},branch(0x610fa8,EndTextBatchHook,5,0xe9)});
    call(0x6125c1,{0xe8,0x5a,0xd6,0xdf,0xff},BindTextTextureHook);
    call(0x612677,{0xe8,0xa4,0xd5,0xdf,0xff},BindTextTextureHook);
    call(0x43e663,{0xe8,0x18,0x20,0x10,0x00},bsHook);
    call(0x583bb5,{0xe8,0x26,0xc9,0xff,0xff},pdaHook);
    call(0x611885,{0xe8,0x66,0xeb,0xff,0xff},modeHook);
    call(0x5d0643,{0xe8,0x38,0xff,0xff,0xff},composeToEsi);
    call(0x5d06fb,{0xe8,0x80,0xfe,0xff,0xff},composeToEdi);
    call(0x58074d,{0xe8,0x0e,0xff,0xff,0xff},pdaWord);
    call(0x580832,{0xe8,0xd9,0xfd,0xff,0xff},pdaSkip);
    call(0x580c2a,{0xe8,0x11,0xfa,0xff,0xff},pdaExpandAdapter);
    call(0x580c4c,{0xe8,0xef,0xf9,0xff,0xff},pdaExpandAdapter);
    for(uintptr_t a:{0x610a96,0x6119f3,0x611a59,0x611d1b,0x611d58,0x612561}) patches.push_back({a,{0x3c,0x2c},{0x3c,marker}});
    // 32x32 cells/page, still 16px cells. UV is pixel*16 and normalized by
    // actual DDS dimensions at 0x40DB70; no UV halving or measure patch.
    patches.push_back({0x612595,{0x81,0xe2,0xff,0,0,0},{0x81,0xe2,0xff,3,0,0}});
    patches.push_back({0x6125a7,{0xc1,0xfe,8},{0xc1,0xfe,10}});
    patches.push_back({0x6125cf,{0x81,0xe1,0x0f,0,0,0x80},{0x81,0xe1,0x1f,0,0,0x80}});
    patches.push_back({0x6125d8,{0x83,0xc9,0xf0},{0x83,0xc9,0xe0}});
    patches.push_back({0x6125dc,{0xc1,0xe6,8},{0xc1,0xe6,10}});
    patches.push_back({0x6125e4,{0x83,0xe2,0x0f},{0x83,0xe2,0x1f}});
    patches.push_back({0x6125fc,{0xc1,0xf8,4},{0xc1,0xf8,5}});
    if(pack.hdAtlas) {
        // UV only: row/column to pixels, then pixels to 1/16 units. Both
        // right/bottom stop at pixel 31 plus the native half-texel bias.
        patches.push_back({0x612603,{0xc1,0xe0,4},{0xc1,0xe0,5}});
        patches.push_back({0x612606,{0x8d,0x50,0x10},{0x8d,0x50,0x1f}});
        patches.push_back({0x612615,{0xc1,0xe1,4},{0xc1,0xe1,5}});
        patches.push_back({0x612621,{0x81,0xc2,0xf8,0,0,0},{0x81,0xc2,0xf0,1,0,0}});
    }
    struct Hook { uintptr_t address; std::vector<unsigned char> before; const void* target; void** original; };
    std::vector<Hook> hooks={
        {0x456610,{0x85,0xc0,0x57,0x8b,0xfa},GameplayCaptionEventHook,&GameplayCaptionOriginal},
        {0x611c70,{0x81,0xec,0x04,0x02,0,0},wrapHook,reinterpret_cast<void**>(&originalWrap)},
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
    log("TEXT batch texture-transition flush installed; normal pass only");
    log(pack.hdAtlas?"FONT 1024 atlas UV enabled":"FONT legacy 512 atlas UV retained");
    log("SUBTITLE cutscene layout scales with render height; private style restored after captions");
    log("CAPTIONS speech lifecycle observer and independent gameplay renderer installed; source-bound locale text; runtime acceptance pending");
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
        if(!gameplay_captions::selfTest()) return 52;
        glyph_batch::State batch;
        uint8_t pending=0; std::string calls;
        auto end=[&]() { calls+="E"; };
        auto bind=[&](int texture) { calls+=std::to_string(texture); };
        batch.bind(1,pending,end,bind);
        if(calls!="1" || pending || batch.active) return 43;
        batch.begun(true); batch.bind(2,pending,end,bind);
        if(calls!="1E2" || pending!=1 || batch.active) return 44;
        pending=0; batch.begun(false); batch.bind(3,pending,end,bind);
        if(calls!="1E23" || pending) return 45;
        batch.begun(true); batch.finish(end);
        if(calls!="1E23E" || batch.active) return 46;
        auto data=readFile(path); auto parsed=parse(data);
        if(parsed.bs.empty()||parsed.pda.empty()) return 1;
        if(data[3]=='2' || data[3]=='3') {
            size_t exeAt=data[3]=='3'?24:20;
            for(const auto& t:parsed.bs) exeAt+=12+t.source.size()+t.target.size();
            for(const auto& t:parsed.pda) exeAt+=12+t.source.size()+t.target.size();
            size_t exeBytes=0;
            for(const auto& t:parsed.exe) exeBytes+=12+t.source.size()+t.target.size();
            const size_t aliasAt=exeAt+exeBytes;
            size_t aliasBytes=0;
            for(const auto& t:parsed.bs) for(const auto& a:t.aliases) aliasBytes+=8+a.size();
            auto legacyPack=data;
            if(data[3]=='3') {
                legacyPack.erase(legacyPack.begin()+aliasAt,legacyPack.begin()+aliasAt+aliasBytes);
                auto slp2=legacyPack;
                slp2.erase(slp2.begin()+20,slp2.begin()+24); slp2[3]='2';
                if(parse(slp2).bs.size()!=parsed.bs.size()) return 40;
                // Exercise malformed sparse alias records through the real parser.
                auto aliasFixture=[&](const std::vector<std::pair<uint32_t,std::string>>& aliases) {
                    std::vector<unsigned char> value(data.begin(),data.begin()+aliasAt);
                    const uint32_t count=static_cast<uint32_t>(aliases.size());
                    memcpy(value.data()+20,&count,4);
                    auto append=[&](uint32_t n) { const auto b=reinterpret_cast<const unsigned char*>(&n); value.insert(value.end(),b,b+4); };
                    for(const auto& a:aliases) {
                        append(a.first); append(static_cast<uint32_t>(a.second.size()));
                        value.insert(value.end(),a.second.begin(),a.second.end());
                    }
                    value.insert(value.end(),data.begin()+aliasAt+aliasBytes,data.end());
                    return value;
                };
                auto rejected=[&](const std::vector<std::pair<uint32_t,std::string>>& aliases) {
                    try { parse(aliasFixture(aliases)); return false; } catch(const std::exception&) { return true; }
                };
                const auto& first=parsed.bs.front();
                if(!rejected({{0,"not-a-source"}}) || !rejected({{first.index,first.source}}) ||
                   !rejected({{first.index,""}}) || !rejected({{first.index,std::string("a\0b",3)}}) ||
                   !rejected({{first.index,std::string(4097,'x')}}) ||
                   !rejected({{first.index,"alias"},{first.index,"alias"}})) return 47;
                std::vector<std::pair<uint32_t,std::string>> excess;
                for(uint32_t i=0;i<8;++i) excess.push_back({first.index,"alias"+std::to_string(i)});
                if(!rejected(excess)) return 48;
                auto badCount=aliasFixture({}); uint32_t count=static_cast<uint32_t>(parsed.bs.size()*7+1);
                memcpy(badCount.data()+20,&count,4);
                try { parse(badCount); return 49; } catch(const std::exception&) {}
                auto shortAlias=aliasFixture({{first.index,"alias"}}); shortAlias.resize(aliasAt+9);
                try { parse(shortAlias); return 50; } catch(const std::exception&) {}
            }
            legacyPack.erase(legacyPack.begin()+exeAt,legacyPack.begin()+exeAt+exeBytes);
            legacyPack.erase(legacyPack.begin()+16,legacyPack.begin()+(data[3]=='3'?24:20));
            legacyPack[3]='1';
            if(!parse(legacyPack).exe.empty()) return 37;
            if(!parsed.exe.empty()) {
                auto badLiteral=data;
                badLiteral[exeAt+8]^=1; // Source spelling must match fixed contract.
                try { parse(badLiteral); return 38; } catch(const std::exception&) {}
                badLiteral=data; badLiteral[exeAt]=99;
                try { parse(badLiteral); return 39; } catch(const std::exception&) {}
            }
        }
        const Text matchFixture{1,"Primary","",{"Alias","Alias!"}};
        if(!matchesText("Primary",matchFixture) || !matchesText("Alias!",matchFixture) ||
           matchesText("Alias!!",matchFixture) || matchesText("Alia",matchFixture) ||
           matchesText(nullptr,matchFixture)) return 51;
        for(const auto& item:parsed.bs) {
            if(!matchesText(item.source.c_str(),item)) return 41;
            for(const auto& alias:item.aliases) {
                if(!matchesText(alias.c_str(),item)) return 42;
            }
            const char* p=item.target.c_str(); while(*p) p=nextGlyph(p);
            if(p!=item.target.c_str()+item.target.size()) return 2;
        }
        auto truncated=data; truncated.pop_back();
        try { parse(truncated); return 3; } catch(const std::exception&) {}
        auto badDds=data;
        const unsigned char magic[]={'D','D','S',' '};
        auto firstDds=std::search(badDds.begin(),badDds.end(),std::begin(magic),std::end(magic));
        if(firstDds==badDds.end()) return 8;
        *(firstDds+16)=1; // width 513 instead of expanded 512
        try { parse(badDds); return 9; } catch(const std::exception&) {}
        if(parsed.resources.size()==7) {
            auto badUi=data;
            const std::string uiName="textures/misc/nse_tv/loading.dds";
            auto name=std::search(badUi.begin(),badUi.end(),uiName.begin(),uiName.end());
            if(name==badUi.end()) return 33;
            *name='X';
            try { parse(badUi); return 34; } catch(const std::exception&) {}
            auto legacy=data;
            legacy.resize(legacy.size()-8-uiName.size()-16512);
            legacy[12]=6;
            if(parse(legacy).resources.size()!=6) return 35;
            badUi=data;
            const size_t lastDds=badUi.size()-16512;
            badUi[lastDds+16]=1; // exact 256-pixel UI contract, not arbitrary resources
            try { parse(badUi); return 36; } catch(const std::exception&) {}
        }
        if(encoded(std::string("\x1f")+"00015") || encoded(std::string("\x1f")+"6144")) return 4;
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
        if(transport::bsLimit(5503)!=4095 || transport::bsLimit(850)!=255) return 22;
        const auto measure=[](const char* text) { float size=0; while(*text) { const size_t n=transport::glyph(text); text+=n?n:1; ++size; } return size; };
        auto wrapped=transport::wrap(longPda,10.f,measure);
        if(std::count(wrapped.begin(),wrapped.end(),'\n')!=24) return 23;
        std::string joined=wrapped; joined.erase(std::remove(joined.begin(),joined.end(),'\n'),joined.end());
        if(joined!=longPda || wrapped.size()!=longPda.size()+24) return 24;
        auto asciiWrapped=transport::wrap("one two three",7.f,measure);
        if(asciiWrapped!="one two\nthree" || transport::wrap(longPda,0.f,measure)!=longPda) return 25;
        auto mutableText=transport::wrap(atom+"\n"+atom,10.f,measure);
        mutableText.data()[5]=0;
        if(strcmp(mutableText.c_str(),atom.c_str()) || longPda.substr(0,10)!=atom+atom) return 26;
        auto byteCapped=transport::wrap(longPda,10000.f,measure);
        if(std::count(byteCapped.begin(),byteCapped.end(),'\n')!=4) return 27;
        size_t lineBytes=0;
        for(char c:byteCapped) { if(c=='\n') lineBytes=0; else if(++lineBytes>250) return 28; }
        if(!transport::deferred(5494) || transport::deferred(5503) ||
           !transport::longWrapCaller(0x5e2b17) || transport::longWrapCaller(0x62fec7) ||
           transport::longWrapCaller(0x5d0653)) return 29;
        if(transport::hudBody(std::string(510,'x'),std::string(511,'y')).size()!=511 ||
           transport::hudBody(std::string(510,'x'),std::string(512,'y'))!=std::string(510,'x')) return 30;
        try { transport::hudBody(std::string(511,'x'),"x"); return 31; } catch(const std::runtime_error&) {}
        char composeDestination[16]{};
        const char* composeResult=nullptr;
        ComposeFn savedCompose=originalCompose;
        originalCompose=[](const uint32_t*,char* target,int capacity) { if(capacity==16) strcpy_s(target,16,"owned"); };
        __asm {
            push esi
            push 16
            lea eax,composeDestination
            push eax
            push 0
            call composeToEsi
            add esp,12
            mov composeResult,esi
            pop esi
        }
        bool esiOkay=composeResult==composeDestination && strcmp(composeDestination,"owned")==0;
        composeDestination[0]=0;
        __asm {
            push edi
            push 16
            lea eax,composeDestination
            push eax
            push 0
            call composeToEdi
            add esp,12
            mov composeResult,edi
            pop edi
        }
        originalCompose=savedCompose;
        if(!esiOkay || composeResult!=composeDestination || strcmp(composeDestination,"owned")) return 32;
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
