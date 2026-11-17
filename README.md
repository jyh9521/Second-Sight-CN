# 《Second Sight》简体中文汉化

PC 版《Second Sight》的简体中文汉化项目。保留原版 FusionFix，以独立本地化模块和结构化语言数据实现中文支持，也为其他语言保留可复用工具。

**当前为菜单与 PDA 扩展测试阶段，尚未正式发布。** PoC 005 将思源黑体、821 条菜单/共享界面文本、PDA 68 页共 447 段整合进独立测试包，保留 FusionFix、ReMade 高清材质和无边框启动。004 的菜单和短 PDA 已有用户反馈；005 的新增内容、长文折行和按键提示待用户实测。

## 当前进度

| 内容 | 状态 |
|---|---|
| PoC 005 | 菜单/PDA 扩展与思源黑体；离线检查后由用户测试 |
| 翻译数据 | 821 条菜单/共享界面 + 11 条原有字幕候选；PDA 447/447 个非空显示段 |
| 字体/术语 | 思源黑体 Regular 2.005，1,170 字形，6 页图集；110 项名词表 |
| 工程验证 | 117 项测试；x86 自有宿主、原字节检查与独立 PDA 回滚 |
| FusionFix / ReMade | 保留固定二进制和 5,110 张材质；输出 WindowMode=2 |
| 未完成 | 005 实机验收、全剧情/电脑文档翻译、通关校对与正式发布 |

当前基线为 GOG PC 版 EXE `0,10,0,0` 和用户提供的 FusionFix `13.11.2026.1802-7bce79f`；文件身份见[技术说明](TECHNICAL.md)。其他版本尚未验证。

**游戏由用户手动启动并反馈验收结果。** 自动化只执行离线开发、构建和文件验证，不自行启动游戏。此前隔离副本的一次启动在截图取证前中止，没有形成实机通过结果。

## 从源码验证

需要 Python 和用户自行提供的原版游戏文件。以下命令只运行不含游戏资产的合成测试：

```powershell
python -X utf8 -m unittest discover -s tests -v
```

中文样本、x86 ASI、离线测试宿主和资源探针的命令见[构建说明](BUILDING.md)。PoC 通过运行时指针提供译文，不改写原 PAK；本地生成的完整资源及隔离游戏副本不作为发行包提交。

本次本地测试包位于 `dist/poc-zh-CN-005/`，完整副本仅供本地测试，不上传 GitHub。新包校验完成后保留 004、005 两版；原安装与两套模组输入保持不变。测试说明见[三合一测试](docs/INTEGRATED_TESTING.md)，覆盖统计、保留专名和验收重点见[005 记录](docs/MENU_PDA_005.md)。

11 条剧情字幕候选保持不变，未当作已完成剧情汉化。菜单的内部控件名、其他平台存储提示、键帽简称及非本轮的电脑邮件/剧情不计入“已翻译菜单”。

## 项目文档

- [构建与验证](BUILDING.md) · [PoC 手动测试](docs/POC_TESTING.md) · [已知问题](docs/KNOWN_ISSUES.md)
- [翻译约定](TRANSLATING.md) · [技术路线](TECHNICAL.md)
- [文件格式](docs/FILE_FORMATS.md) · [踩坑记录](docs/PITFALLS.md)
- [2026-11-17 初始可行性评估](docs/ASSESSMENT_2026-11-17.md)：保留当时证据，当前进度以本页和已知问题为准。
- [ReMade 高清材质兼容评估](docs/REMASTERED_COMPATIBILITY_2026-11-17.md)：保留整合前的离线评估，PoC 002 的布局见三合一测试说明。

## 来源与许可

本项目不包含原版游戏、原始资源或 FusionFix 整套二进制。项目自有代码采用 [MIT](LICENSE)，原创译文采用 [CC BY-SA 4.0](LICENSE-translations.md)；004 字库基于 Noto Sans CJK SC，新源码改用思源黑体 Source Han Sans SC（均为 SIL OFL 1.1）；第三方内容分别遵循其原许可，详见[许可与分发边界](LICENSING.md)。

字体来源、[名词表](locales/zh-CN/glossary.json)与标点铁律见[翻译约定](TRANSLATING.md)。[前一轮编辑基线](docs/FONT_AND_EDITORIAL.md)保留 004 反馈与当时仅离线语言包的历史状态。
