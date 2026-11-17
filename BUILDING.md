# 构建与离线验证

当前中文样本、独立 x86 ASI、离线宿主和 **PoC 004 无边框测试包已完成离线构建与检查**；游戏内显示及高清材质/FusionFix 共存均待用户验收。**以下自动化只处理文件或运行自有测试宿主，不启动游戏。**

## 环境与输入

- Windows、Python；初始资源实验使用 Python 3.14.2。
- [requirements.txt](requirements.txt)固定 Pillow、fonttools、pefile 与 capstone 版本。
- Visual Studio / Build Tools 的 MSVC x86/x64 C++ 工具及 Windows SDK。构建脚本通过 `vswhere` 定位工具链，生成 x86 产物。
- 原版 GOG PC 游戏文件，版本与 SHA-256 见[技术说明](TECHNICAL.md)。
- 用户提供的固定版本 `FusionFix/`，供后续隔离副本联合测试；该目录不纳入 Git。
- 首次语言包构建需要按 `locales/<locale>/font.json` 下载固定提交的字体与 OFL（中文现用思源黑体）；后续使用经过 hash 校验的本地缓存。

从仓库根目录运行。建议使用独立 Python 环境；以下命令中的 `$Game` 始终指向原版输入，不是安装目标。

```powershell
$Game = 'C:\Program Files (x86)\GOG Galaxy\Games\Second Sight'
python -m pip install -r requirements.txt
python -X utf8 -m unittest discover -s tests -v
python -X utf8 tools/build_locale.py --game-root $Game --locale zh-CN --out build/locale-zh-CN
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_runtime.ps1
```

`build_runtime.ps1` 默认输出 `build/runtime`，可通过 `-Out` 指定仓库内其他构建目录。它使用 C++17、`/W4 /WX` 和可复现构建参数，编译模块与自有测试宿主；不调用游戏。

## 中文样本输出

输入为 [locales/zh-CN/poc.json](locales/zh-CN/poc.json)：21 条菜单、11 条剧情字幕候选，以及 Isolation 任务页的 4 条 PDA 文本。字幕候选尚未完成场景映射，4 条 PDA 文本也不是 4 个页面。

构建器校验 EXE、主文本和找到的全部 `pdaps_a.raw` 副本的 hash，逐条核对原文；不接受未知版本或原文不符的数据。字体由各语言的 `font.json` 固定提交与 SHA-256；中文现用思源黑体 Regular，字形由样本文本确定；当前六页分配跳过原引擎特殊编号 178、184，共 1,534 个候选字位，不代表完整汉化容量已解决。编码后 BS 上限为 255 字节、PDA 上限为 450 字节；这些保守护栏不是游戏布局验收。

| 输出 | 用途 |
|---|---|
| `build/locale-zh-CN/locale.bin` | SLP1 语言包：BS/PDA 原文校验记录、标记编码译文、6 张 256×256 DXT3 DDS |
| `build/locale-zh-CN/manifest.json` | 输入 hash、字形映射、字体来源与资源 hash |
| `build/locale-zh-CN/atlas-preview.png` | 第一页字形图集预览，不是游戏截图 |
| `build/locale-zh-CN/OFL.txt` | 字体原许可证，随使用图集的测试包保留 |
| `build/locale-zh-CN/BASELINE.raw`、`MODIFIED_FILE.raw` | PDA 离线回写验证副本；不是运行时安装文件，不公开分发 |
| `build/runtime/SecondSight.Localization.asi` | 独立 x86 本地化模块 |
| `build/runtime/localization_host.exe` | 仅测试自有模块/数据的离线宿主，不是游戏启动器 |

PoC 运行时在 BS 加载后替换指定条目指针，在 PDA 解析/重定位后替换指定字段指针；字体数据由模块提供。它不改写安装目录中的 EXE 或 PAK，也不通过整包替换绕过 PDA 的加载/缓存路径。

## 离线宿主检查

构建完成后运行自有宿主，使用绝对参数路径避免 DLL 搜索位置歧义：

```powershell
$Root = (Get-Location).Path
& "$Root/build/runtime/localization_host.exe" `
  "$Root/build/runtime/SecondSight.Localization.asi" `
  "$Root/build/locale-zh-CN/locale.bin"
```

宿主检查语言包、截断输入、字形标记边界、自有内存的修改/恢复，以及非目标 EXE 身份拒绝。它不会执行游戏内挂钩路径；输出 `HOST PASS` 也不代表中文界面或 FusionFix 实机通过。

## 隔离三合一测试副本

`tools/stage_poc.py` 重新构建语言包与 ASI、运行自有离线宿主，再复制原游戏、固定 FusionFix 与可选 ReMade 输入。它不启动游戏，不加载第三方 DLL；拒绝已有输出、输入/输出重叠和目录联接，核对构建前后原安装及第三方输入的 hash。

```powershell
python -X utf8 tools/stage_poc.py --game-root $Game --fusionfix-root FusionFix --remastered-root "ReMade With Second Sight Remastered Textures" --out dist/poc-zh-CN-004
python -X utf8 tools/stage_poc.py --verify --out dist/poc-zh-CN-004
```

004 已存在时使用新的递增编号，例如 005。输出必须是仓库 `dist/` 的直接子目录，命名为 `poc-<locale>-NNN`。省略 `--remastered-root` 可构建仅 FusionFix + 汉化的对照包；HD 模式固定核对已评估的 5,111 文件完整 inventory digest，未知版本需先重新评估并更新固定值，不静默接受。

HD 模式保持 ReMade 的 `dinput8.dll`，将 FusionFix 自带 UAL 原字节复制为 `dsound.dll`。两份 ASI 保留在 `game/scripts/`；`dsound.ini` 开启诊断日志，未强制 DLL 初始化内加载插件。完整材质真实复制，不使用硬链接或目录联接。原版 EXE/PAK、FusionFix 二进制及输入配置不变；输出配置仅将 `[MAIN] WindowMode` 从 `0` 改为 `2`，固定输出 hash 与 override 记录写入清单。004 起默认无边框，其余设置不变。

包内提供 `TESTING.md`、`package.json`、原安装与高清输入清单、`Disable-Localization.ps1` 和 `Set-HD.ps1`。`game/profiles/` 初始为空；不复制个人存档，但用户目录/注册表隔离仍待实测。手动启动和分层排查见[三合一测试说明](docs/INTEGRATED_TESTING.md)。

### 永远只保留最近两个已完成的测试包

新包完整校验通过后，构建器按递增编号保留最近两个受管包。`tools/package_retention.py` 生成带清单 hash 的计划；`tools/prune_test_packages.ps1` 验证绝对路径位于仓库 `dist/`、无联接、清单和 EXE 身份一致，且副本未被运行，再删除旧包。计划保存在 `build/package-retention/<包名>/retention-plan.json`。

失败/未完成/无法识别的目录、外部输入与研究记录不自动删除。保留规则按全局包编号排序，跨语言也要使用新的编号。旧包的测试存档、配置和日志随包删除，重要反馈应先保存到包外。当前 `dist/` 保留 003、004，早期未编号副本已删除。历史 `build/poc-20261117/runtime` 的清理调用被执行器拦截，目录仍存在，不将它记为已清理；它不属于后续受管发布目录。

`--verify` 只检查清单文件与固定依赖，不运行游戏；手动改配置、禁用模块后会报告差异，不代表实机故障。

### PoC 002 加载器历史证据

以下是当时的回滚流程与留存证据，不代表 001/002 启动成功。001 已按两版保留规则删除；重做该历史实验须自行提供相应基线，而非重新使用已删除目录。003 的历史验证见下文；当前 004 的配置验证见末节。

```powershell
python -X utf8 tools/verify_integration.py prepare --baseline dist/poc-zh-CN-001 --package dist/poc-zh-CN-002 --out build/integration-002
python -X utf8 tools/verify_integration.py evidence --out build/integration-002
```

`prepare` 只可对新的证据目录运行；`evidence` 执行基线/修改检查和 Git Bash 回滚脚本。输出为 `MODIFIED_FILE.json`（002 清单快照）、`DIFF_FILE.json`、`VERIFICATION.txt`、`ROLLBACK.sh`。回滚仅在不含游戏 EXE 的独立 DLL/数据夹具内禁用高清层，保留 FusionFix 与汉化，交付包仍保持三者启用；不把这个文件状态写成已验证的游戏行为。测试包是本地副本，不上传完整游戏或模组资产。

## 中文 PDA 副本回滚证据

以下验证语言包构建时生成的 PDA 离线副本，**不是运行时安装步骤**。每轮使用新的证据目录，`evidence` 会执行基线、修改、另一副本恢复与恢复结果检查：

```powershell
$Evidence = 'build/poc-verification-local'
python -X utf8 tools/verify_poc.py prepare --game-root $Game --locale-build build/locale-zh-CN --out $Evidence
python -X utf8 tools/verify_poc.py evidence --out $Evidence
```

输出 `MODIFIED_FILE.raw`、`DIFF_FILE.json`、`VERIFICATION.txt` 和可执行 `ROLLBACK.sh`。恢复只处理 `ROLLBACK_TEST.raw`，修改产物仍保留。四个变更指针字段为 `0x188C`、`0x1894`、`0x189C`、`0x18A4`；其余原始字节和机器 ID 保持原样。

已有本轮记录位于 `build/poc-verification-20261117/VERIFICATION.txt`，基线/修改/恢复/回滚命令均退出 0。重复执行恢复前需重新准备独立测试副本；不要把已恢复副本误当修改输入。

## 原始资源探针

以下是初始 P4CK/BS 格式实验，与运行时中文 PoC 分开。每次选择新的 `$Out`，避免覆盖既有证据：

```powershell
$Out = 'build/resource-probe-local'
python -X utf8 tools/assess_resources.py inventory $Out --game-root $Game
python -X utf8 tools/assess_resources.py prepare $Out --game-root $Game
python -X utf8 tools/assess_resources.py baseline $Out
python -X utf8 tools/assess_resources.py modified $Out
```

探针读取 `pak/arcade/l_103.pak` 内 `data/strsspxe.bs`，只在隔离副本中把 ID 850 从 `New Game` 改成 `Localization probe`。其余 6,525 个 ID 和 6 个封包成员应保持原样。它验证变长回写和目录，不验证游戏加载重建包。

输出包括 `BASELINE.pak`、`MODIFIED_FILE.pak`、`probe.json`、`DIFF_FILE.json`、`ROLLBACK.sh` 和清点报告，全部留在忽略的 `build/`。`prepare` 拒绝覆盖已有 `probe.json` 的目录。

从修改产物另复制一份，只恢复指定测试副本：

```powershell
Copy-Item -LiteralPath "$Out/MODIFIED_FILE.pak" -Destination "$Out/ROLLBACK_TEST.pak"
python -X utf8 tools/assess_resources.py restore $Out --target "$Out/ROLLBACK_TEST.pak"
python -X utf8 tools/assess_resources.py rollback $Out
```

也可用 Git Bash 执行等价恢复命令：

```bash
bash build/resource-probe-local/ROLLBACK.sh build/resource-probe-local/ROLLBACK_TEST.pak
```

恢复工具校验目标名称、目录和前后 hash。最终恢复测试副本的原字节，同时保留修改产物；这不是任意安装目录的通用覆盖命令。

## 证据与发布

初始评估完成 15 项合成测试、258 个 PAK 的结构检查和资源探针回滚，历史日志在本地 `build/assessment-20261117/VERIFICATION.txt`，摘要见[初始评估](docs/ASSESSMENT_2026-11-17.md)。PoC 001 当时完整测试为 **49 项合成测试通过**；MSVC x86 构建与离线宿主通过，语言包为 32 条 BS、4 条 PDA、92 个字形、6 张图集，PoC 001 的 299 个清单文件校验通过，原安装 305 个文件保持不变。本轮未启动游戏，不把这些结果写成实机验收。

每次构建记录输入/产物 hash、工具版本、修改字段、命令与退出状态。仅提交源码、原创译文和合成测试；不提交原版资产或完整隔离副本。正式发布前还需完成用户验收和[许可检查](LICENSING.md)。

PoC 002 新增分离加载器、完整材质输入身份和最近两版保留流程；003 当时合成测试为 **84 项通过**。三者运行时共存继续由用户验证。

## PoC 003 启动兼容回归

构建额外输出 `SecondSight.Compatibility.asi` 与 `compatibility_host.exe`。打包前校验四处版本指令和 27 条直接签名；UAL 的 `LoadExtraPlugins` 显式先初始化适配器，再运行原 FusionFix，原 EXE 和 FusionFix 磁盘字节不变。该适配与语言数据无关。

```powershell
$Root = (Get-Location).Path
& "$Root/build/runtime/compatibility_host.exe" "$Root/build/runtime/SecondSight.Compatibility.asi"
python -X utf8 tools/startup_compat.py preflight --exe "$Game/secondsight.EXE"
```

原始离线探针应失败（23/27、退出 2），原生适配器处理后的分析图像为 27/27、退出 0；另一副本回滚恢复原始字节与原始缺失签名，回滚命令退出 0。证据位于 `build/startup-003/`；完整方法、地址、用户日志与局限见[启动兼容记录](docs/STARTUP_COMPATIBILITY.md)。这些命令不运行任何游戏指令；003 用户测试后来确认越过加载故障，但在另一处纹理路径退出；当前状态见下一节。

## PoC 004 无边框策略与配置回滚

004 只将输出 FusionFix 配置的 `MAIN.WindowMode` 改为 `2`，不改源码模块或第三方二进制。`tools/fusionfix_config.py` 保留其他字节；清单的 `fusionfix_config` 记录输入/输出 hash 与 override。94 项合成测试通过。

```powershell
python -X utf8 tools/verify_window_mode.py prepare --source FusionFix/scripts/SecondSight.FusionFix.cfg --out build/window-004
python -X utf8 tools/verify_window_mode.py evidence --out build/window-004
```

证据目录需尚不存在；已生成时选新目录。BASELINE 退出 2（仍为独占全屏），MODIFIED/ROLLBACK 退出 0；回滚只恢复独立配置副本，交付包保持无边框。实际失焦与退出原因仍待用户实验，详见[004 记录](docs/STARTUP_004.md)。

## 字体、名词表与标点检查

`locales/<locale>/font.json` 管理字体和许可依赖，`style.json` 管理编辑规则，`glossary.json` 管理术语；译文逐条声明 `text_kind` 和 `terms`。构建器先检查标点/术语，再生成图集，manifest 记录四份编辑输入的 hash；`FONT-NOTICE.txt` 从当前语言字体配置生成，不再共用固定中文通知文件。

```powershell
python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN
python -X utf8 tools/build_locale.py --game-root $Game --locale zh-CN --out build/locale-editorial-005
python -X utf8 tools/verify_poc.py prepare --game-root $Game --locale-build build/locale-editorial-005 --out build/editorial-validation-005
python -X utf8 tools/verify_poc.py evidence --out build/editorial-validation-005
```

证据目录需尚不存在。本轮 104 项测试通过；旧译文夹具触发两条句号错误，修订后检查通过。只生成语言包与回滚证据，不更新用户正在验收的 004，也未另建完整游戏副本。
