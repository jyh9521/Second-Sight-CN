# PoC 004：无边框启动与第二处退出记录

## 用户反馈与已验证事实

003 的高清工具窗口开始滚动，游戏窗口出现后反复切回桌面，用户切回游戏也再次失去焦点，随后退出；未进入主菜单。用户要求无边框启动，仍由用户自行运行游戏。

与 001/002 不同，003 的既有日志已记录：

- Compatibility：`COMPAT APPLIED`。
- UAL：FusionFix、本地化 ASI 都加载，随后 `plugins loaded`。
- 本地化：六次 `ATLAS read served`、`FONT mode=1; descriptor refreshed`、`BS substituted=32 expected=32`。

这证明本次进程越过了前一处加载故障，并走到字体资源读取与文本替换；**不证明用户已经看到中文，也不证明高清纹理替换成功**。

既有 Windows Error Reporting 与用户启动产生的转储记录了另一处异常：`secondsight.EXE + 0x135FC`，`0xC0000005` 读取地址 0。现场 `EAX=0`，指令为 `8B 08`（`mov ecx,[eax]`）。记录的调用参数为纹理槽 0，纹理表该槽的对象指针也是 0。原始 `0x4135A0` 纹理表/表面复制路径随后本应调用对象虚表 `+0x48`，但尚未到达该调用就已异常。

本地只读证据在 `build/startup-004/`：`recorded-crash.json`、`fault-proof.json`、`fault-disassembly.txt`、003 配置/日志快照和 Application Error 记录。原转储不修改、不提交。REA 仅用于绑定 EXE 身份；指令与内存事实来自 pefile/Capstone 和项目的 minidump 读取器，不声称深层反编译或完整进程重放。

## 本轮只改变一个运行参数

003 的配置实际为 `[MAIN] WindowMode = 0`。这是打包器复制上游默认配置的结果，没有延续用户需要的无边框设置。

004 及后续测试包默认使用 `WindowMode = 2`。固定 FusionFix 的 [Window.ixx](https://github.com/ThirteenAG/WidescreenFixesPack/blob/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix/Window.ixx)在该模式下请求窗口化 D3D 设备、清除全屏刷新率，并设置覆盖显示器的无边框窗口。

输出配置仅改变 offset **330** 的一个字节：`0` → `2`。FPS、分辨率、失焦暂停、片头跳过及其他配置保持上游原值；注释和换行也不重写。没有新增游戏指令修改，没有跳过空指针检查处，没有禁用高清或汉化。

| 配置 | SHA-256 |
|---|---|
| 用户提供的原配置（保留） | `a05007595a84708d4973785e5ef690f6d95901484af3542c00045d2f5f49c826` |
| 004 无边框输出配置 | `61bf3e1c037a57661d7df2273a58cd6ac62529bbdfd9bf5fff642e890ce5f48b` |

`tools/fusionfix_config.py` 提供字节保留转换，打包器固定验证输入/输出 hash，并在 `package.json` 的 `fusionfix_config` 记录策略、字段和两个 hash。004 起的清单缺少该记录即拒绝验证，001–003 的历史清单仍可按旧规则检查。

## 因果边界与后续验证

当前的优先假设是独占全屏与失焦切换触发后续渲染问题；另两条待排查路线为高清纹理/D3D9 共享路径和本地化字体生命周期。**空纹理槽为何产生、哪个窗口引发失焦尚未确证；无边框设置不等于这次退出已经修复。** 不仅凭故障地址所在模块归责原游戏、高清或汉化。

本轮 93 项合成测试与配置副本回滚通过。配置测试能发现错误窗口模式，但不能自动复现实际焦点切换或证明主菜单显示。自动化没有启动、附加或操作游戏，也没有执行第三方 DLL。

下一次用户只需手动启动 004，确认：

1. 游戏是否以无边框覆盖屏幕。
2. 是否还自动切回桌面，以及能否停留在主菜单。

若再次退出，保留日志并报告现象即可，不必反复切回，也暂不开展全部字幕/PDA 测试。003 作为上一版对照保留；002 在 004 完整文件验证通过后按最近两版规则删除。

## 可复现的配置验证

```powershell
python -X utf8 tools/verify_window_mode.py prepare --source FusionFix/scripts/SecondSight.FusionFix.cfg --out build/window-004
python -X utf8 tools/verify_window_mode.py evidence --out build/window-004
```

`prepare` 要求新目录。基线探针报告 `WindowMode=0`，退出 2；修改配置报告 `WindowMode=2`，退出 0。Git Bash 执行 `ROLLBACK.sh`，只恢复另一份 `ROLLBACK_TEST.cfg`，退出 0。四份证据为 `MODIFIED_FILE.cfg`、`DIFF_FILE.json`、`VERIFICATION.txt`、`ROLLBACK.sh`；源配置保持原 hash，交付配置保持无边框。回滚结果只描述文件状态，不表示游戏运行状态恢复。
