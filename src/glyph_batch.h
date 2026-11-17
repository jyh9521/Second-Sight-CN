#pragma once
#include <cstdint>

// Normal text-batch lifecycle only. Count, shadow and recording passes do not
// activate this state; native glyph callbacks retain count/capacity ownership.
namespace glyph_batch {
struct State {
    bool active = false;
    void begun(bool normal) { active = normal; }
    template<class End> void finish(End end) { active = false; end(); }
    template<class End, class Bind>
    void bind(int texture, uint8_t& pendingBegin, End end, Bind bindTexture) {
        if(active) {
            active = false;
            end(); // Submit the old texture before changing its binding.
            pendingBegin = 1; // Next visible glyph opens the remaining batch.
        }
        bindTexture(texture);
    }
};
}
