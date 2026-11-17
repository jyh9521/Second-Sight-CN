# 基准采用验收快照

本页只记录 2026-11-17 规范迁移与离线检查，不替代[验收标准](ACCEPTANCE.md)。基础源码为 `10d4dfc7cc30f9a3f251fe1a6cc16a437c73b185`，冻结运行候选仍是 007；本次没有生成新游戏候选。测试者为本地自动检查；用户尚未执行本轮 G3，手动检查没有伪造退出码。

## 证据身份

- 工具/测试/STYLE 输入集 SHA-256：`4411a52ea44f0e955cefd947a08e38e08d1fbd2903a06345be9e71ecf8c65a73`（逐文件列表本地 `code-inputs.json`）。
- 原安装 307 文件清单 SHA-256：`84682e8ee59683112b5454f1caf8f27f06a5772cf54ac8d24cc4ae86eb2d0713`；Windows x86 固定 EXE，地区/商店修订未知，详见[输入身份](PROJECT_CONTRACT.md#输入身份)。
- 新策略目录发现及目标指纹：[policy-review.json](../locales/zh-CN/policy-review.json)，SHA-256 `d8ce9ef43289ed9a721d7e89c0a76a0926c6b157c420691be1863c24a824abcd`。
- 007 包清单 SHA-256：`3e3702b9f73c3efd7b1917f3d73c965a7bf836aed807d16d22bc57fc5b96b3e5`。与本轮源码检查候选分开，不拿旧二进制代表新规范通过。
- 本地环境：Windows / Python 3.14；Python 工程依赖见 [requirements](../requirements.txt)。完整版本及字面输出在本地证据目录。

## 保留包只读复核

006/007 各复核 5,414 个清单文件：006 的 `game/secondsight.cfg`，007 的 `game/secondsight.cfg` 与 `game/scripts/SecondSight.FusionFix.cfg` 和原打包清单不同。其余清单文件匹配。当前 007 的无边框配置仍为 `WindowMode=2`，分辨率覆盖为 2880×1800。本轮没有修改这些配置，保留现状，不重置或重写旧包清单；差异来源未在本轮确认。此复核不等于整个旧包仍与出厂清单完全一致，也不替代 G4。

## 分项覆盖

| 内容及分母 | 目标字段覆盖 | 当前源/目标绑定审校登记 | 007 运行验证登记 |
|---|---:|---:|---:|
| BS 5,957 条 | 5,957 / 5,957（100%） | 0 / 5,957（0%）；5,957 状态未登记 | 0 / 5,957（0%）；未测 |
| PDA 447 段 | 447 / 447（100%） | 0 / 447（0%）；447 状态未登记 | 0 / 447（0%）；未测 |
| EXE 提示 2 条 | 2 / 2（100%） | 0 / 2（0%）；2 状态未登记 | 0 / 2（0%）；未测 |
| 图像文字 1 张、2 行 | 1 / 1（100%） | 0 / 1（0%）；状态未登记 | 0 / 1（0%）；未测 |

“登记 0”指尚无满足新证据绑定口径的逐条台账，不抹去历史人工修改。569 个 BS 槽有保留理由，另列而不冒充译文；14 条旧文本的消费者未定但有目标，仍留在分母。上述 100% **仅为已识别目录的目标字段完整度**，不是 reviewed、全屏无英文或完整完成声明。内容角色仍待复核，字幕也没有独立 cue/时间覆盖分母。

## 实际命令与结果

工作目录为仓库根目录；`E` 表示本地 `build/baseline-adoption-20261117`，不是发布目录。精确绝对路径、完整标准输出/错误、输入 hash、退出码见该目录的 `VERIFICATION.txt` 和 `commands.json`。

| 检查 | 实际命令 | 结果/退出码 |
|---|---|---|
| 旧工程基线 | `python -X utf8 -m unittest discover -s tests -q`（修改前） | 189 tests / OK，0 |
| 新工程回归 | `python -X utf8 -m unittest discover -s tests -q` | 203 tests / OK，0；包括正确识别已有失败的测试，不是 G1 通过 |
| 严格逐句审计 | `python -X utf8 tools/audit_locale_policy.py --locale-dir locales/zh-CN --out build/baseline-adoption-20261117/style-audit.json` | `SENTENCE_POLICY FAIL: records=27; violations=45; review=6; mutations=0; game_launched=false`，2 |
| 编辑门禁 | `python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN` | `EDITORIAL FAIL: errors=51; punctuation + glossary; no game execution`，2 |
| 目录分类 | `python -X utf8 tools/audit_coverage.py --locale-dir locales/zh-CN` | COVERAGE PASS，0；`source_bound=false`，只证实 ID 分类/目标存在 |
| 文档链接 | `python -X utf8 tools/check_docs.py` | 本地链接检查通过，0；外部链接仅计数，未在线检查 |
| 构建拒绝 | `python -X utf8 tools/build_locale.py --game-root <本地原版目录> --locale zh-CN --out build/baseline-adoption-20261117/blocked-candidate` | `ValueError: editorial checks failed`，1；输出目录未创建 |
| 合成反例与副本回滚 | E 内 `probe.py` 的 BASELINE/MODIFIED 与 `ROLLBACK.sh` | 旧检测 False / 1；新检测 True / 0；副本恢复原 hash 与 False 行为，回滚脚本 0 |

反例输入是非剧情 UI「保存完成，请继续。按键返回。」；预期检测为 True。明确失败与含糊待审均阻止新语言包。没有为绿色 CI 将待审项转成例外；严格目录任务当前预期失败，工程任务单独报告。

## 门禁结论

- **G0：not_run（全门禁）**。已识别固定 EXE/成员契约并只读清点 307 文件；全输入 manifest 前置拒绝及其负例尚未实现完毕。
- **G1：fail**。上述 51 项待解决；全量逐条源/目标绑定审校与重复 JSON 键拒绝也未齐。
- **G2：本轮 not_run**。007 历史资源/切页离线验证保留，本轮只测规范与工具，未重建游戏资源。
- **G3：not_run**。007 没有候选绑定的运行观察；不启动游戏、不要求用户现在测试。
- **G4：not_run**。无新公开补丁/安装器发行；本地文件 hash 复核不代替安装升级卸载验收。

四个本地交付证据为 `MODIFIED_FILE.py`、`DIFF_FILE.patch`、`VERIFICATION.txt`、可执行 `ROLLBACK.sh`。回滚只作用于另一份检查器副本，工作树继续保留新实现；原游戏、基准输入及 006/007 不作修改。

本快照保留基础游戏候选身份；文档在正常合并远端 `d0c81c1` 后重新运行链接、回归及门禁检查，工程代码没有被远端替换。合并经过见[迁移合并记录](BASELINE_ADOPTION.md#并行远端迁移的合并)。
