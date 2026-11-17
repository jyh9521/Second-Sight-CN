// Optional 32-bit ASI for the pinned offline PC game. No rendering hooks.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <atomic>
#include <array>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include "gameplay_tweaks_sites.h"

using namespace gameplay_tweaks;
enum Option : unsigned { Health=1, Power=2, Invisible=4 };
static HMODULE module;
static LONG initialized;
static int status;
static std::wstring directory;
extern "C" { std::atomic<unsigned> TweakOptions{0}; }
static constexpr uintptr_t primaryContextAddress=0xa1d604;
static constexpr uintptr_t actorOffset=0x20, hp=0x208, maxHp=0x20c;
static constexpr uintptr_t fuel=0xee0, maxFuel=0xee8, powers=0xec8;

static void log(const char* message) {
    FILE* f=nullptr;
    if(!_wfopen_s(&f,(directory+L"SecondSight.GameplayTweaks.log").c_str(),L"ab")) {
        fprintf(f,"%s\r\n",message); fclose(f);
    }
}
static bool shaMatches(const wchar_t* fileName,const char* expected) {
    HANDLE f=CreateFileW(fileName,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_FLAG_SEQUENTIAL_SCAN,nullptr);
    if(f==INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE alg=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
    bool ok=BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)==0 &&
            BCryptCreateHash(alg,&hash,nullptr,0,nullptr,0,0)==0;
    unsigned char buffer[16384], digest[32]{}; DWORD count=0;
    while(ok) {
        ok=ReadFile(f,buffer,sizeof(buffer),&count,nullptr)!=FALSE;
        if(!ok || !count) break;
        ok=BCryptHashData(hash,buffer,count,0)==0;
    }
    ok=ok && BCryptFinishHash(hash,digest,sizeof(digest),0)==0;
    if(hash) BCryptDestroyHash(hash);
    if(alg) BCryptCloseAlgorithmProvider(alg,0);
    CloseHandle(f);
    char hex[65]{};
    for(size_t i=0;i<sizeof(digest);++i) sprintf_s(hex+2*i,3,"%02x",digest[i]);
    return ok && strcmp(hex,expected)==0;
}
static uint32_t& cell(uintptr_t a) { return *reinterpret_cast<uint32_t*>(a); }
static uintptr_t context() { return cell(primaryContextAddress); }
static uintptr_t actor(uintptr_t ctx) { return ctx?cell(ctx+actorOffset):0; }
static bool positive(uint32_t bits) { return bits>0 && bits<0x7f800000u; }

// The integer-only helpers never touch the pending x87 value in a write hook.
extern "C" __declspec(noinline) uint32_t __cdecl TweakHealth(uintptr_t victim) {
    if(!(TweakOptions.load(std::memory_order_relaxed)&Health) || !victim || victim!=actor(context()) ||
       !positive(cell(victim+hp))) return 0;
    const auto limit=cell(victim+maxHp);
    return positive(limit)?limit:0;
}
extern "C" __declspec(noinline) uint32_t __cdecl TweakPower(uintptr_t state) {
    if(!(TweakOptions.load(std::memory_order_relaxed)&Power)) return 0;
    const auto ctx=context();
    const auto player=actor(ctx);
    if(!player || state!=ctx+powers || !positive(cell(player+hp))) return 0;
    const auto limit=cell(ctx+maxFuel);
    return positive(limit)?limit:0;
}
extern "C" __declspec(noinline) uint32_t __cdecl TweakHidden(uintptr_t observer,uintptr_t target) {
    return (TweakOptions.load(std::memory_order_relaxed)&Invisible) && observer && target!=observer &&
           target && target==actor(context()) && positive(cell(target+hp));
}
extern "C" __declspec(noinline) void __cdecl TweakRefill() {
    if(!TweakOptions.load(std::memory_order_relaxed)) return;
    const auto ctx=context(), player=actor(ctx);
    if(!player) return;
    if(const auto max=TweakHealth(player)) cell(player+hp)=max;
    if(const auto max=TweakPower(ctx+powers)) cell(ctx+fuel)=max;
}
#define SAVE_AND_GET(reg, helper) \
    __asm pushfd \
    __asm pushad \
    __asm push reg \
    __asm call helper \
    __asm add esp,4 \
    __asm test eax,eax
#define RESTORE_REGS __asm popad __asm popfd
#define CONTINUE_AT(addr) __asm push addr __asm ret

#define HP_HOOK(name,resume) \
    extern "C" __declspec(naked) void name() { \
        SAVE_AND_GET(eax,TweakHealth) \
        __asm jz original \
        __asm mov edx,[esp+28] \
        __asm mov [edx+208h],eax \
        __asm fstp st(0) \
        RESTORE_REGS CONTINUE_AT(resume) \
        __asm original: \
        RESTORE_REGS \
        __asm fstp dword ptr [eax+208h] \
        CONTINUE_AT(resume) \
    }
HP_HOOK(TweakHpNormal,005DFF26h)
HP_HOOK(TweakHpAlt,005E1985h)

// On the override branch, preserve the x87 depth and exact skipped register
// side effects. Charm also compares ST(0), so replace that value, not only RAM.
#define CLEAR_EDI __asm xor edi,edi
#define ENERGY_HOOK(name,reg,saved,resume,originalExtra) \
    extern "C" __declspec(naked) void name() { \
        SAVE_AND_GET(reg,TweakPower) \
        __asm jz original \
        __asm mov edx,[esp+saved] \
        __asm mov [edx+18h],eax \
        __asm fstp st(0) \
        RESTORE_REGS \
        originalExtra \
        CONTINUE_AT(resume) \
        __asm original: \
        RESTORE_REGS \
        __asm fsubr dword ptr [reg+18h] \
        originalExtra \
        __asm fstp dword ptr [reg+18h] \
        CONTINUE_AT(resume) \
    }
ENERGY_HOOK(TweakPower856,edi,0,005CA85Bh,)
ENERGY_HOOK(TweakPower9bf,edi,0,005CA9C5h,)
ENERGY_HOOK(TweakPowerc56,ebp,8,005CAC5Ch,)
ENERGY_HOOK(TweakPowerd9f,edi,0,005CADA5h,)
ENERGY_HOOK(TweakPower0df,ebp,8,005CB0E7h,CLEAR_EDI)
ENERGY_HOOK(TweakPower693,ebx,16,005CB699h,)
ENERGY_HOOK(TweakPowerf02,esi,4,005CBF08h,)
extern "C" __declspec(naked) void TweakPower751() {
    SAVE_AND_GET(esi,TweakPower)
    __asm jz original
    __asm mov edx,[esp+4]
    __asm mov [edx+18h],eax
    __asm fstp st(0)
    __asm fld dword ptr [edx+18h]
    RESTORE_REGS CONTINUE_AT(005CB757h)
    __asm original:
    RESTORE_REGS
    __asm fsubr dword ptr [esi+18h]
    __asm fst dword ptr [esi+18h]
    CONTINUE_AT(005CB757h)
}
extern "C" __declspec(naked) void TweakPerception() {
    __asm pushfd
    __asm pushad
    __asm push [esp+44]
    __asm push [esp+44]
    __asm call TweakHidden
    __asm add esp,8
    __asm test eax,eax
    __asm jz original
    RESTORE_REGS
    __asm mov eax,0
    __asm ret
    __asm original:
    RESTORE_REGS
    __asm sub esp,48h
    __asm mov eax,[esp+58h]
    CONTINUE_AT(0048D7C7h)
}
extern "C" __declspec(naked) void TweakTick() {
    __asm pushfd
    __asm pushad
    __asm call TweakRefill
    RESTORE_REGS
    CONTINUE_AT(005CFBC0h)
}
static const void* const targets[]={
    TweakHpNormal,TweakHpAlt,TweakPower856,TweakPower9bf,TweakPowerc56,TweakPowerd9f,
    TweakPower0df,TweakPower693,TweakPower751,TweakPowerf02,TweakPerception,TweakTick
};
static_assert(std::size(targets)==sites.size());
static bool install() {
    // For the authenticated mapped image, validate every exact original opcode
    // before acquiring permission to write any. No scan or fallback addresses.
    for(const auto& s:sites) {
        if(memcmp(reinterpret_cast<void*>(s.va),s.before.data(),s.size)) {
            char message[96]{};
            sprintf_s(message,"TWEAKS SITE CONFLICT %08lx; no writes",static_cast<unsigned long>(s.va));
            log(message); return false;
        }
    }
    std::array<DWORD,sites.size()> protections{};
    size_t prepared=0;
    for(;prepared<sites.size();++prepared) {
        const auto& s=sites[prepared];
        if(!VirtualProtect(reinterpret_cast<void*>(s.va),s.size,PAGE_EXECUTE_READWRITE,&protections[prepared])) break;
    }
    const bool ready=prepared==sites.size();
    bool ok=false;
    if(ready) {
        for(size_t i=0;i<sites.size();++i) {
            const auto& s=sites[i];
            const auto bytes=encoding(s,reinterpret_cast<uintptr_t>(targets[i]));
            memcpy(reinterpret_cast<void*>(s.va),bytes.data(),s.size);
        }
        ok=FlushInstructionCache(GetCurrentProcess(),nullptr,0)!=FALSE;
        if(!ok) {
            for(const auto& s:sites) memcpy(reinterpret_cast<void*>(s.va),s.before.data(),s.size);
            FlushInstructionCache(GetCurrentProcess(),nullptr,0);
        }
    }
    // Reverse order is required for multiple windows on the same page.
    while(prepared) {
        --prepared;
        const auto& s=sites[prepared]; DWORD unused=0;
        if(!VirtualProtect(reinterpret_cast<void*>(s.va),s.size,protections[prepared],&unused)) ok=false;
    }
    return ok;
}

struct Panel {
    HWND game=nullptr, window=nullptr;
    bool shown=false, f1=false;
    float scale=1;
    HFONT font=nullptr;
    std::wstring ini;
    const wchar_t* label(const wchar_t* key,const wchar_t* fallback,wchar_t (&buffer)[96]) const {
        GetPrivateProfileStringW(L"Menu",key,fallback,buffer,static_cast<DWORD>(std::size(buffer)),ini.c_str());
        return buffer;
    }
    int px(int v) const { return static_cast<int>(scale*static_cast<float>(v)+0.5f); }
    void hide(bool focus) {
        shown=false;
        ShowWindow(window,SW_HIDE);
        if(focus && IsWindow(game) && !IsIconic(game)) SetForegroundWindow(game);
    }
    void toggle() {
        if(shown) { hide(true); return; }
        RECT rect{}, panel{};
        if(!GetWindowRect(game,&rect) || !GetWindowRect(window,&panel)) return;
        SetWindowPos(window,HWND_TOP,rect.left+(rect.right-rect.left-panel.right+panel.left)/2,
                     rect.top+(rect.bottom-rect.top-panel.bottom+panel.top)/2,0,0,SWP_NOSIZE|SWP_NOACTIVATE);
        shown=true;
        ShowWindow(window,SW_SHOW);
        SetForegroundWindow(window);
        if(GetForegroundWindow()!=window) { hide(false); return; }
        ClipCursor(nullptr);
    }
    void timer() {
        if(!IsWindow(game)) { DestroyWindow(window); return; }
        const auto foreground=GetForegroundWindow();
        const bool pressed=(GetAsyncKeyState(VK_F1)&0x8000)!=0;
        const bool edge=keyEdge(f1,pressed,foreground==game || foreground==window);
        if(shown && foreground!=window) hide(false);
        if(edge && IsWindowVisible(game) && !IsIconic(game)) toggle();
        if(shown && (GetAsyncKeyState(VK_ESCAPE)&0x8000)) hide(true);
    }
    static LRESULT CALLBACK proc(HWND h,UINT msg,WPARAM w,LPARAM l) {
        if(msg==WM_NCCREATE) {
            const auto p=static_cast<Panel*>(reinterpret_cast<CREATESTRUCTW*>(l)->lpCreateParams);
            SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(p));
            p->window=h;
        }
        const auto p=reinterpret_cast<Panel*>(GetWindowLongPtrW(h,GWLP_USERDATA));
        if(p) switch(msg) {
            case WM_TIMER: p->timer();return 0;
            case WM_CLOSE: p->hide(true);return 0;
            case WM_DESTROY: PostQuitMessage(0);return 0;
            case WM_COMMAND:
                if(HIWORD(w)==BN_CLICKED && l) {
                    const unsigned id=LOWORD(w);
                    if(id==200) { p->hide(true);return 0; }
                    if(id>=100 && id<103) {
                        const unsigned option=1u<<(id-100);
                        if(SendMessageW(reinterpret_cast<HWND>(l),BM_GETCHECK,0,0)==BST_CHECKED)
                            TweakOptions.fetch_or(option,std::memory_order_relaxed);
                        else TweakOptions.fetch_and(~option,std::memory_order_relaxed);
                        return 0;
                    }
                }
                break;
        }
        return DefWindowProcW(h,msg,w,l);
    }
};
static BOOL CALLBACK findGame(HWND window,LPARAM out) {
    DWORD pid=0;
    GetWindowThreadProcessId(window,&pid);
    if(pid!=GetCurrentProcessId() || GetWindow(window,GW_OWNER) || !IsWindowVisible(window)) return TRUE;
    wchar_t name[64]{};
    if(!GetClassNameW(window,name,static_cast<int>(std::size(name))) || wcscmp(name,L"Direct3DWindowClass")) return TRUE;
    *reinterpret_cast<HWND*>(out)=window;
    return FALSE;
}
static DWORD WINAPI menuThread(void*) {
    constexpr wchar_t windowClass[]=L"SecondSight.GameplayTweaks.Panel";
    static const wchar_t* keys[]={L"Health",L"Power",L"Invisibility",L"Close"};
    static const wchar_t* labels[]={L"Infinite health",L"Infinite psychic energy",L"Invisibility",L"Close (F1)"};
    Panel p;
    while(!p.game) { EnumWindows(findGame,reinterpret_cast<LPARAM>(&p.game)); if(!p.game) Sleep(160); }
    RECT rect{};
    if(GetClientRect(p.game,&rect)) p.scale=std::clamp(static_cast<float>(rect.bottom)/1080.0f,1.0f,3.0f);
    p.ini=directory+L"SecondSight.GameplayTweaks.ini";
    WNDCLASSW cls{};
    cls.lpfnWndProc=Panel::proc; cls.hInstance=module; cls.lpszClassName=windowClass;
    cls.hCursor=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512)); cls.hbrBackground=GetSysColorBrush(COLOR_BTNFACE);
    if(!RegisterClassW(&cls)) { log("TWEAKS PANEL class creation failed");return 1; }
    const DWORD style=WS_POPUP|WS_CAPTION|WS_SYSMENU;
    RECT bounds{0,0,p.px(300),p.px(177)}; AdjustWindowRectEx(&bounds,style,FALSE,WS_EX_TOOLWINDOW);
    wchar_t title[96]{};
    const HWND window=CreateWindowExW(WS_EX_TOOLWINDOW,windowClass,p.label(L"Title",L"Second Sight gameplay tweaks",title),
                                      style,0,0,bounds.right-bounds.left,bounds.bottom-bounds.top,p.game,nullptr,module,&p);
    if(!window) { log("TWEAKS PANEL creation failed");UnregisterClassW(windowClass,module);return 1; }
    p.font=CreateFontW(-p.px(17),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,0,0,CLEARTYPE_QUALITY,0,L"Microsoft YaHei UI");
    bool complete=true;
    for(unsigned i=0;i<4;++i) {
        wchar_t label[96]{};
        const bool button=i==3;
        const HWND control=CreateWindowExW(0,L"BUTTON",p.label(keys[i],labels[i],label),
            WS_CHILD|WS_VISIBLE|WS_TABSTOP|(button?BS_PUSHBUTTON:BS_AUTOCHECKBOX),
            p.px(18),p.px(14+static_cast<int>(i)*38),p.px(button?123:264),p.px(30),
            window,reinterpret_cast<HMENU>(static_cast<UINT_PTR>(button?200:100+i)),module,nullptr);
        if(!control) { complete=false;break; }
        SendMessageW(control,WM_SETFONT,reinterpret_cast<WPARAM>(p.font?p.font:GetStockObject(DEFAULT_GUI_FONT)),FALSE);
    }
    p.f1=(GetAsyncKeyState(VK_F1)&0x8000)!=0;
    if(complete && SetTimer(window,1,16,nullptr)) {
        log("TWEAKS PANEL ready (F1)");
        MSG message{};
        while(GetMessageW(&message,nullptr,0,0)>0) {
            if(!p.shown || !IsDialogMessageW(window,&message)) {
                TranslateMessage(&message); DispatchMessageW(&message);
            }
        }
    } else log("TWEAKS PANEL controls or timer failed");
    TweakOptions.store(0,std::memory_order_relaxed);
    if(IsWindow(window)) DestroyWindow(window);
    if(p.font) DeleteObject(p.font);
    UnregisterClassW(windowClass,module);
    return 0;
}

extern "C" void __cdecl InitializeASI() {
    if(InterlockedCompareExchange(&initialized,1,0)) return;
    wchar_t own[MAX_PATH]{}, host[MAX_PATH]{};
    const auto pathLength=GetModuleFileNameW(module,own,MAX_PATH);
    if(!pathLength || pathLength>=MAX_PATH) { status=2;return; }
    directory=own; directory.resize(directory.find_last_of(L"\\/")+1);
    const auto hostLength=GetModuleFileNameW(nullptr,host,MAX_PATH);
    if(!hostLength || hostLength>=MAX_PATH || reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr))!=0x400000 ||
       !shaMatches(host,"4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda")) {
        status=2;log("TWEAKS IDENTITY REJECTED; no game-memory access");return;
    }
    if(!shaMatches((directory+L"SecondSight.FusionFix.asi").c_str(),
                  "939d0bbc6dacca73b4323fa018ba11d04a87dde5073e795b5914db85d6158430")) {
        status=3;log("TWEAKS DEPENDENCY OR PATCH REJECTED; flags off");return;
    }
    HMODULE pinned=nullptr;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
                           reinterpret_cast<LPCWSTR>(&InitializeASI),&pinned)) {
        status=3;log("TWEAKS MODULE PIN ERROR; flags off");return;
    }
    if(!install()) { status=3;log("TWEAKS PATCH REJECTED; flags off");return; }
    HANDLE ui=CreateThread(nullptr,0,menuThread,nullptr,0,nullptr);
    if(!ui) { status=3;log("TWEAKS PANEL thread failed; flags off");return; }
    CloseHandle(ui);
    status=1;log("TWEAKS SITE GUARDS PASS; F1 panel initializing; flags off");
}
extern "C" int __cdecl GameplayTweaksStatus() { return status; }
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) module=instance;
    return TRUE;
}
