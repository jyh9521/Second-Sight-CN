// Locale-neutral token handling. No game addresses or code execution here.
#pragma once
#include <cstddef>
#include <cstring>
#include <string>
#include <stdexcept>

namespace transport {
constexpr unsigned char marker = 0x1f;
inline size_t glyph(const char* p) {
    if (!p || static_cast<unsigned char>(*p) != marker) return 0;
    unsigned int n = 0;
    for (size_t i = 1; i <= 4; ++i) {
        if (p[i] < '0' || p[i] > '9') return 0;
        n = n * 10 + p[i] - '0';
    }
    return n < 1536 && !(p[5] >= '0' && p[5] <= '9') ? 5 : 0;
}
inline bool opcode(char c) { return (c >= '1' && c <= '9') || (c >= 'A' && c <= 'K'); }
inline size_t budget(const std::string& text) {
    size_t total=0;
    for(size_t i=0;i<text.size();) {
        if(text[i]==11 && i+1<text.size()) {
            const char c=text[i+1];
            total+=std::strchr("1234GHI",c)?59:std::strchr("AB",c)?119:std::strchr("DE",c)?27:0;
            i+=2;
        }
        else if(text[i]=='%' && i+1<text.size() && text[i+1]>='1' && text[i+1]<='9') { total+=127; i+=2; }
        else { ++total; ++i; }
    }
    return total;
}
inline const char* skip(const char* p) {
    if (!p) return p;
    while (*p && static_cast<signed char>(*p) <= 32 && *p != 11 && !glyph(p)) ++p;
    return p;
}
// Native word destination is 200 bytes. Include legacy terminal whitespace,
// but split a custom glyph atomically so CJK can wrap without literal spaces.
inline const char* word(char* out, const char* p) {
    size_t used = 0;
    if (!p) { out[0] = 0; return p; }
    if (glyph(p)) { std::memcpy(out, p, 5); out[5] = 0; return p + 5; }
    while (*p && used < 190) {
        if (glyph(p)) break;
        if (*p == 11 && p[1]) {
            if (used + 2 > 190) break;
            out[used++] = *p++; out[used++] = *p++; continue;
        }
        const auto ch = static_cast<signed char>(*p);
        out[used++] = *p++;
        if (ch <= 32) break;
    }
    out[used] = 0;
    return p;
}
// Expand one native button token at a time through the supplied callback. The
// callback output is copied immediately, before the native scratch is reused.
template<typename Expand>
std::string expand(const char* text, Expand control) {
    std::string out;
    for (const char* p = text; p && *p;) {
        if (*p == 11 && p[1]) {
            const char unit[] = {11, p[1], 0};
            const char* value = control(unit);
            if (value) out += value;
            p += 2;
        } else {
            out += *p++;
        }
        if (out.size() > 4095) throw std::runtime_error("expanded text exceeds owned buffer");
    }
    return out;
}
}
