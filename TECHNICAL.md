# 技术说明

## 当前路线

保留原版 FusionFix，以同一 Ultimate ASI Loader 加载独立 `SecondSight.Localization.asi`；语言数据与通用本地化实现分离。当前源代码已实现小规模样本构建和运行时适配，先让用户验证菜单、字幕与 PDA，再决定完整字库和内容生产方案。

独立模块与 `dist/poc-zh-CN-001` 本地测试包已完成离线构建和检查，运行时共存尚未验收。若确证共享入口存在不可消除的冲突，再考虑小型上游集成，不预先分叉并维护整套 FusionFix。

以下“已验证”仅指指定文件的静态或离线结果。游戏显示、布局和共存需要用户手动验收；自动化不启动游戏。

## 固定基线

| 文件 | 版本/身份 | SHA-256 |
|---|---|---|
| `secondsight.EXE` | GOG PC、x86、5,484,544 字节、`0,10,0,0` | `4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda` |
| 原安装 `dinput8.dll` | GOG Input wrapper `1.0.0.5195` | `6c059a19692ac72a8b11b4972f67d1afc6765092181a8bacf539345a08abe65e` |
| `SecondSight.FusionFix.asi` | `13.11.2026.1802-7bce79f` | `939d0bbc6dacca73b4323fa018ba11d04a87dde5073e795b5914db85d6158430` |
| FusionFix 提供的 `dinput8.dll` | Ultimate ASI Loader `10.0.2` | `63b465dbc1bf9c5ab4e33c3ccad099d9edb702f2c51587ac8d4f196497396437` |

对应 FusionFix [源码提交 `7bce79ffaeee61f95db59a68b35a150cd8644223`](https://github.com/ThirteenAG/WidescreenFixesPack/tree/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix)。兼容记录使用这个基线，不以更新的 HEAD 代替已核对版本。任何补丁必须先验证输入身份和预期原字节。

## 资源与文本

已检查 258 个 P4CK 封包、24,930 个目录条目、15,083 个不同成员名。主文本 `data/strsspxe.bs` 在两个 arcade 封包内逐字节相同，包含 6,526 个 ID。6,425 个非空 ID 中有 5,484 个不同非空字符串；约 36,738 个英文词元只是初始规模参考，包含调试、未使用和其他平台遗留内容。

PDA 使用独立的 `data/pdaps_[aefgis].raw` 资源，每个后缀在 17 个剧情包重复；a/e 内容相同。PDA 与主文本可能重叠，不能直接叠加工作量。具体结构与已知边界见[文件格式](docs/FILE_FORMATS.md)。

已验证的资源探针只更改英文 ID 850，保留其他 ID 和成员，并在另一副本上恢复原字节。这不证明重建包已经由游戏成功加载。

## 当前 PoC 实现

- `tools/build_locale.py` 读取 `locales/<locale>/poc.json`，校验固定 EXE/BS/PDA 及逐条原文，生成 SLP1 语言包。当前中文样本为 32 条 BS（21 条菜单、11 条剧情候选）和同一 PDA 任务页的 4 条文本。
- BS 在加载后改写选定条目指针；PDA 在解析/重定位后改写所选字段指针。译文内存由模块持有，原 EXE、PAK 不改写；不依赖只拦截底层文件读取而可能漏掉的 PDA 缓存路径。
- 从固定 Noto 字体生成 6 张 256×256 DXT3 DDS，模块按资源名提供大小和读取。图集沿用 16×16 网格，逐字检查字体覆盖和单元边界。
- 原逗号识别点改为 `0x1F`；每个可见译文字符使用四位十进制编号，数字也编码，避免原解析器贪婪读取相邻数字。构建器与运行时同时校验编号范围；字集分配跳过原引擎特殊编号 178、184，六页内共 1,534 个候选字位。BS 编码后上限 255 字节，PDA 上限 450 字节。
- 宽度路径、字符计数和子串边界同时适配；字体描述符加载标志、资源名和模式初始化一起处理。上述代码存在不等于布局已通过。
- 模块先验证宿主 EXE 的基址/hash，再解析语言包；所有目标位置先核对预期原字节，再写入。冲突时拒绝安装，不覆盖未知钩子。
- `DllMain` 不安装钩子；初始化由 `InitializeASI` 触发。离线宿主仅检查数据、边界、自有内存恢复和错误宿主拒绝，不执行游戏地址。

工具命令见[构建说明](BUILDING.md)，SLP1 结构见[文件格式](docs/FILE_FORMATS.md)，静态字形研究见[字形路径证据](docs/research/GLYPH_RENDERER.md)。

## 字形路径

### 已验证的静态事实

- 普通绘制路径主要使用单字节字符查表；Windows 宽字符 API 导入不是正文支持 Unicode 的证据。
- 现有特殊路径读取“逗号 + 十进制字形编号”，同时存在绘制和宽度计算分支。
- 字形编号高位选择页面、低位选择 16×16 网格；EXE 声明 `jpnfont1`～`jpnfont6`。
- 本次全部封包成员中没有找到这些日文字库。常规 impact/book/booklight 字体是 DXT3 DDS；加载器会把 `.raw` 字体名转换为 `.dds`。
- 已观察到日文字体记录在初始化加载条件下跳过，找到的初始化调用将特殊模式设为零。

### 实现假设与验收项

当前实现复用并适配原有字形编号路径，但六页的 **1,536 格上限不是已验证的完整中文容量**；仍须实测字宽、行高、换行、截断和不同调用者。最小样本不含控制码、占位符或长段文本，这些覆盖仍待扩展。

若 PC 分支不完整，再引入独立解码与字形查找。字形生成和编码映射应来自所选语言数据，不能让通用工具依赖手工填入的中文表。

## FusionFix 共存边界

- `TextLanguage` 控制 FusionFix 设置界面，不能把它作为游戏正文汉化开关。
- FusionFix 的开发者覆盖层字体不等于 BS/PDA 中文字库。
- 基线 EXE 的 `0x612BC0`、`0x613330` 被 FusionFix 用于文字/HUD 坐标调整；当前模块不改这两个入口，改用加载/解析调用点与下层字形路径。其他共享状态和时序仍须实测，不把地址避让当作共存通过。
- 观察到 `InitializeASI`、`AsiSettings_GetApi` 导出，但尚未确认稳定的外部游戏本地化 API。
- UAL 整文件重定向不等于 P4CK 内部成员替换。真实加载路径、包优先级和重定向命中仍需分别验证。
- 如模块持有 D3D9 纹理，还需验证设备重置、关卡切换和资源释放。
- 原安装与 FusionFix 的 `dinput8.dll` 不是同一文件；测试包必须备份、记录并可恢复原加载器，不能把两个同名 DLL 当成并排加载。

用户已提供 ReMade 高清模组，已完成[离线兼容评估](docs/REMASTERED_COMPATIBILITY_2026-11-17.md)。它使用 D3DX PNG 内容 hash 替换纹理，附带同名 dinput8 代理并共享 D3D9 钩子；建议保持可选外部依赖，UAL 链载及三方运行时共存待用户验证。PoC 001 未加入该模组；PoC 002 已按下述布局构建。

## 本轮离线结果

- 49 项合成单元测试、MSVC x86 构建和自有离线宿主通过。
- 语言包含 32 条 BS、4 条 PDA、92 个字形和 6 张 DDS；不是全量翻译。
- PoC 001 的 299 个清单文件校验通过；构建前后原安装 305 个文件 hash 不变。
- PDA 四字段的基线、修改和另一副本回滚均退出 0；证据在 `build/poc-verification-20261117/VERIFICATION.txt`。
- 本轮未启动游戏。字体实际显示、三类场景和 FusionFix 共存继续待用户手动验收。

## 证据与继续条件

- [初始评估](docs/ASSESSMENT_2026-11-17.md)保留资源统计、静态地址与 FusionFix 分析背景。
- `tools/assess_resources.py` 与 `tests/test_assess_resources.py` 提供资源解析、隔离修改和合成测试。
- 本地 `build/assessment-20261117/` 保存输入 hash、反汇编摘录和基线/修改/回滚日志，不提交完整资产。
- 初始深层反编译 provider 因 JDK 配置未运行；相关静态证据来自 pefile/Capstone，不冒称 Ghidra 已验证。

进入全量翻译前，必须让用户手动验证菜单、字幕和 PDA 的中文、混排与布局，并确认 FusionFix 开关/配置、读档、关卡切换和恢复原版的行为。没有这一轮反馈，进度保持最小样本阶段。

## PoC 002：dsound 分离加载器

已验证的文件状态：ReMade 的 `dinput8.dll` 保持原字节，FusionFix 自带 UAL 10.0.2 改名复制为 `dsound.dll`；两份 ASI 在 `scripts/` 中，5,110 张 DDS 独立复制。原 EXE 保持 SHA-256 和 PE Characteristics `0x010E`，未修改 LAA。构建器固定核对 HD 全输入 inventory digest `2ee7e2b39b9e56f3c55ab396157775f18bb5adbd411aab983a654d235281da5a`，不依赖本地评估缓存才能重建。

静态依据：原 EXE 导入 DSOUND 的 ordinal 2、11，系统 32 位 DLL 分别对应 `DirectSoundEnumerateA`、`DirectSoundCreate8`。UAL v10.0.2 的 [安装说明](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/readme.md#installation)支持 `dsound.dll`；[proxy.cpp](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/source/loader/proxy/proxy.cpp) 的 `OrdinalEntries` 按系统代理库名称和导出名适配序号，[exports.inl](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/source/loader/proxy/exports.inl)包含所需 DirectSound 转发项。不能只拿 UAL 原始 PE 导出表的 ordinal 2/11 直接判定不兼容。

未选 `d3d9.dll`：游戏相关静态路径使用 `GetSystemDirectoryA` 拼接 `\d3d9.dll`，根目录同名代理并非可靠入口。本轮没有通过加载第三方 DLL 或启动游戏验证这些路线。

`dsound.ini` 采用 `[GlobalSets] LoadPlugins=1 / DontLoadFromDllMain=1 / DebugLog=1`，诊断日志为 `dsound.log`。改名解决的是文件名冲突，不是 D3D9 钩子顺序、中文字库或高清缓存生命周期已经兼容。三合一实机、8K 内存占用和音频输入功能均待用户验收。独立回滚夹具证明高清 DLL 可禁用且两份 ASI 保持字节不变，不宣称原游戏行为已经恢复。
