# 006 加载挂起：用户反馈与证据

2026-11-17 用户报告006打开后一直停在加载状态、无响应。该报告是运行时失败，不能用先前离线测试通过替代。

## 已观察

- Windows Application事件1002，记录号63268，发生于本机14:43:43（UTC+9），明确指向006的游戏EXE；同时有AppHangB1报告
- Compatibility、FusionFix、本地化模块均有加载记录；本地化日志显示六次字库读取和字体模式初始化
- BS日志重复出现 `substituted=5867 expected-direct=5938 deferred=19`；71条差额是待解释现象，不据此直接认定挂起原因
- EXE、本地化ASI、语言包、FusionFix、Compatibility、高清代理和UAL共7项hash仍与006交付清单一致
- 006无新崩溃转储，当前发现的5个CrashDumps文件均早于此次006运行；没有把003的旧访问异常当成新挂起根因
- 检查时游戏进程已结束。自动化未启动、关闭、重启或附加游戏，也未改动006

## 当前结论与下一步

已确认加载阶段挂起，根因尚未建立。缺少挂起时的线程堆栈，因此当前没有能针对该挂起红/绿切换的离线复现入口，也没有宣布修复。保留现有包，不通过更换模组、删减全量译文或改窗口模式试猜。

请用户在其手动运行再次卡住时，仅对 `secondsight.EXE` 创建用户态内存转储，并提供本地路径。任务管理器的“详细信息”页右键目标进程，选择“创建内存转储文件”；参照[Microsoft操作说明](https://learn.microsoft.com/en-us/troubleshoot/windows-server/support-tools/support-tools-task-manager)。无需系统内核转储，也无需上传文件至GitHub。

本地证据在 `build/hang-006-20261117/`：3份日志快照、ApplicationHang事件XML、`diagnosis.json`（输入hash、事实与未决项）。这些文件只留在忽略目录。收到转储后先读取所有线程与模块身份，再建立针对已定位路径的复现和回归；不将日志计数或一般宿主测试冒称挂起已修复。
