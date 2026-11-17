# 《Second Sight》简体中文汉化

Windows PC 固定 GOG 版本的可复用汉化工程：结构化译文、资源提取与验证工具，以及独立本地化 ASI。原版游戏和第三方模组由使用者自行提供。

**当前是本地实验候选，不是正式发行。** 用户反馈的高分辨率过场字小已加入专用缩放；独白和 NPC 对话新增独立语音事件字幕，不再仅调查原生显示门控。两者已进入 008；[009](docs/RENDER_POLISH_009.md) 又补充处理了时长型对白、字幕竖线和字库清晰度，通过离线回放与包文件校验；游戏内效果由用户验收。严格目录门禁的 51 项发现已经处理，见[编辑修复](docs/EDITORIAL_REPAIR.md)与[CI 记录](docs/CI_REPAIR.md)。没有公开完整游戏测试包下载。

## 覆盖与边界

| 类别 | 有目标文本 | 可追溯逐条审校 | 009 逐条运行通过 |
|---|---:|---:|---:|
| BS 主文本 | 5,957 / 5,957 | 0 条已登记；其余未知 | 0 条已登记；其余未测 |
| PDA 显示段 | 447 / 447 | 0 条已登记；其余未知 | 0 条已登记；其余未测 |
| EXE 条件提示 | 2 / 2 | 0 条已登记；其余未知 | 0 条已登记；其余未测 |
| 图像文字 | 1 / 1 张（2 行） | 0 张已登记；其余未知 | 0 张已登记；其余未测 |

“有目标文本”只表示首轮目标字段齐全，不代表译文正确、审校完成或所有屏幕英文归零。BS 另有 569 槽按理由保留；14 条活跃消费者未明的旧文本仍在 5,957 分母内。已有人工修改和 004/006 用户反馈保留为历史，未据此编造当前源/目标及 当前候选绑定的逐条验收台账。详见[资源清单与状态口径](docs/PROJECT_CONTRACT.md)、[验收快照](docs/ADOPTION_VALIDATION.md)。

当前字库为思源黑体 Source Han Sans SC Regular 2.005，已识别静态目录使用 1,958 个字形。动态输入、长文本排版、字幕时间轴和设备重置仍有待验证项。

## 兼容与本地候选

已建立离线契约的组合为固定 GOG EXE、用户提供的 FusionFix `13.11.2026.1802-7bce79f`、Ultimate ASI Loader 与 ReMade 高清材质；无边框输出配置为 `WindowMode=2`。其他商店版本、地区版本和模组版本未验证。精确输入身份见[项目适配](docs/PROJECT_CONTRACT.md)。

本地保留 **008、009**。新候选保留 FusionFix、ReMade 高清材质、思源黑体与无边框配置。完整包校验通过后只保留最新两版；旧包存档、配置和日志先另存并校验。007 的字库切页修复见[007记录](docs/GLYPH_FIX_007.md)，不据此外推其他画面通过。由用户运行游戏，自动化不启动、操作或附加游戏进程。

## 从源码检查

以下命令从仓库根目录执行。离线测试使用 Python 3.14 及 [requirements.txt](requirements.txt) 中的依赖；这些检查不需要启动游戏。实际命令结果见[验收快照](docs/ADOPTION_VALIDATION.md)。

```powershell
python -X utf8 -m unittest discover -s tests -q
python -X utf8 tools/check_docs.py
python -X utf8 tools/audit_coverage.py --locale-dir locales/zh-CN
python -X utf8 tools/audit_locale_policy.py --locale-dir locales/zh-CN
```

最后一条及严格目录命令 `python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN` 当前均返回 **0**。工程与严格目录 CI 分开保留；修复译文和精确语境，不删除检查或改变通知设置。语言包及 x86 ASI 的真实构建前提、历史命令和恢复办法见[BUILDING](BUILDING.md)与[本地候选使用说明](docs/INTEGRATED_TESTING.md)。

## 参与翻译与工程维护

- 翻译前读[工作流程](TRANSLATING.md)、[中文 STYLE](locales/zh-CN/STYLE.md)和[名词表](locales/zh-CN/glossary.json)；保留稳定 ID、源文指纹、上下文与控制码。
- 工程从 [AGENTS](AGENTS.md) 按任务路由阅读；新基准采用及条款冲突见[迁移记录](docs/BASELINE_ADOPTION.md)。示例规范不是游戏已实现功能。
- 反馈应附候选版本、场景、分辨率、复现步骤与截图。未测组合保持未验证。

## 文档与许可

[技术说明](TECHNICAL.md) · [文件格式](docs/FILE_FORMATS.md) · [已知问题](docs/KNOWN_ISSUES.md) · [踩坑记录](docs/PITFALLS.md) · [验收标准](docs/ACCEPTANCE.md)

自有代码及工程文档采用 [MIT](LICENSE)，原创译文采用 [CC BY-SA 4.0](LICENSE-translations.md)。字体及第三方组件保持各自许可和来源通知，详见[许可说明](LICENSING.md)。仓库不分发完整原版游戏、原始资源、FusionFix/ReMade 整套文件或转储；兼容性不等于第三方再分发授权。
