# PoC 003：启动退出定位与兼容适配

## 用户现象与已观测证据

用户报告 001 双击后无反应，002 显示 ReMade 的 `D3D9 Shader & Texture Tools` 窗口后退出。该窗口不是报错框，也不证明高清纹理已成功替换。

2026-11-17 的 Windows Application Error/WER 与两份既有转储均指向同一故障：`SecondSight.FusionFix.asi + 0x519E5`，异常 `0xC0000005`，读取地址 0。记录的指令为 `FF 30`（`push dword ptr [eax]`），EAX=0；对应 pattern 对象的匹配向量 begin/end/capacity 均为 0。两份转储的模块清单均没有 `SecondSight.Localization.asi`，002 的 UAL 日志止于 FusionFix 加载后。

这是用户实际启动产生的证据。本轮分析没有启动、附加或操作游戏；只读取既有日志/转储，静态扫描文件，并运行自有离线宿主。转储未包含完整游戏代码及所有堆页；缺失内存保持未知，未冒称完整进程重放。REA 确认了输入 PE 身份，但 Ghidra 的 JDK 前置条件未满足；指令、上下文及签名证据来自本项目 minidump 读取器、pefile 和 Capstone。

## 根因与范围

当前固定 FusionFix 的 [Resolution::Init](https://github.com/ThirteenAG/WidescreenFixesPack/blob/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix/Resolution.ixx#L56-L67)查找原指令签名，随后直接调用 `filter.get_first()`，没有处理空结果。当前固定 GOG EXE 已在该位置放置刷新率跳板，因此签名缺失，与转储的空向量访问一致。

进一步扫描发现另三处 GOG 宽高比跳板也与 FusionFix 的指令假设不同。仅补一个空指针检查或改搜索文本会留下后续问题；后一种做法还可能把跳转位移误当浮点指针写入。

| 虚拟地址 | GOG 当前指令字节 | 提供给 FusionFix 的指令契约 |
|---|---|---|
| `0x4171B9` | `E9 14 B7 FE FF` | `83 F8 55 7F 15`，条件跳转指向 `0x4171D3` |
| `0x44975B` | `E9 E4 93 FB FF 90` | `D8 0D 70 CC 7C 00`，随后由 FusionFix 重定向乘数 |
| `0x58392F` | `E9 84 F2 E7 FF` | `68 AB AA AA 3F`，4/3 浮点立即数 |
| `0x4F01CB` | `E9 15 2A F1 FF 90` | `D8 0D <适配器自有 float 地址>` |

共覆盖四处、22 字节。这些是经静态分析验证的**兼容指令契约**，不是声称恢复了全部零售原版字节。Overlay 使用适配器内持久、可写、初值 4/3 的存储，避免把 FusionFix 的动态宽高比写入共享常量或 GOG 临时变量。[GameRef](https://github.com/ThirteenAG/WidescreenFixesPack/blob/7bce79ffaeee61f95db59a68b35a150cd8644223/includes/gameref.hpp)与 [ComVars](https://github.com/ThirteenAG/WidescreenFixesPack/blob/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix/ComVars.ixx)的实现允许该指针契约。

原 GOG 跳板本身及共享变量保持原字节；此四处范围与当前本地化模块的写入范围无交集。

## 实现

- 独立、语言无关的 `SecondSight.Compatibility.asi`，源文件 `src/startup_compat.cpp` / `.hpp`。
- UAL 配置显式设置 `LoadExtraPlugins=scripts\SecondSight.Compatibility.asi`，在 FusionFix 前初始化，不依赖目录枚举顺序。UAL v10.0.2 [plugins.cpp 的 141–153 行](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/source/loader/plugins/plugins.cpp#L138-L153)先同步调用额外插件的 `InitializeASI`，随后才扫描普通 ASI；普通扫描也会去重。
- 验证原 EXE SHA-256、固定 FusionFix SHA-256、加载先后与四处全部预期字节，再进行进程内适配；不修改磁盘 EXE、FusionFix、原安装或第三方输入目录。
- `DllMain` 不安装修改；`InitializeASI` 有重复调用保护。版本/字节不符只记录拒绝，不对未知输入盲写。
- 此模块承担 GOG/FusionFix 兼容，不包含中文规则。原独立汉化 ASI 和语言包保持原字节。
- 模块随进程退出结束，适配不是持久安装。不要单独关闭兼容模块而继续使用这个固定 FusionFix 组合。

## 离线回归

`assets/fusionfix-startup-contracts.json` 保存固定上游 SecondSight 源码中的 27 条直接字节模式及预期唯一位置；不包含原始游戏资源或上游完整实现。它不覆盖共享辅助库的全部内部搜索，也不替代游戏测试。

```powershell
python -X utf8 -m unittest discover -s tests -q
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_runtime.ps1
python -X utf8 tools/startup_compat.py prepare --exe "$Game/secondsight.EXE" --out build/startup-003
python -X utf8 tools/startup_compat.py probe --image build/startup-003/BASELINE.image
python -X utf8 tools/startup_compat.py probe --image build/startup-003/MODIFIED_FILE.image
```

基线为 23/27、缺失 4 项，探针退出 2；修改后 27/27 唯一匹配，退出 0。修改图像由自有 C++ 宿主调用与真实初始化共享的四处适配函数产生，不是只验证另一套 Python 模拟实现。游戏指令仅当作数据读取，未执行；图像只保留 `.text/.rdata` 前缀，省去巨大 BSS，使用分析专用 overlay 哨兵地址，不能当游戏 EXE 安装。

`ROLLBACK.sh` 恢复另一个 `ROLLBACK_TEST.image`，验证逐字节恢复，并保留修改产物。四份证据位于 `build/startup-003/`：`MODIFIED_FILE.image`、`DIFF_FILE.json`、`VERIFICATION.txt`、`ROLLBACK.sh`。已有转储与源分析证据保存在 `build/startup-investigation/`，不提交私人路径清单、转储或完整资产。

## 用户下一次只需验证启动

003 继续包含完整高清材质、FusionFix 和中文样本。请用户手动启动 003，先确认能否进入主菜单，不急着测试全部字幕/PDA。

预期日志：`game/scripts/SecondSight.Compatibility.log` 出现 `COMPAT APPLIED`，UAL 日志随后记录 FusionFix、本地化模块的加载。本地化日志再结合实际菜单截图判断。以上是预期，不是已观测的 003 运行结果。

**状态：已完成针对既有启动故障的离线修正；003 是否成功进入菜单，以及后续画面/音频/输入/场景切换，仍待用户验收。**

## 后续用户结果（003 → 004）

003 的用户日志已确认兼容适配生效，FusionFix 和本地化 ASI 都完成加载；字体资源已读、32 条 BS 已替换。但用户未进入主菜单，反复失焦后在原 EXE 的另一处纹理路径退出。上述原有离线证据保持不变；新故障、无边框要求与当前待验收状态见[004 记录](STARTUP_004.md)。
