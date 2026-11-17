#pragma once
// Locale-neutral speech-event state. No game pointers are dereferenced here.
#include <array>
#include <cstdint>
#include <limits>
namespace gameplay_captions {
struct Voice {
    std::uintptr_t owner{};
    std::uint32_t bs{};
    int handle{-1}, priority{};
    const char* text{};
    std::uint64_t sequence{};
};
// -1 is the native duration-driven cue sentinel, not a pending audio handle.
inline bool timedCue(int handle, std::uint32_t flags, float remaining) {
    return handle == -1 && (flags & 8) != 0 && remaining > 0.0f &&
        remaining <= (std::numeric_limits<float>::max)();
}
struct State {
    std::array<Voice, 16> voices{};
    std::uint64_t serial{};
    std::uintptr_t selected{};
    void clear() { voices = {}; serial = 0; selected = 0; }
    void finish(std::uintptr_t owner) {
        for (auto& v : voices) if (v.owner == owner) v = {};
        if (selected == owner) selected = 0;
    }
    const Voice* find(std::uintptr_t owner) const {
        for (const auto& v : voices) if (v.owner == owner && owner) return &v;
        return nullptr;
    }
    void active(std::uintptr_t owner, std::uint32_t bs, int handle, int priority, const char* text) {
        if (!owner || !bs || handle < -1 || handle == 0 || !text || !*text) return;
        Voice* slot = nullptr;
        for (auto& v : voices) if (v.owner == owner) { slot = &v; break; }
        if (slot && slot->bs == bs && slot->handle == handle) return;
        if (!slot) for (auto& v : voices) if (!v.owner) { slot = &v; break; }
        // Bound ambient chatter without evicting a more important active voice.
        if (!slot) {
            slot = &voices.front();
            for (auto& v : voices) if (v.priority < slot->priority ||
                (v.priority == slot->priority && v.sequence < slot->sequence)) slot = &v;
            if (priority < slot->priority) return;
            if (selected == slot->owner) selected = 0;
        }
        *slot = {owner, bs, handle, priority, text, ++serial};
    }
    const Voice* choose() {
        const Voice* best = find(selected);
        for (const auto& v : voices) if (v.owner && (!best || v.priority > best->priority ||
            (v.priority == best->priority && !selected && v.sequence < best->sequence))) best = &v;
        selected = best ? best->owner : 0;
        return best;
    }
};
inline bool selfTest() {
    State s;
    s.active(1, 100, 7, 1, "first");
    s.active(2, 101, 8, 1, "second");
    if (!s.choose() || s.choose()->bs != 100) return false;
    s.active(1, 100, 7, 1, "first");
    if (s.serial != 2 || s.choose()->bs != 100) return false;
    s.active(3, 102, 9, 2, "priority");
    if (s.choose()->bs != 102) return false;
    s.finish(3); if (s.choose()->bs != 100) return false;
    s.finish(1); if (s.choose()->bs != 101) return false;
    s.active(2, 103, 10, 1, "replacement");
    if (s.choose()->bs != 103) return false;
    s.clear(); if (s.choose()) return false;
    for (std::uintptr_t i = 1; i <= 20; ++i) s.active(i, 100, 7, 1, "bounded");
    if (!s.choose()) return false;
    s.clear(); s.active(1, 0, 7, 1, "invalid"); s.active(2, 100, -2, 1, "invalid");
    return s.choose() == nullptr && timedCue(-1,14,3.6f) &&
        !timedCue(-1,4,3.6f) && !timedCue(-1,14,0.0f) && !timedCue(0,14,3.6f);
}
}
