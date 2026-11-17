#pragma once
// GOG x86 subtitle scope. Only audited caption paths opt in; no locale data here.
#include <cstdint>
namespace subtitle_layout {
struct Style { std::uint32_t font, flags; float x, y; std::uint32_t metrics, spacing; std::int32_t adjustment; };
static_assert(sizeof(Style) == 0x1c, "native style layout");
struct Scope { Style style; Style* previous; std::uint32_t fontIndex, descriptor; bool active; };
static Scope cutscene{};
// This is a pixel-space renderer. Match its 480-line reference UI at each height.
inline float screenScale(int height) { return height > 0 && height <= 16384 ? static_cast<float>(height) / 480.0f : 1.0f; }
static int begin(Scope& scope, int font) {
    using SetFont = int (__cdecl*)(int);
    auto& current = *reinterpret_cast<Style**>(0x9e88ac);
    auto& index = *reinterpret_cast<std::uint32_t*>(0x9e88a4);
    auto& descriptor = *reinterpret_cast<std::uint32_t*>(0x9e88a8);
    // A stale/repeated begin must not compound the existing caption scale.
    if (!scope.active) { scope.previous = current; scope.fontIndex = index; scope.descriptor = descriptor; }
    const int previous = reinterpret_cast<SetFont>(0x610590)(font);
    scope.style = *current;
    const float scale = screenScale(*reinterpret_cast<const int*>(0x872504));
    scope.style.x *= scale; scope.style.y *= scale;
    current = &scope.style; scope.active = true;
    return previous;
}
static void end(Scope& scope) {
    if (!scope.active) return;
    auto& current = *reinterpret_cast<Style**>(0x9e88ac);
    // Do not override a later explicit font selection made by another path.
    if (current == &scope.style) {
        current = scope.previous;
        *reinterpret_cast<std::uint32_t*>(0x9e88a4) = scope.fontIndex;
        *reinterpret_cast<std::uint32_t*>(0x9e88a8) = scope.descriptor;
    }
    scope.active = false;
}
static int __cdecl beginCutscene(int font) { return begin(cutscene,font); }
static void __cdecl finishCutscene() { end(cutscene); }
// Replays overwritten FLD at 0x5431e8, then rejoins the original function.
static __declspec(naked) void endCutsceneHook() {
    __asm {
        pushfd
        pushad
        call finishCutscene
        popad
        popfd
        fld dword ptr ds:[09674b4h]
        push 05431eeh
        ret
    }
}
}
