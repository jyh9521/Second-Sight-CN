# 008：新增游戏中对白字幕与过场字号

## 交付状态

已生成独立本地完整候选 `dist/poc-zh-CN-008`，5414 个受清单约束文件通过校验；保留 FusionFix、ReMade 全部 5110 张 DDS、思源黑体、全量首轮译文及 `WindowMode=2`。未启动、操作或附加游戏，状态为 `awaiting-user-runtime-test`，不是正式发行或全游戏验收通过。

这次按用户纠正，**新增独白/NPC 的字幕显示功能**，不再把取得新转储作为继续工作的前置条件。现有语音 BS 记录的目标文本作为来源，不凭空转录或用关卡开始时间猜测对白。

## 身份

| 产物 | SHA-256 |
|---|---|
| 原 GOG EXE（保持不变） | `4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda` |
| 007 基线 ASI | `fe4b102f17eeb0e900c0d1bdaf3da89c7069cb2e26ebe65dc0ae84c77687219c` |
| 008 本地化 ASI | `9205468bbd1d5a91427837dd3c9142ae74fd1bc44d778f014d57440565ba54f4` |
| 008 locale.bin | `151beae66c5a207d8229a84b1549d3d83e76875b6ba450c134c88e9c4b2eef40` |
| 008 package.json | `9765252377c205264d817e4553ebafd7e7293603f8e6c63b72944f4f4b793563` |

独立编译目录与实际包内 ASI/locale hash 完全一致。`package.json` 保存完整相对路径及文件 hash，私有完整游戏副本与第三方资源不上传 GitHub。

## 改动与证据层级

- `0x456610`：保存寄存器/flags，观察 speech 事件后仍执行原回调与分发；BS ID、音频 handle、优先级进入有限状态表
- `0x63D78A`：在原 HUD 接入处绘制新增字幕，保留没有新 cue 时的原生 fallback；尊重字幕选项，HUD 内相同对白不绘制两次
- `0x63D494`：HUD 初始化清掉旧 cue；BS 重载也清状态；结束/中止事件清对应 owner，取消排队项不误杀正在说的那句
- `0x543031`、`0x5431E8`：过场专用私有 `Style.x/y *= RenderHeight/480`，测量/折行/绘制共用样式，出口恢复，不永久放大菜单/PDA
- 不改 FusionFix 的文字入口，不改原 EXE、FusionFix 二进制和 ReMade 输入；27 条固定上游写区间与当前 21 处审计区间不相交

[事件研究](research/GAMEPLAY_CAPTIONS.md)维护 ABI、字段和原生回放细节；[首轮记录](research/SUBTITLE_008.md)保留字号发现与早期调查。曾考虑依据脚本序列标志屏蔽新增字幕，复核发现它不等于“已经有定时字幕”，故移除该条件；没有把不确定的门控重新加回功能。

| 验证层级 | 本轮结果 | 不代表什么 |
|---|---|---|
| 数据校验 | 严格目录 0 错误；5957 BS、447 PDA、2 EXE 目标字段；源绑定构建通过 | 非全量审校；27 条仅按标点语境复核 |
| 自有工程 | 243 项测试；真实/合成宿主；错误宿主拒绝；x86 编译 | 非游戏运行 |
| 离线原生回放 | 新字幕 33/33；过场字号 12/12；字库批次 14/14 | 非音频设备、GPU 像素或所有对白场景 |
| 本地包验证 | 5414 文件；包内 ASI/locale 与回放产物一致；原安装 307 文件不变 | 非正式安装器/升级卸载 G4 |
| 游戏内 | 未执行，由用户测试 | 不用上述通过替代 G3 |

语音/BS 输入、音频 ready/active、GPU 提交及操作系统资源边界在回放中明确为合成输入；生产编译的事件、状态、绘制、wrap 及原生测量代码实际执行。未沿已审计队列播放的声音、无 BS 的音效/呻吟和未提供文本的音频不据此宣称补全。跨 timed 路径交接、同屏可读性、长对白阅读速度及全关卡覆盖留待实际验收。

## 基线、修改和隔离恢复

命令入口及前提见 [BUILDING](../BUILDING.md#008-新增对白字幕与完整包)。本地四件证据位于 `build/gameplay-captions/verification-final/`，均已重开：

- `MODIFIED_FILE.asi`：保留改动的模块
- `DIFF_FILE.patch`：相对 007 源码的字号与新增字幕差异
- `VERIFICATION.txt`：输入 hash、绝对命令、stdout/stderr、退出码和恢复状态
- `ROLLBACK.sh`：实际用 Git Bash 执行，只恢复命名独立副本，不触碰原安装或交付包

| 步骤 | 字面摘要 | 退出码 |
|---|---|---|
| BASELINE | `BASELINE REPRODUCED: gameplay=1; cutscene=1; host=0; added captions absent and fixed pixel scale` | 1，预期红 |
| MODIFIED | `MODIFIED PASS: gameplay=33/33; cutscene=12/12; host=0; game_launched=false` | 0 |
| ROLLBACK | `ROLLBACK PASS: isolated ASI and locale restored to 007; native cases equal baseline; modified retained; game_launched=false` | 0 |

恢复文件的 ASI/locale 分别回到冻结 007 hash；另一个原生映射副本恢复五处补丁，行为 cases 与基线严格相等。当前模块和 008 仍保持修改。基线/恢复回放保留未改变的生产 wrap 代码，以隔离新增字幕/字号变量；真实 007 模块另由自有宿主检查。

初版证据 wrapper 曾因把 `rollback_bytes_verified` 的真假审计标志混入行为 cases 而拒绝比较；把该标志移到报告顶层后，恢复字节核对保留，行为可严格逐项比较。失败尝试留在 `build/gameplay-captions/verification/ATTEMPT.txt`，不覆盖成功证据。

## 保留与恢复

新包完整校验后，已验证绝对路径并清理 006，删除 9235749631 字节。本地只保留 **007、008**；007 的用户配置不回写。006 的 6 份 CFG/INI/LOG 在删除前复制、校验到 `build/package-retention/poc-zh-CN-008/preserved-user-files/`，其 profiles 原本为空；后续保留策略也包含 profiles 文件。备份失败停止清理。

使用独立旧包 007 可回到本次字幕变更前的运行候选；它仍有已反馈的小字号/无新增字幕问题。包内 `Disable-Localization.ps1` 用于单独关闭汉化，不等于回到纯原版。实际用户操作步骤和待验收项见[完整测试说明](INTEGRATED_TESTING.md)。

## GitHub 构建

真实失败源于严格目录的 51 项编辑发现，不是 MSVC 故障。修复数据和精确语境后，两项远端 job 已通过；不删门禁、不关闭通知。运行链接与原始失败证据见[CI 修复记录](CI_REPAIR.md)。最终字幕源码提交另核对其对应 run，本地结果保存在 `build/ci-repair/final-*.json`，不把较早数据提交的通过冒充最终源码通过。
