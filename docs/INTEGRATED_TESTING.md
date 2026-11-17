# 完整三合一测试包与验收约定

012 保留全量首轮译文、思源黑体、FusionFix、5110 张高清材质、HUD 与字幕修复。中文菜单字库扩为 64 像素字格，提升地图／PDA 私有渲染目标分辨率，放大过场时间地点，并给左下角标签保留完整空间。首次加载请等待材质载入。

本页随完成校验的全量首轮测试包交付，版本以同目录 `package.json` 为准；不是005菜单/PDA中间样本。当前已识别目录的目标字段齐全；本轮只完成 27 条记录的标点语境复核，不等于全部译文审校或游戏内通过，自动化不启动、操作或附加游戏进程。

最终包继续保留 **FusionFix、ReMade 高清材质、思源黑体和汉化**，沿用 GOG 启动兼容模块及 `WindowMode=2` 无边框。原安装、EXE 的 LAA 标志、FusionFix 二进制和高清输入不改。文件检查或自有宿主通过不等于游戏通过。

当前内容为 5,957 条 BS、PDA 68 页共 447 段，另有两条 EXE 提示和一张独立生成的载入提示位图。六张 1024×1024 字库当前共 1,958 字形、6,142 个可用字位；六张字库加一张 UI 位图共七项资源。14条旧文本暂无已证活跃消费链，采用受审计调用者约束的延迟绑定；原稿、完整译文均保留。两条EXE提示为防御性覆盖，不声称已在PC实际触发。范围见[全量文本记录](https://github.com/jyh9521/Second-Sight-CN/blob/main/docs/FULL_LOCALIZATION.md)。

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
| `game/scripts/localization/` | SLP3 语言包、manifest、字形清单及许可通知 |

完整包的输出配置仅将固定输入的 `WindowMode=0` 改为 `2`；不改帧率、失焦暂停或其他设置。输入配置保持原字节。003 配置/日志和原 001 配置均已在本地故障证据目录保留。

这是独立的本地游戏副本，不依赖原目录的硬链接或目录联接，也不把三个模组同名覆盖。原安装中的 GOG 输入包装器未复制进测试包。ReMade 本地 DLL 没有版本资源，以包内 hash 清单识别，不根据网站版本号推定其版本。

## 完整包交付后，由用户手动验收

以下检查面向完整包，不要求先测试004/005：

1. 打开本测试包的 `game/` 目录（包编号见 `package.json`），由你手动双击 `secondsight.EXE`。不要使用指向原安装或旧测试包的快捷方式。若从终端启动，先切换到这个 `game/` 目录；ReMade 按工作目录查找材质。
2. 确认无边框、无反复自动切出，检查“选择关卡 / 观看过场动画 / 图形选项 / 档案 / 退出”，再浏览音量、难度、统计、按键设置及档案提示。思源黑体是否清晰、是否裁切也请截图。
3. PDA 先看 Isolation 的“任务目标”和“任务简介”，再看人物、能力、武器资料。重点观察长文自动折行、链接点击、段间接续、翻页和滚动；任务短句“逃离”“离开隔离室”无末尾句号，剧情简介保留正常标点。能力页的动态按键应跟随实际绑定。
4. 开启游戏字幕选项，先复核高分辨率过场字号；醒来后主角独白和 NPC 对话应出现底部字幕，随语音结束消失。暂停、取消对白、重复对白、读档后不应留下旧句。再推进剧情，核对完整句和连续切换，以及病历、邮件、多段电脑文档；检查载入提示。记录进出 PDA、读取存档、关卡切换、切换窗口后的字形、贴图和稳定性。高清包含 108 张 8K 材质，留意加载时间、内存增长和崩溃；本轮没有降采样或应用 4GB 补丁。
5. 退出后保留截图和日志：`game/dsound.log`、`game/scripts/SecondSight.Compatibility.log`、`game/scripts/SecondSight.Localization.log`，以及实际生成的 ReMade/FusionFix 日志。日志没有生成时也请报告，不以文件存在代替功能验收。

当前目录覆盖 **5,957 条 BS 与 PDA 68 页共 447 段**，包括剧情、教程、病历和电脑文档。569 个 BS 槽按空值、内部项、其他平台、姓名或机器字面值等理由保留；WinterICE、JC、密码、文件名、邮箱和检索键不视作漏译。覆盖不等于全游戏可见英文归零。

“快速滚动”“按钮不可用”有已核对消费者及局部容量，但实际 PC 触发可达性尚未完全闭合，现作防御性覆盖。载入提示由 `ui-textures.json` 独立生成，不改原图像素或高清 DDS；版权原图和标志原样保留。旧暂停/Controls 已核对非当前 PC 使用路径，不另加补丁。

BS 日志中的 `expected-direct` 应对照实际交付 manifest 的 `bs_binding.direct_ids`，`deferred` 包括未直接改表的旧文本及五段组合终端。不要把 5,957 总条数直接当成直接替换数量，也不要继续套用 005 的 `expected=832`。PDA 本轮目标为 447 段。日志计数不代替可见文本和布局验收。
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

构建器只在新包完整校验通过后，按递增包编号保留 `dist/` 中最近两个已完成的受管测试包。当前包构建通过后自动保留它与紧邻上一版，删除更早受管包；具体保留清单在构建结果记录。历史 005 完成时清理了 003。删除前，构建器把旧包 profiles、CFG、INI 和 LOG 复制到 build/package-retention/<新包>/preserved-user-files 并逐文件核对 hash；备份失败则停止清理。输入材质目录、FusionFix 目录和研究证据不在自动清理范围；未完成或无法识别的目录不自动删除。

反馈请注明包编号、三个功能分别是否生效、场景/操作、分辨率、截图和日志。全量汉化与离线检查完成后，再统一交付验收；不以中间包测试作为继续生产的前提。

## 历史检查点

001/002 曾遇启动签名问题；003 用户日志确认三个模块初始化，但仍在纹理路径退出；004 已进入菜单并看到部分中文菜单和短 PDA。005 的 832 条 BS、447 段 PDA 属于菜单/PDA 扩展检查点，不是本轮交付范围。历史数据见[005 记录](https://github.com/jyh9521/Second-Sight-CN/blob/main/docs/MENU_PDA_005.md)，不因新目录更新而倒写旧测试结果。

## 字幕功能的边界

新增字幕跟随已审计 speech owner 的真实播放事件，以当前源绑定的 BS 记录查找语言包译文；不通过从关卡开始计时猜测对白。多说话者按优先级稳定选一条，结束/中止清除，重载 HUD 与 BS 时重置；字幕关闭时不绘制。原有定时过场字幕路径保持独立；HUD 内同一条原生/新增对白只绘制一次，不仅凭脚本序列状态屏蔽新字幕。跨路径交接仍需场景验收。

无文本 ID 的音效/呻吟、未走已审计语音队列的媒体，以及尚未确认的其他对白路径，不从现有翻译条数推定已覆盖。完整游戏逐句时间轴和同步验收仍未执行。离线回放验证代码、生命周期和几何，不验证真实 GPU 清晰度、主观阅读速度或全部关卡。

009 复测：开启字幕，复现“啊，不行！我怕是撑不下去了……”及截图附近普通对白，检查两侧竖线是否消失；在原分辨率观察菜单、PDA、过场及对白清晰度，尤其留意“。 ， 、”是否落在正常位置。离线依据见仓库的 `docs/RENDER_POLISH_009.md`。

010 重点：在 4K 重看左上按键教程和左下“徒手”，记录是否够大、是否遮住图标。

012 重点：用相同分辨率比较主菜单、地图和 PDA；检查地图边框、箭头和交互区域；看过场左下时间地点、字幕以及选择「治疗」后文字能否显示完整。选测作弊菜单时，先关闭游戏，在测试包根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Set-GameplayTweaks.ps1 -Mode Enable
```

由你手动启动包内游戏，按 F1 打开「《第二视界》作弊菜单」，勾选无限生命、无限超能力或隐身。关面板保留勾选，退出游戏后开关清空。关闭游戏后可用同一脚本的 `-Mode Disable` 移除加载副本，保留汉化、FusionFix、无边框和高清材质。实际 F1 焦点、鼠标与 Ctrl+F10 共存、玩家伤害、能量和 NPC 感知由用户在游戏内验收。详细边界见仓库的 `docs/MENU_TWEAKS_011.md`。
