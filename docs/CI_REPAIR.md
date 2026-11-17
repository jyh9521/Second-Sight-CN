# GitHub Actions 目录门禁失败记录

## 已确认的失败原因

用户报告近期持续收到 GitHub 构建失败邮件。本次直接读取 Actions 运行、job、step 和日志，确认失败发生在严格译文目录门禁，**不是 C++ 编译失败**：

| 运行 | 源码 | 工程 job | 目录 job |
|---|---|---|---|
| [44050722902](https://github.com/jyh9521/Second-Sight-CN/actions/runs/44050722902) | `a74c4b3be5c721cf287e2d9a632c255a599c115c` | `133927552542`，success | `133927553070`，failure |
| [44037912405](https://github.com/jyh9521/Second-Sight-CN/actions/runs/44037912405) | `af73f71f47e361179f252bb1601eadd5abc9976f` | `133885167524`，success | `133885166632`，failure |

两次失败 step 均为：

```powershell
python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN
```

远端日志的实际结果均为：

```text
EDITORIAL FAIL: errors=51; punctuation + glossary; no game execution
##[error]Process completed with exit code 1.
```

同一命令在仓库根目录直接调用 Python 的本地复现返回 **2**。GitHub 的 PowerShell step 报告 **1**，两者分别记录，不把 shell step 的退出码写成 Python 自身的退出码。

51 项发现来自既有逐句检查：45 处明确句号问题及 6 处语境待审，涉及 27 条记录。个人写法仍以 [STYLE](../locales/zh-CN/STYLE.md) 为唯一来源；查出问题后的处理应修正数据或有证据的上下文适配，不能通过 `continue-on-error`、删除 job、关闭通知或无条件抑制来把失败变成成功。

## 修复与验收要求

当前 [.github/workflows/offline.yml](../.github/workflows/offline.yml) 的工程和严格目录 job 均保留。工程 job 已在上述两次真实远端运行中成功；无需为本次故障改动编译参数或降低检查等级。

修订目录后，重新执行严格检查，再推送候选并核对**该提交**的新 Actions 运行。旧失败记录不会因新源码修复而自动改成成功。

日志另有旧版 checkout/setup-python 的 Node 运行时弃用 warning；它未使上述工程 job 失败，和这次 51 项数据发现分开处理，不将升级动作冒充根因修复。

## 已验证的远端恢复

目录修复提交 `64c0e7501755d0bfed407cee5eb206f66b04cde6` 的新运行 [44057388724](https://github.com/jyh9521/Second-Sight-CN/actions/runs/44057388724) 已实际完成，结论为 **success**：

| job | ID | 实际结果 |
|---|---|---|
| offline | `133950138196` | success：241 项测试、文档/覆盖检查、MSVC 构建及合成宿主通过 |
| Strict catalog gate | `133950138871` | success：`EDITORIAL PASS: errors=0; punctuation + glossary; no game execution` |

修复的是[逐句数据及精确语境适配](EDITORIAL_REPAIR.md)，没有关闭检查或通知。该远端通过仅绑定此提交；后续字幕运行时改动仍需其自身新运行结果，不从本次绿灯外推。

## 证据位置与边界

本地 `build/ci-repair/` 保存：

- `runs-before.json`：最近十次运行的实际状态
- `jobs-44050722902.json`、`jobs-44037912405.json`：job/step 结果
- `job-133927553070.log`、`job-133885166632.log`：失败 job 的真实日志
- `catalog-baseline.json`：本地失败命令、stdout/stderr 和退出码
- `run-44057388724.json`、`jobs-44057388724.json` 和对应两个 job 日志：修复提交的实际远端成功证据

读取 GitHub 使用既有目标仓库授权，凭据不打印、不写入证据。上述目录不提交到 GitHub。没有启动游戏、运行第三方模组、采集转储或修改邮件通知设置。
