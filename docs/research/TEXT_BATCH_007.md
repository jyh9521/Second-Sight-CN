# 007 原生文字批次与跨页错字

Inspected existing original EXE and user-provided dump with Capstone; no game launch, attachment, or process operation.

## Root cause

The regular glyph callback at 0x610E60 opens one native batch per text pass but the glyph loop binds different font pages without ending that batch. End submits all accumulated vertices under the final texture, matching the observed +/-1024 glyph aliases. Texture bind 0x40FC20 -> 0x40DC60 -> 0x40DB70 has no flush and writes stage-zero texture to 0x8DA4D0.

## Minimal bounded patch points

| Site | Original bytes | Purpose |
|---|---|---|
| 0x610EFD | E8 CE CF DF FF | CALL 0x40DED0; regular text Begin |
| 0x610FA8 | E9 53 D1 DF FF | JMP 0x40E100; regular text final End |
| 0x6125C1 | E8 5A D6 DF FF | CALL 0x40FC20; custom glyph page change |
| 0x612677 | E8 A4 D5 DF FF | CALL 0x40FC20; return to Latin texture |

The normal End is a tail jump, not a call. Replace with a tail jump to a no-argument cdecl shim; that shim clears active state and calls original End, returning to the glyph-loop caller. Do not insert a new CALL there without handling the changed return address.

Begin ABI: int __cdecl Begin(int vertexFormat, int mode, int requestedQuadVertices, int texture). Arguments here are (0x92, 2, remainingGlyphs * 4, -10). Return is 1. End ABI: void __cdecl End(void). Bind ABI: void __cdecl Bind(int texture).

Recommended state:
1. BeginNormal forwards all four arguments, records active only for native regular-text batches and recording flag 0x8DAF6C == 0, and preserves original return value.
2. BindTextTexture, if active and a different texture is being bound, clears active, calls original End before original Bind, and sets byte 0x9E88BC = 1.
3. It must leave remainingGlyphs 0x9E88B8 unchanged. The next regular glyph automatically invokes original Begin with remainingGlyphs * 4. This avoids empty eager restarts for whitespace/control-only changes.
4. EndNormal clears active then invokes original End. All normal text actual endings converge at 0x610FA8.
5. A defensive flush guard can additionally require vertex cursor 0x8DAF00 != 0 and actual vertex count 0x8DAF14 > 0; End itself leaves actual count stale, so count alone is insufficient.

Latin binding at 0x612677 precedes the space test at 0x612683. Handling page-switch only will leave mixed ASCII/space cases broken.

## Native count, capacity, and submission facts

- 0x612B92 resets remaining glyph count to zero before the first pass at 0x612B9C. Second pass calls the same glyph walker at 0x612BAF.
- First-pass count callback 0x610D10 increments 0x9E88B8 at 0x610E3B onward and sets byte 0x9E88BC = 1 at 0x610E41.
- Regular callback tests that byte at 0x610ED6, clears it at 0x610EF6, then calls Begin at 0x610EFD.
- Each quad appended by 0x60FEC0 emits six actual vertices. Actual count increments at 0x60FF12, 0x60FFB9, 0x610061, 0x6100F4, 0x610172, 0x610200.
- 0x610F9E updates remaining after the actual quad. Only zero takes tail End at 0x610FA8; nonzero returns to append later glyphs.
- Begin wrapper 0x40DED0 invokes 0x40DCF0 with primitive 5. Native Begin converts requestedQuadVertices / 4 * 6 to allocated capacity and resets actual count at 0x40DD64.
- End loads actual count at 0x40E111; primitive 5 takes branch 0x40E164 and submits actualCount / 3 as D3D triangle-list primitive count, not the entire reserved capacity. Early flush therefore does not draw uninitialized reserved vertices.
- Normal End sets cursor 0x8DAF00 = 0 at 0x40E337 but does not zero actual count. Next Begin zeroes count.

## Unmodified paths and edge conditions

- Shadow callback 0x610D10 uses immediate Begin at 0x610DF5 and tail End at 0x610E36. It does not need batching changes.
- Styled callback 0x610FC0 uses immediate helpers 0x411270 and 0x4118E0. Their End sites include 0x411544 and 0x411C17; no normal batch active state should be set for these paths.
- Text wrappers 0x612BC0 and 0x613330 are already FusionFix hook sites in the dump. Do not overwrite them. Neither owns the normal final batch End.
- Recording mode 0x8DAF6C != 0 skips vertex-buffer allocation in Begin and makes End overwrite metadata at 0x8DAF94 instead of a normal submit. Do not apply this normal-batch splitting strategy there without a separate record-list implementation.
- Original EXE only directly enters recording mode through 0x40F020 from 0x506FBA / 0x507214. Those routines have no text calls and end with 0x5070DC / 0x507303, then 0x40F080. Dump recording flag is 0.
- Do not reset, increment, or decrement the native remaining count inside texture hook. Do not set pending before flushing without making active false. Preserve cdecl stack cleanup and nonvolatile registers.

## Fixture identities

Original EXE SHA256: 4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda
Dump SHA256: d8d542b1331ce2469530a45040a38daa7186417661bc2691d6ddb4571ef04e3c

This audit establishes native control-flow evidence, not in-game visual acceptance.

## Reproducible regression

`tools/replay_glyph_batches.py` maps the SHA-256-pinned user-supplied EXE in Unicorn. It executes the actual count/shadow/normal callback instructions, both bind call sites and the newly built ASI hooks loaded from their link MAP. Only graphics primitive allocation/emission/submission and terminal texture storage are mocked. It does not load the game in Windows, create a window, or attach to a process. It proves callback/texture submission ordering, not D3D presentation or real device acceptance.

Baseline recreates these screenshot labels exactly: 选择档案→选预档案; 新游戏→新人戏; 退出→往出; 选择关卡→徒择关卡; 观看过场动画→观看过自礼画; 选择难度→徒择抑度. Modified replay samples every glyph from its expected page. Atlas DDS and glyph IDs are unchanged; this is not a translation wording or Source Han font change.
