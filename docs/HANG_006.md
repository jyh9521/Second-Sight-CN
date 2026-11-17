# 006 加载等待：历史报告与更正

2026-11-17 用户最初报告006停在加载状态、无响应，随后明确更正：游戏没有卡住，等待加载后可以进入。当前报告转为汉字错乱，见[007修复记录](GLYPH_FIX_007.md)。以下事件、转储和旧排查路线保留为历史证据，不再要求采集新的前台转储，也不据历史Application Hang事件认定持续死锁。

## 已观察

- Windows Application事件1002，记录号63268，发生于本机14:43:43（UTC+9），明确指向006的游戏EXE；同时有AppHangB1报告
- Compatibility、FusionFix、本地化模块均有加载记录；本地化日志显示六次字库读取和字体模式初始化
- BS日志重复出现 `substituted=5867 expected-direct=5938 deferred=19`；71条差额是待解释现象，不据此直接认定挂起原因
- EXE、本地化ASI、语言包、FusionFix、Compatibility、高清代理和UAL共7项hash仍与006交付清单一致
- 006无新崩溃转储，当前发现的5个CrashDumps文件均早于此次006运行；没有把003的旧访问异常当成新挂起根因
- 检查时游戏进程已结束。自动化未启动、关闭、重启或附加游戏，也未改动006

## 14:59 转储：已收到并离线读取

用户提供`secondsight.DMP`，304,925,013字节，SHA-256为`d8d542b1331ce2469530a45040a38daa7186417661bc2691d6ddb4571ef04e3c`。模块路径明确指向006，三个模组均存在。读取到17个线程、647个内存区间；没有ExceptionStream，这是手动状态快照，不是异常崩溃记录。

### 已观察：采样时主循环暂停等待

- 主线程ID4252，WOW64上下文位于`0xAF544`，EIP在`ntdll!ZwDelayExecution+0xC`
- 有效栈段为`SleepEx → Sleep → secondsight.EXE+0x246592`。帧循环`0x646550`中的调用点`0x64658E`记录字节为`6A 64 FF D5`，参数100毫秒；未停在汉化函数内
- 状态对象`0x9FE900`的`+0x1EA=0`、`+0x1EC=1`、`+0x1F0=1`、`+0x1F4=1`、`+0x1F8=0`。`0x643FF0`读取`+0x1F0`并判断是否大于0，该分支解释这次休眠
- FusionFix仍配置`WindowMode=2`、`PauseOnFocusLoss=1`；**用户明确确认采集时已切到任务管理器，游戏在后台**

推断：这次采样符合切后台后的暂停，不能据此解释前台加载故障，也不能排除任何模组。优化代码把EBP用作普通寄存器，简单EBP链在Sleep返回后失效；不将栈内任意模块地址当成完整调用栈。

### 已验证的独立缺陷：英／美源文变体导致71条未绑定

转储语言索引`*(int*)0x875E80=1`，后缀表`0x875EB0`选择`nxa.bs`，实际加载`data/strssnxa.bs`。006构建却只核对英式`data/strsspxe.bs`。

美式资源SHA-256为`78e8e6959c3bdfa193985301602fbe37f6eb6f09b4d4846a16439f208f441230`，转储原始字符串池完整211281字节与它一致。5957条记录为5867条译文完全相等、71条美式原文未绑定、19条预期延迟项。71条内存保护与边界检查均通过，失败条件只有源文内容不等。

英／美资源共73条差异，另外两条为延迟项314、3647；3647还会使五段组合终端的严格源文比较失败。007已为已校验的英／美源文建立显式变体契约，共用译文，覆盖直接、延迟和组合消费者；不模糊匹配或强改游戏语言配置。**这是漏绑定缺陷，尚无证据将其归因为加载挂起，006运行文件保持原样。**

## 转储工具与历史采集方案（本次不再需要）

读取器新增可选异常流、ThreadList、x86/AMD64上下文。`--wow64`显式选择AMD64 TEB TLS[1]+4恢复方式，参照[Microsoft布局说明](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-wow64_context)及[LLDB对应方法](https://lldb.llvm.org/cpp_reference/MinidumpParser_8cpp_source.html)。布局保留版本敏感性；缺失内存或未知上下文标记保持unknown。

```powershell
python -X utf8 tools/minidump_reader.py --dump "$env:LOCALAPPDATA/Temp/secondsight.DMP" --wow64 --out build/hang-006-20261117/dump-analysis/threads.json
```

旧读取器在这份转储上`KeyError: 6`、退出1；新读取器输出`RECORDED DUMP: exception=absent; threads=17; x86_contexts=17; memory_ranges=647; no target execution`、退出0。独立副本回滚恢复原错误和退出1，修改产物保留。**这是读取器回归，不是游戏挂起修复。**

以下是用户更正前准备的方案；本次不执行，也不要求用户执行。`tools/collect_hang_dump.ps1`供用户手动执行：精确选择已运行的一个EXE路径，等待连续前台8秒，采两份快照、相隔至少5秒，记录采集前后是否仍在前台。不启动、退出、调试附加或激活窗口；输出目录及文件必须不存在。调用[MiniDumpWriteDump](https://learn.microsoft.com/windows/win32/api/minidumpapiset/nf-minidumpapiset-minidumpwritedump)时使用查询/读取权限。采集本身可能短暂停顿，勿将其当作原故障。

```powershell
# 仅由用户执行；OutputDirectory须不存在
powershell -NoProfile -ExecutionPolicy Bypass -File tools/collect_hang_dump.ps1 -ExpectedExecutable "$PWD/dist/poc-zh-CN-006/game/secondsight.EXE" -OutputDirectory "$PWD/build/hang-006-foreground"
```

自动化仅运行`-SelfTest`编译声明与检查路径，未执行采集分支。该轮没有针对前台故障的红/绿证据，所以当时没有制作猜测性修复。后续007针对的是截图错字，已有独立原生指令红/绿回放；不是“挂起修复”。

本地证据在`build/hang-006-20261117/`：原事件和日志保留；`dump-analysis/`保存线程、原始字段与读取器BASELINE/MODIFIED/ROLLBACK证据；`dump-analysis-bs/`保存可复现比对脚本和逐条hash。原DMP保留用户给定位置，仅计算hash与读取，不复制或上传。
