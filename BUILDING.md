# 构建与离线验证

当前中文样本、独立 x86 ASI、离线宿主和 **PoC 001 本地测试包已完成离线构建与检查**；游戏内显示与 FusionFix 共存均待用户验收。**以下自动化只处理文件或运行自有测试宿主，不启动游戏。**

## 环境与输入

- Windows、Python；初始资源实验使用 Python 3.14.2。
- [requirements.txt](requirements.txt)固定 Pillow、fonttools、pefile 与 capstone 版本。
- Visual Studio / Build Tools 的 MSVC x86/x64 C++ 工具及 Windows SDK。构建脚本通过 `vswhere` 定位工具链，生成 x86 产物。
- 原版 GOG PC 游戏文件，版本与 SHA-256 见[技术说明](TECHNICAL.md)。
- 用户提供的固定版本 `FusionFix/`，供后续隔离副本联合测试；该目录不纳入 Git。
- 首次语言包构建需要下载固定提交的 Noto 字体与 OFL；后续使用经过 hash 校验的本地缓存。

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

构建器校验 EXE、主文本和找到的全部 `pdaps_a.raw` 副本的 hash，逐条核对原文；不接受未知版本或原文不符的数据。字体使用固定提交与 SHA-256，字形由样本文本确定；当前六页分配跳过原引擎特殊编号 178、184，共 1,534 个候选字位，不代表完整汉化容量已解决。编码后 BS 上限为 255 字节、PDA 上限为 450 字节；这些保守护栏不是游戏布局验收。

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

## 隔离测试副本

`tools/stage_poc.py` 会重新构建语言包与 ASI、运行离线宿主，再复制指定游戏目录和固定 FusionFix 到新目录；不会启动游戏。它拒绝已存在的输出或与原游戏重叠的目录，校验复制前后原安装的文件清单/hash。

```powershell
python -X utf8 tools/stage_poc.py --game-root $Game --fusionfix-root FusionFix --out dist/poc-zh-CN-001
python -X utf8 tools/stage_poc.py --verify --out dist/poc-zh-CN-001
```

输出含 `game/`、`TESTING.md`、`package.json`、`source-inventory.json` 和 `Disable-Localization.ps1`。`game/profiles/` 初始为空，不复制原存档；`game/scripts/` 保留固定 FusionFix 并放入独立本地化 ASI。运行时语言包位于 `game/scripts/localization/`。

本轮输出为 `dist/poc-zh-CN-001`；该目录已存在时，重建请另选新名称，不覆盖已交付副本。

`--verify` 校验打包清单中的文件、EXE 与 FusionFix，不启动游戏，也不表示游戏已经加载这些文件。请在手动测试前执行；修改配置或禁用模块后，原始包清单不再代表当前文件状态。具体包是否已完成本轮校验，以验证日志为准。

用户手动退出测试游戏后，可只禁用汉化模块，保留 FusionFix：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File dist/poc-zh-CN-001/Disable-Localization.ps1
```

脚本校验 ASI hash 后改名为 `.asi.disabled`，不启停进程。禁用后不是恢复纯 GOG 安装，而是保留 FusionFix 的无汉化测试副本；原安装始终未由本流程改动。

用户手动验收步骤和需保留的证据见[PoC 测试说明](docs/POC_TESTING.md)。完整隔离副本只供本地测试，不提交 Git、不作为可下载游戏包发布。

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

初始评估完成 15 项合成测试、258 个 PAK 的结构检查和资源探针回滚，历史日志在本地 `build/assessment-20261117/VERIFICATION.txt`，摘要见[初始评估](docs/ASSESSMENT_2026-11-17.md)。本轮完整测试为 **49 项合成测试通过**；MSVC x86 构建与离线宿主通过，语言包为 32 条 BS、4 条 PDA、92 个字形、6 张图集，PoC 001 的 299 个清单文件校验通过，原安装 305 个文件保持不变。本轮未启动游戏，不把这些结果写成实机验收。

每次构建记录输入/产物 hash、工具版本、修改字段、命令与退出状态。仅提交源码、原创译文和合成测试；不提交原版资产或完整隔离副本。正式发布前还需完成用户验收和[许可检查](LICENSING.md)。
