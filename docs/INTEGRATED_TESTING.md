# 三合一测试包

本包包含 **ReMade 高清材质、FusionFix 和中文最小样本**。文件整合与离线检查不等于三者运行时共存通过；游戏由用户手动启动。本轮不修改原安装，不修改 EXE 的 LAA 标志。

## 文件与用途

| 路径 | 内容 |
|---|---|
| `game/dinput8.dll` | 用户提供的 ReMade 纹理替换模块，保持原名和原字节 |
| `game/Remaster_Textures/` | 全部 5,110 张 DDS，保持原尺寸和内容 |
| `game/dsound.dll` | FusionFix 自带的 Ultimate ASI Loader 10.0.2，仅改文件名 |
| `game/dsound.ini` | 开启 ASI 加载和诊断日志，保留默认延迟初始化 |
| `game/scripts/SecondSight.FusionFix.asi`、`.cfg` | 固定 FusionFix `13.11.2026.1802-7bce79f`，使用输入目录的原始配置 |
| `game/scripts/SecondSight.Localization.asi` | 独立汉化模块 |
| `game/scripts/localization/` | 语言包、字形清单及许可通知 |

002 使用输入目录的全屏/跟随显示器刷新率默认配置；001 已有的无边框/60 FPS 配置保持不动。

这是独立的本地游戏副本，不依赖原目录的硬链接或目录联接，也不把三个模组同名覆盖。原安装中的 GOG 输入包装器未复制进测试包。ReMade 本地 DLL 没有版本资源，以包内 hash 清单识别，不根据网站版本号推定其版本。

## 你来测试

1. 打开本测试包的 `game/` 目录（包编号见 `package.json`），由你手动双击 `secondsight.EXE`。不要使用指向原安装或旧测试包的快捷方式。若从终端启动，先切换到这个 `game/` 目录；ReMade 按工作目录查找材质。
2. 先看菜单、“新游戏”“选项”“字幕”等样本及 FusionFix 功能，再检查场景纹理是否生效。记录分辨率、窗口模式和设置。
3. 检查剧情中的候选句，例如“我在哪里？”；进入 Isolation 的 PDA 任务页，观察“任务目标 / 隔离 / 逃离。 / 离开隔离室。”。候选字幕尚未全部定位，不把遇到英文当作整包故障。
4. 记录进出 PDA、读取存档、关卡切换、切换窗口后的字形、贴图和稳定性。高清包含 108 张 8K 材质，留意加载时间、内存增长和崩溃；本轮没有降采样或应用 4GB 补丁。
5. 退出后保留截图和日志：`game/dsound.log`、`game/scripts/SecondSight.Localization.log`，以及实际生成的 ReMade/FusionFix 日志。日志没有生成时也请报告，不以文件存在代替功能验收。

中文仍是 **21 条菜单、11 条剧情候选、同一 PDA 页 4 条文本**，不是全量汉化。更详细的样本与日志解释见[基础 PoC 测试说明](https://github.com/jyh9521/Second-Sight-CN/blob/main/docs/POC_TESTING.md)；其中 001 的目录和单加载器布局属于历史版本，本包以本页为准。

包内 `game/profiles/` 初始为空，不复制原存档；请自行备份重要存档。文件副本隔离不代表用户目录或注册表状态已实测隔离。

## 出问题时分层排查

先手动关闭游戏。在测试包根目录执行以下命令可暂时关闭高清层，保留 FusionFix 和汉化，脚本不启停游戏：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-HD.ps1 -Mode disable
```

脚本核对 hash 后将 ReMade 的 `game/dinput8.dll` 改为 `.dll.disabled`，不删材质。恢复高清层：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-HD.ps1 -Mode enable
```

也可运行 `Disable-Localization.ps1` 单独关闭汉化；这是另一个排查状态，不等于关闭 FusionFix 或恢复纯原版。切换后原始清单检查会报告文件状态变化，重新启用并恢复原配置后再核对。纯原版对照使用一直未改动的原安装。

## 版本保留

构建器只在新包完整校验通过后，按递增包编号保留 `dist/` 中最近两个已完成的受管测试包。例如 002 完成后保留 **001 和 002**，后续生成 003 后删除 001。删除包括旧包内的测试存档、配置和日志，需要保留的反馈先移到包外。输入材质目录、FusionFix 目录和研究证据不在自动清理范围；未完成或无法识别的目录不自动删除。

反馈请注明包编号、三个功能分别是否生效、场景/操作、分辨率、截图和日志。菜单、真实字幕、PDA 及三者基础共存通过后，再推进全量汉化。
