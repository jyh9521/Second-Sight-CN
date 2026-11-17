# 三合一测试包

005 包含 **ReMade 高清材质、FusionFix、思源黑体和菜单/PDA 中文扩展**。继续使用 004 的 GOG 启动兼容模块和默认无边框配置。文件检查与离线宿主通过不等于游戏内验收；游戏由用户手动启动，自动化不启动游戏。原安装与 EXE 的 LAA 标志保持不变。

## 文件与用途

| 路径 | 内容 |
|---|---|
| `game/dinput8.dll` | 用户提供的 ReMade 纹理替换模块，保持原名和原字节 |
| `game/Remaster_Textures/` | 全部 5,110 张 DDS，保持原尺寸和内容 |
| `game/dsound.dll` | FusionFix 自带的 Ultimate ASI Loader 10.0.2，仅改文件名 |
| `game/dsound.ini` | 开启诊断日志，显式先加载 Compatibility，保留默认延迟初始化 |
| `game/scripts/SecondSight.Compatibility.asi` | 仅在进程内适配四处 GOG/FusionFix 指令契约，磁盘 EXE 不变 |
| `game/scripts/SecondSight.FusionFix.asi`、`.cfg` | 固定 FusionFix `13.11.2026.1802-7bce79f`，输入配置仅覆盖 `MAIN.WindowMode=2`，其余值不变 |
| `game/scripts/SecondSight.Localization.asi` | 独立汉化模块 |
| `game/scripts/localization/` | 语言包、字形清单及许可通知 |

005 输出配置仅将固定输入的 `WindowMode=0` 改为 `2`；不改帧率、失焦暂停或其他设置。输入配置保持原字节。003 配置/日志和原 001 配置均已在本地故障证据目录保留。

这是独立的本地游戏副本，不依赖原目录的硬链接或目录联接，也不把三个模组同名覆盖。原安装中的 GOG 输入包装器未复制进测试包。ReMade 本地 DLL 没有版本资源，以包内 hash 清单识别，不根据网站版本号推定其版本。

## 你来测试

1. 打开本测试包的 `game/` 目录（包编号见 `package.json`），由你手动双击 `secondsight.EXE`。不要使用指向原安装或旧测试包的快捷方式。若从终端启动，先切换到这个 `game/` 目录；ReMade 按工作目录查找材质。
2. 确认无边框、无反复自动切出，检查“选择关卡 / 观看过场动画 / 图形选项 / 档案 / 退出”，再浏览音量、难度、统计、按键设置及档案提示。思源黑体是否清晰、是否裁切也请截图。
3. PDA 先看 Isolation 的“任务目标”和“任务简介”，再看人物、能力、武器资料。重点观察长文自动折行、链接点击、段间接续、翻页和滚动；任务短句“逃离”“离开隔离室”无末尾句号，剧情简介保留正常标点。能力页的动态按键应跟随实际绑定。
4. 记录进出 PDA、读取存档、关卡切换、切换窗口后的字形、贴图和稳定性。高清包含 108 张 8K 材质，留意加载时间、内存增长和崩溃；本轮没有降采样或应用 4GB 补丁。
5. 退出后保留截图和日志：`game/dsound.log`、`game/scripts/SecondSight.Compatibility.log`、`game/scripts/SecondSight.Localization.log`，以及实际生成的 ReMade/FusionFix 日志。日志没有生成时也请报告，不以文件存在代替功能验收。

005 覆盖 **821 条菜单/共享界面文本、PDA 68 页共 447 个非空文本段**，另保留原有 11 条字幕候选。专名 WinterICE、JC 及必要缩写/键帽保留，不视作漏译。没有把全游戏剧情、电脑邮件或纹理文字列为完成。

正常加载日志应显示 `BS substituted=832 expected=832`、`PDA substituted=447 expected=447`。日志可确认替换数量，不代替可见文本和布局验收。
包内 `game/profiles/` 初始为空，不复制原存档；请自行备份重要存档。文件副本隔离不代表用户目录或注册表状态已实测隔离。

004 的新故障证据、无边框策略与待验收边界见[004 记录](https://github.com/jyh9521/Second-Sight-CN/blob/main/docs/STARTUP_004.md)；003 的启动适配依据见[兼容记录](https://github.com/jyh9521/Second-Sight-CN/blob/main/docs/STARTUP_COMPATIBILITY.md)。不要单独关闭 Compatibility 模块再搭配当前固定 FusionFix；该组合会重新遇到原始签名不匹配。

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

构建器只在新包完整校验通过后，按递增包编号保留 `dist/` 中最近两个已完成的受管测试包。005 完成后保留 **004 和 005**，删除 003。删除包括旧包内的测试存档、配置和日志，需要保留的反馈先移到包外。输入材质目录、FusionFix 目录和研究证据不在自动清理范围；未完成或无法识别的目录不自动删除。

反馈请注明包编号、三个功能分别是否生效、场景/操作、分辨率、截图和日志。菜单、真实字幕、PDA 及三者基础共存通过后，再推进全量汉化。
