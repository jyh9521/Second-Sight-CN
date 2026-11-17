// Locale-neutral token handling. No game addresses or code execution here.
#pragma once
#include <cstddef>
#include <cstdint>
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
    return n < 6144 && !(p[5] >= '0' && p[5] <= '9') ? 5 : 0;
}
inline bool opcode(char c) { return (c >= '1' && c <= '9') || (c >= 'A' && c <= 'K'); }
inline size_t templateBudget(unsigned int id,char slot) {
    const unsigned int n=static_cast<unsigned char>(slot)-'1';
    switch(id) {
        case 2441: { const size_t limits[]={59,59,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2442: { const size_t limits[]={59,59,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2443: { const size_t limits[]={59,59,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2444: { const size_t limits[]={59,59,27,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2445: { const size_t limits[]={59,59,27,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2446: { const size_t limits[]={59,59,27,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2447: { const size_t limits[]={59,59,27,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2448: { const size_t limits[]={59,59,27,10}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2449: { const size_t limits[]={10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2896: { const size_t limits[]={10,59,27}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2897: { const size_t limits[]={59,27}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2907: { const size_t limits[]={10,59,27}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2908: { const size_t limits[]={59,27}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2909: { const size_t limits[]={10,59,27,10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2910: { const size_t limits[]={10,59,27}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 2911: { const size_t limits[]={27,10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 3336: { const size_t limits[]={10,59,10,59,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 3337: { const size_t limits[]={10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 3820: { const size_t limits[]={10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 3821: { const size_t limits[]={10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 4261: { const size_t limits[]={10,59,10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        case 4478: { const size_t limits[]={10,59}; return n<sizeof(limits)/sizeof(limits[0])?limits[n]:127; }
        default: return 127;
    }
}
inline size_t budget(const std::string& text,unsigned int identifier=0) {
    size_t total=0;
    for(size_t i=0;i<text.size();) {
        if(text[i]==11 && i+1<text.size()) {
            const char c=text[i+1];
            total+=std::strchr("1234GHI",c)?59:std::strchr("AB",c)?119:std::strchr("DE",c)?27:0;
            i+=2;
        }
        else if(text[i]=='%' && i+1<text.size() && ((text[i+1]>='1' && text[i+1]<='9') || text[i+1]=='s')) { total+=templateBudget(identifier,text[i+1]); i+=2; }
        else { ++total; ++i; }
    }
    return total;
}
// Unproven long consumers keep original BS pointers. Only the owned wrapper at
// audited long-output call sites may late-substitute their complete target.
inline bool deferred(unsigned int id) {
    return (id>=3644 && id<=3648) || (id>=3846 && id<=3852) || id==2912 || id==313 || id==314 || id==3029 || id==4637 || id==4638 || id==5494;
}
inline bool longWrapCaller(uintptr_t returnAddress) {
    switch(returnAddress) {
        case 0x541d41: case 0x541e14: case 0x565745: case 0x565870:
        case 0x565cf7: case 0x5e283b: case 0x5e2b17:
            return true;
        default: return false;
    }
}
inline size_t bsLimit(unsigned int id) {
    if(deferred(id)) return 4095;
    switch(id) { case 3027: case 3608: case 3609: case 3650: case 3923: case 3924: case 3928: case 3929: case 3930: case 3931: case 3933: case 3958: case 4004: case 4415: case 4498: case 4501: case 4561: case 4639: case 5184: case 5330: case 5331: case 5408: case 5497: case 5500: case 5503: case 5506: case 5682: case 5683: case 5684: case 5685: case 5898: case 5899: case 5900: case 5901: return 4095; case 5922: case 5924: case 5926: return 1023; default: return 255; }
}
inline size_t bsExpandedLimit(unsigned int id) { return id==3336?510:bsLimit(id); }
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

namespace transport {
// HUD copies the returned body into 512-byte global and stack destinations.
// Retain the entire input, not a prefix, if wrapping alone exhausts LF room.
inline std::string hudBody(const std::string& input,const std::string& wrapped) {
    if(input.size()>510) throw std::runtime_error("HUD input exceeds original gate");
    return wrapped.size()<=511?wrapped:input;
}
// The original UI modifies the returned wrap buffer in place to select visible
// lines. Caller owns this result; no pointer to translation storage is returned.
// Keep ASCII words together; encoded glyphs are individual break opportunities.
template<typename Measure>
std::string wrap(const std::string& input, float width, Measure measure) {
    if (input.size()>4095) throw std::runtime_error("wrap input exceeds owned budget");
    if (!(width>0)) return input;
    std::string out;
    float used=0; size_t lineBytes=0;
    for (size_t i=0;i<input.size();) {
        const char c=input[i];
        if (c=='\n' || c=='`') { out+=c; ++i; used=0; lineBytes=0; continue; }
        size_t end=i;
        if (glyph(input.c_str()+i)) end=i+5;
        else if (c==' ') end=i+1;
        else {
            do { ++end; }
            while(end<input.size() && input[end]!=' ' && input[end]!='\n' && input[end]!='`' && !glyph(input.c_str()+end));
        }
        std::string word=input.substr(i,end-i);
        float amount=measure(word.c_str());
        // Split an oversized ASCII word at character boundaries, never a glyph.
        if (!glyph(word.c_str()) && word.size()>1 && (amount>width || word.size()>250)) {
            end=i+1;
            word=input.substr(i,1); amount=measure(word.c_str());
        }
        // Paper documents copy each line into a 256-byte native stack buffer.
        // The physical width alone does not bound encoded bytes (five per glyph).
        if (lineBytes && ((used>0 && used+amount>width) || lineBytes+word.size()>250)) {
            while(!out.empty() && out.back()==' ') out.pop_back();
            out+='\n'; used=0; lineBytes=0;
            if (word==" ") { i=end; continue; }
        }
        out+=word; used+=amount; lineBytes+=word.size(); i=end;
        if(out.size()>8190) throw std::runtime_error("wrap output exceeds owned budget");
    }
    return out;
}
}
