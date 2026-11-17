# 《Second Sight》简体中文汉化

PC 版《Second Sight》的简体中文汉化项目。保留原版 FusionFix，以独立本地化模块和结构化语言数据实现中文支持，也为其他语言保留可复用工具。

**当前处于中文最小样本开发阶段，尚未发布可玩的汉化补丁。** 独立模块、语言包与 **PoC 002 三合一本地测试副本已完成离线构建**。先由用户验证菜单、剧情字幕和 PDA，再推进全量翻译。离线检查不代表游戏内显示或三者共存已通过。

## 当前进度

| 内容 | 状态 |
|---|---|
| PoC 002 | 高清材质 + FusionFix + 汉化独立包；71 项合成测试、离线宿主、文件清单与独立副本回滚通过 |
| P4CK 封包、主文本 BS | 已完成静态解析与离线回写/回滚验证 |
| 中文字形与编码 | 6 张图集和标记编码已实现；显示、宽度与换行待实测 |
| 中文菜单、剧情字幕、PDA 最小样本 | 21 条菜单、11 条剧情字幕候选、同一 PDA 任务页 4 条文本；游戏内未验收 |
| 原版 FusionFix + 独立 `SecondSight.Localization.asi` | 模块已实现；运行时共存未验收 |
| 全量翻译、通关校对、正式发布 | 尚未开始 |
| ReMade 高清材质包 | 已整合 5,110 张材质；ReMade 保持 `dinput8.dll`、UAL 使用 `dsound.dll`，运行时共存待测 |

当前基线为 GOG PC 版 EXE `0,10,0,0` 和用户提供的 FusionFix `13.11.2026.1802-7bce79f`；文件身份见[技术说明](TECHNICAL.md)。其他版本尚未验证。

**游戏由用户手动启动并反馈验收结果。** 自动化只执行离线开发、构建和文件验证，不自行启动游戏。此前隔离副本的一次启动在截图取证前中止，没有形成实机通过结果。

## 从源码验证

需要 Python 和用户自行提供的原版游戏文件。以下命令只运行不含游戏资产的合成测试：

```powershell
python -X utf8 -m unittest discover -s tests -v
```

中文样本、x86 ASI、离线测试宿主和资源探针的命令见[构建说明](BUILDING.md)。PoC 通过运行时指针提供译文，不改写原 PAK；本地生成的完整资源及隔离游戏副本不作为发行包提交。

本次本地测试包位于 `dist/poc-zh-CN-002/`，含测试说明、高清层开关和禁用汉化脚本；完整副本不上传。构建器只保留最近两个已完成包，目前为 001 和 002。原安装及用户提供的两套模组输入保持不变，本轮没有启动游戏。

本包操作见[三合一测试说明](docs/INTEGRATED_TESTING.md)，样本与模块日志详见[基础 PoC 说明](docs/POC_TESTING.md)。11 条剧情文本仍属候选，尚未完成场景对应，不能视为已有 11 条字幕实测。

## 项目文档

- [构建与验证](BUILDING.md) · [PoC 手动测试](docs/POC_TESTING.md) · [已知问题](docs/KNOWN_ISSUES.md)
- [翻译约定](TRANSLATING.md) · [技术路线](TECHNICAL.md)
- [文件格式](docs/FILE_FORMATS.md) · [踩坑记录](docs/PITFALLS.md)
- [2026-11-17 初始可行性评估](docs/ASSESSMENT_2026-11-17.md)：保留当时证据，当前进度以本页和已知问题为准。
- [ReMade 高清材质兼容评估](docs/REMASTERED_COMPATIBILITY_2026-11-17.md)：保留整合前的离线评估，PoC 002 的布局见三合一测试说明。

## 来源与许可

本项目不包含原版游戏、原始资源或 FusionFix 整套二进制。项目自有代码采用 [MIT](LICENSE)，原创译文采用 [CC BY-SA 4.0](LICENSE-translations.md)；PoC 字库基于 Noto Sans CJK SC（SIL OFL 1.1）；第三方内容分别遵循其原许可，详见[许可与分发边界](LICENSING.md)。
