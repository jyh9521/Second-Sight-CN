# 原生字形渲染路径与最小接入点

本记录服务于菜单、剧情字幕、PDA 的最小验证包，不代表游戏内验收完成。研究仅读取本地 PE 并运行静态检查，未启动、操作或附加游戏进程；游戏内测试交由用户执行。

## 证据与适用版本

| 项目 | 值 |
| --- | --- |
| 输入 | GOG `secondsight.exe`，x86，5,484,544 字节 |
| SHA-256 | `4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda` |
| ImageBase | `0x00400000` |
| 方法 | pefile 2024.8.26、Capstone 5.0.7、原字节比对 |
| 可复现工具 | `tools/inspect_renderer.py` |
| 状态 | **Verified：静态字节/控制流**；**High-confidence deduction：接入方案**；运行效果未验证 |

下列地址均为 VA。工具使用 PE 节映射换算文件偏移，不把 `VA - ImageBase` 泛化为所有节的文件偏移。之前 REA `open_binary` 确认了输入身份，但 Ghidra provider 的 Java 路径失效，未得到深层反编译证据；本记录不将 Capstone 输出描述为 REA 反编译结果。

## 1. Font descriptor

表从 `0x8BA7E0` 到 `0x8BA920`，10 项，每项 `0x20` 字节。

| 偏移 | 静态用途 | 说明 |
| --- | --- | --- |
| `+00` | 资源路径指针 | 前四项 impact、fontcaps、book、booklight；后六项 jpnfont1..6 |
| `+04` | 加载 flags | 最低字节的 `0x80` 表示禁用；场景选择使用其他位 |
| `+08` | 字形 metrics 指针 | Latin 每项 10 字节；JPN 初始为 0 |
| `+0C` | 间距/字偶表指针 | 精确表结构尚未全部命名；JPN 初始为 0 |
| `+10` | 字形高度 | JPN 为 16；参与 draw、measure、行距 |
| `+14` | 固定 advance | JPN 为 16；参与 measure 和 draw 后移 |
| `+18` | 间距调整参数 | JPN 为 1；完整语义仍待补充 |
| `+1C` | 运行时纹理 handle/index | 初始 `0xFFFFFFFF`；绑定资源记录的 `+14` |

JPN 描述符起点为 `0x8BA860`。六个 flags 地址为 `0x8BA864 + n*0x20`，`n=0..5`。推荐仅将 `9F 00 00 00` 改成 `1F 00 00 00`，不改全局 eligibility 分支。

`0x610460` 在 flag 的符号位为 1 时直接跳过记录；清除该位后，JPN 采用与 book 相同的场景位集合。它不等于“不论场景都加载”。记录中的 path 指针必须指向插件持有的稳定内存，不能指向临时字符串。

## 2. 资源加载与生命周期

静态调用链：

```text
0x544A80 → 0x610510（筛选 descriptor）
          → 0x4A0130（登记 type=3 纹理资源记录）
          → 0x49F500（按来源/偏移排序）
资源队列 → 0x49FA5C → 0x413A60（.raw 改为 .dds）
          → 0x49DDF0（大小）
          → 0x49DD70（PAK 内存缓存指针）
          → 缓存未命中：分配内存 + 0x49E4E0（读取）
          → 0x4133B0（创建纹理）
0x611840（resolve）→ 0x49F850（查记录）→ descriptor.texture = record[+14]
```

`0x49E490` 在 PAK 未命中时返回 0，这只是排队排序键；`0x4A0130` 仍登记记录。因而自有文件可以保留引擎资源登记和纹理生命周期，只在 `0x49DDF0` / `0x49E4E0` 对明确的自有路径提供大小/字节，其他路径调用原 trampoline。两入口的首条指令都是 5 字节 `A1 D0 0F 91 00`。

这条链支持“独立 ASI + 自有 DDS，不重打 PAK”的方案，但上述是静态推导，不是已经观察到的加载成功。读取钩子还须尊重目的缓冲区、请求长度和原返回语义。

**启用顺序很重要：**在第一次 enqueue 前准备好稳定路径、可用 DDS 数据、资源读取钩子，然后才清 flags。`0x611840` 对 `0x49F850` 的返回值直接解引用 `+14`，没有空指针检查。只启用 flags 而不提供资源会产生崩溃风险。应在安装阶段验证所有页文件，缺页则不启用整个本地化功能。

不要自行释放引擎创建的纹理 handle，原 enqueue/resolve 会在场景生命周期中重新绑定。不要假定初次场景加载后 handle 永久有效。

## 3. Mode、style 与 FusionFix 边界

| 地址 | 类型/作用 |
| --- | --- |
| `0x9E88A0` | `int32_t`，JPN/custom glyph mode |
| `0x9E88A4` | `int32_t`，当前 style index |
| `0x9E88A8` | 当前 descriptor 指针 |
| `0x9E88AC` | 当前 style 记录指针；表基址 `0x8BA920`，步长 `0x1C` |
| `0x6103F0` | `int __cdecl SetMode(int)`，返回旧 mode |
| `0x610590` | `int __cdecl SetFont(int)`，返回旧 style |

`SetFont` 在 mode 非零时将当前 descriptor 置为 JPN 第一页，否则按 style 第一字取 Latin descriptor。**设置 mode 后必须重新 SetFont。**

`0x611840` 的尾部先选择 style 24，再调用 `SetMode(0)`。最小接入是只替换 `0x611885` 处原 `E8 66 EB FF FF` call，保留现有参数和调用约定：

```cpp
int __cdecl OnFontModeReset(int /* original argument is zero */) {
    auto setMode = reinterpret_cast<int (__cdecl*)(int)>(0x6103F0);
    auto setFont = reinterpret_cast<int (__cdecl*)(int)>(0x610590);
    const int previous = setMode(1);
    setFont(*reinterpret_cast<const int*>(0x9E88A4));
    return previous;
}
```

该尾部也被 `0x611890` 的 Latin metrics 一次性初始化路径跳入，因此不要重复手工执行 metrics 变换。mode 是全局状态，切换后原英文布局是否完全不变仍需用户测试。

已有 FusionFix 在 `0x612BC0`、`0x613330` 处理文字坐标。**不覆盖这两个入口**，不替换 FusionFix 的代理 DLL。本方案在更低层的 marker 分支和独立资源/BS 事件接入；地址不重叠只证明静态无同点覆盖，不能替代兼容性验收。

## 4. 字形编码：专用 marker，不复用逗号

原 `0x610680` 的输入是 `EAX=marker 指针`、栈上一个可空的 cursor 指针。函数跳过首字节，读取直到首个非数字或 NUL 的**所有**十进制数字，只保留最后四位，并对 cursor 增加数字个数。调用方负责再跳过 marker。无数字得到 0，没有四位数量限制。

所以 `,00015` 是 glyph 15，不是 glyph 1 加 ASCII `5`。开启 mode 后未翻译英文中的逗号也会被解析为 glyph；不能直接启用全局 mode 配合原逗号。

推荐编码：`0x1F + 四位十进制 ID`。所有可见字符，包括译文内的 ASCII 字母、数字和标点，均编码为字形 token；可保留空格、TAB、LF，以及经独立验证的原生控制代码。不要加入 `0x1E` 分隔符，它不是已验证的零宽控制字符。

必须同步替换六个比较，原字节均为 `3C 2C`，新字节为 `3C 1F`：

| VA | 路径 |
| --- | --- |
| `0x610A96` | measure |
| `0x6119F3` | count（见下一节替换建议） |
| `0x611A59` | substring（见下一节替换建议） |
| `0x611D1B` | wrap 当前 token |
| `0x611D58` | wrap 后续标点 token |
| `0x612561` | draw |

`0x1F` 在 measure 的 jump table 中落入普通字节分支 `0x610A80`；draw 在前置分支只特殊处理 `09/0A/0B/60`，所以可以到达 glyph marker 比较。高位字节先过 Latin 重映射，不适合随意作为 marker。

构建时应拒绝：不满四位、非数字 ID、连续第五个数字、ID ≥1536、未知控制码、裸 `0x1F`。不要把未处理的 `0x0B` 参数当成普通译文字符。`tools/inspect_renderer.py --self-test` 包含原 parser 的静态模型及严格编码子集的测试，不是游戏运行测试。

## 5. 计数、substring 与换行

`0x6119D0` 的签名可静态推断为 `int __cdecl(const char*)`；`0x611A30` 为 `const char* __cdecl(const char*, int count)`。mode 非零时二者先调用 `0x610260` 展开按键控制码，然后识别 glyph marker。

**原实现存在静态可见的问题：**parser 更新栈上 cursor，但二者没有将更新值重载到循环使用的 ESI；循环仍只增加 1 字节。原始多字节 token 会按字节计数，substring 可返回 token 中间。

建议整体替换两个入口，而非只换 marker：

1. 调用原 `const char* __cdecl ExpandKeys(const char*)`，地址 `0x610260`，保留按键名称展开行为和返回缓冲区语义。
2. 遇 `0x1F` 加四位合法数字时计作一个字形并前进 5 字节；普通字节前进 1。
3. substring 的 count ≤0 返回展开后起点，遇 NUL 停止；count 返回 token 数而非编码字节数。
4. 严格构建验证负责排除错误 token，运行时仍检查 NUL 和四位数字边界。

两函数入口的完整首两指令是 **6 字节** `51 A1 A0 88 9E 00`。如果建立 trampoline，不能只复制 5 字节，否则截断 `A1`。若整体替换，可写 5 字节跳转加 1 字节 NOP，保留原字节供恢复。

wrap 在 `0x611D1B` 自行复制 marker 和数字，不通过 `0x610680`，因此只修改 parser 不能修复全部路径。后续 glyph ID `0xB2` / `0xB8` 具有“与前一个 token 合并”的静态规则；对应日文字体的实际标点未验证，POC 可保留这两个 ID 的空槽，避免随机汉字获得特殊换行行为。

wrap 的临时工作区约 0x200 字节，循环在 `0x611DF1` 比较 500；但数字复制的内层循环没有逐字节容量检查，构建端必须约束 token 数字长度。`0x610260` 的复制路径亦未发现完整边界检查，不应仅因 BS 能放长文本就放行超长菜单/PDA 字符串。

## 6. Atlas、宽度与混排

draw 的 glyph ID 右移 8 位选择 descriptor 页，低 4 位选择列，低字节右移 4 位选择行。六页共 1536 格，代码未发现页数边界检查。

原生 cell 固定 16×16，UV 以像素×16 传递：列起点 `column*256`，右边界加 248，行起点 `row*256`，下边界加 256。最保守 POC 使用 **256×256 DDS，16×16 格**，不要将图集直接升至 512/1024 并声称自动等比例采样；该行为尚未验证。

JPN 模式的 glyph scale 为 `LatinDescriptor.height / JpnDescriptor.height * 0.87`，常量位于 `0x7DE438`。measure 和 draw 都执行此逻辑；不是独立给 draw 放大字形。修改大小必须对两条路径一致考虑。

mode 分支会从正常 style 的 Latin descriptor 重新取得 metrics 和间距表，因此 JPN descriptor 的 `+08/+0C` 为 0 不必填入伪表；普通未翻译 ASCII 仍走 Latin 路径。全局行高、标点、图标和混排基线的实际外观仍需用户确认。

## 7. BS 指针表接入

`0x43E560` 负责加载 BS；`0x90A338` 是当前 BS 基址，`0x90A33C` 是分配尺寸，`0x875E80` 是语言序号。载入后 `0x43E650..0x43E661` 对 6526 个 u32 加基址，将偏移表变成指针表。

推荐 hook `0x43E663`，原字节 `E8 18 20 10 00`，原目标 `0x540680`：

```cpp
void __cdecl OnStringTableReady() {
    // Validate active language and supported IDs before replacing pointers.
    auto table = *reinterpret_cast<const char***>(0x90A338);
    ApplyValidatedOverrides(table);  // Pointers owned by the ASI for its lifetime.
    reinterpret_cast<void (__cdecl*)()>(0x540680)();
}
```

**先改指针，再调用原目标。**`0x540680` 会读取 BS 指针并缓存按键名称等内容，若顺序颠倒会留下旧缓存。每次 BS 重新加载都重新应用，不能只判断基址是否改变：引擎会复用分配区。不得修改 6526 项之外，也不得将字符串指针指向会重新分配/析构的容器内存。

BS hook 只覆盖 BS；PDA 的 RAW 读取需要单独接入，不能因菜单成功就宣称 PDA 已覆盖。

## 8. 复现与验收边界

```powershell
python -X utf8 tools/inspect_renderer.py --self-test
python -X utf8 tools/inspect_renderer.py "C:\Program Files (x86)\GOG Galaxy\Games\Second Sight\secondsight.exe" --disassemble --output build/assessment-20261117/native/renderer-static.json
```

成功尾行：`RESULT static renderer inspection PASS; original SHA256 unchanged; game not executed`，退出码 0。生成的报告重开解析，输入再次计算 SHA-256。错误版本会在访问固定地址前失败。

此检查不会 patch、安装、启动游戏，也不会写入游戏目录。接入方案的原字节已验证；字体是否出现、菜单裁切、字幕换行、PDA 翻页、场景切换后的资源存活及 FusionFix 实际兼容性，均由后续用户运行测试确认。
