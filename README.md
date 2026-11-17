# 《Second Sight》简体中文汉化

> **交付约定：先完成全量汉化、文字校对与离线检查，再一次性交由用户测试。中间版本只作开发检查点；自动化不启动、操作或附加游戏进程。**

PC 版《Second Sight》的简体中文汉化项目。保留原版 FusionFix，以独立本地化模块、结构化语言数据和可复现工具实现中文支持，也为其他语言保留工程基础。

**固定 PC 版本的全量首轮译文与离线整合已完成，完整006测试包已构建并校验。** 包括5,957条主文本、PDA全部68页的447段、两条防御性EXE提示和一张载入提示位图。资源目录覆盖不等于游戏通关验收，旧资源与版权图的边界明确保留。

## 当前进度

| 内容 | 状态 |
|---|---|
| 主文本（BS） | 5,957 条译文；6,526 个槽位全部分类，569 个空槽、机器值或其他有理由的条目原样保留 |
| PDA | 68 页、447 个非空显示段进入译文目录；任务指令与剧情正文分别遵循标点规则 |
| 字体 | 思源黑体 Source Han Sans SC Regular 2.005；当前 1,958 字形，6 张 512×512 图集、6,142 个可用字位 |
| 图像文字 | `ui-textures.json` 独立生成载入提示；当前语言包设计为 6 张字体图集 + 1 张 UI 位图，不修改原 PAK 或高清材质输入 |
| EXE 提示 | 两条提示加入 SLP2 防御性覆盖；消费者与容量已证，实际触发可达性仍待闭合 |
| 离线检查 | 144 项测试、真实/合成语言包自有宿主、两次构建字节复现和 BS/PDA 独立副本回滚均通过；未运行游戏 |
| 旧资源边界 | 14条旧文本无已证活跃消费链，完整译文保留、受审计调用者延迟绑定；两条EXE提示防御性覆盖；不把有界静态搜索写成全局不可达 |
| 最终包约定 | FusionFix + ReMade 高清材质 + 汉化，`WindowMode=2` 无边框；只保留最近两个完成校验的受管包 |

固定输入为 GOG PC EXE `0,10,0,0` 和用户提供的 FusionFix `13.11.2026.1802-7bce79f`；身份见[技术说明](TECHNICAL.md)。其他游戏版本未验证。

004 已有用户进入菜单、看到部分中文菜单和短 PDA 的反馈。004/005 现在仅是历史检查点，不再要求先测试 005；本轮已生成全量首轮006并保留005作为上一版；没有宣称完整通关或模组共存验收通过。详见[全量文本记录](docs/FULL_LOCALIZATION.md)和[已知问题](docs/KNOWN_ISSUES.md)。

## 从源码验证

需要 Python 和用户自行提供的原版游戏文件。以下命令只运行合成测试或检查翻译数据，不启动游戏：

```powershell
python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN
python -X utf8 tools/audit_coverage.py --locale-dir locales/zh-CN
python -X utf8 -m unittest discover -s tests -v
```

语言包、x86 ASI、自有离线宿主和完整包的构建命令见[构建说明](BUILDING.md)。运行时提供经校验的译文指针和资源，不改写原 PAK；完整游戏副本与本地双语提取稿不上传 GitHub。

本轮完整包与结果见[006交付记录](docs/FULL_TEST_006.md)，操作见[手动验收步骤](docs/INTEGRATED_TESTING.md)。包内保留无边框、FusionFix 和完整 ReMade 输入；新包通过校验后才执行最近两版保留规则，不把未完成目录当成可交付版本。

## 项目文档

- [全量进度与交付门槛](docs/FULL_LOCALIZATION.md) · [构建与验证](BUILDING.md) · [已知问题](docs/KNOWN_ISSUES.md)
- [翻译约定](TRANSLATING.md) · [技术路线](TECHNICAL.md) · [文件格式](docs/FILE_FORMATS.md)
- [全量字体与文本容量](docs/research/FULL_TEXT_CAPACITY.md) · [踩坑记录](docs/PITFALLS.md)
- 历史：[初始评估](docs/ASSESSMENT_2026-11-17.md) · [005 菜单/PDA 检查点](docs/MENU_PDA_005.md) · [004 字体与编辑基线](docs/FONT_AND_EDITORIAL.md)
- [ReMade 高清材质评估](docs/REMASTERED_COMPATIBILITY_2026-11-17.md) · [三合一包结构](docs/INTEGRATED_TESTING.md)

## 来源与许可

项目自有代码采用 [MIT](LICENSE)，原创译文采用 [CC BY-SA 4.0](LICENSE-translations.md)。当前思源黑体与早期 Noto Sans CJK SC 均按 SIL OFL 1.1 保留字体许可；第三方内容遵循各自许可，见[许可与分发边界](LICENSING.md)。仓库不包含原版游戏、完整原始资源或整套 FusionFix/ReMade 二进制。

字体来源、[名词表](locales/zh-CN/glossary.json)和标点铁律见[翻译约定](TRANSLATING.md)。
