# 游戏中语音字幕：原生事件与生命周期接入

## 证据范围

- 目标为 GOG Windows x86 `secondsight.exe`，大小 5484544，SHA-256 `4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda`
- 本文接续 [008 字幕调查](SUBTITLE_008.md)。新目标是给原本没有显示字幕的游戏中语音增加字幕，不以修改原生字幕模式或取得新的进程转储为前提
- 已执行静态反汇编和原生 x86 指令离线回放；未启动、操作或附加游戏，未进行像素、真实音频或实际场景验收
- 本文列出的受控无字幕路径用于建立可复现负对照，不声称还原了用户截图时的全部运行状态
- 本地原生分析文件在 `build/subtitle-009/native/`，不分发反编译全文或游戏原始二进制

## 最小接入点

| 用途 | 地址 | 原字节 | 约定 |
| --- | --- | --- | --- |
| 语音事件观察 | `0x456610` | `85 C0 57 8B FA` | 入口 5 字节为完整无相对指令；`ESI=owner, EDX=event, EAX=callback, ECX=userdata` |
| 游戏内字幕绘制 | `0x63D78A` | `E8 A1 20 00 00` | HUD 对无参数 `0x63F830` 的调用 |
| HUD/关卡字幕重置 | `0x63D494` | `E8 67 21 00 00` | 初始化对无参数 `0x63F600` 的调用；静态交叉引用只有这一处 |

事件 hook 必须保存寄存器和标志，随后执行原 trampoline；原入口 `test eax,eax` 的结果供 `0x456615` 的条件分支使用。原 callback 以 cdecl `(owner,event,userdata)` 调用，不得遗漏或重复调用。

不只 hook `0x45668F -> 0x63F6A0`：那条原生字幕选择调用已经经过 owner flags 的过滤，观察它仍然会漏掉需要补字幕的语音。原生选择器实际有七个参数 `(bsId,owner,color,resolvedSpeaker,priority,displayGate,name)`，不能使用反编译器在自定义寄存器上下文中推断出的单参数调用。

## 事件语义

| event | 已确认的含义 | 新字幕处理 |
| --- | --- | --- |
| 0 | 排队项等待，尚未消费 | 不触发字幕 |
| 1 | `0x456D00` 已填写 active owner，`0x4566A0` 将消费队列头 | 可清掉同 owner 的旧状态；不能假设音频已可播放 |
| 2 | 活动语音更新，由 `0x457181` 或 `0x4571C2` 调用 | 检查 active BS/handle 及音频 ready 后建立或更新 cue，同 owner/BS/handle 去重 |
| 3 | 自然结束，经 `0x4566C0` | 清除该 owner 的 cue |
| 4 | 主动停止/owner 清理，经 `0x4566C0` | 清除该 owner 的 cue |
| 5 | 丢弃排队项，经 `0x4566A0` | 不是当前活动语音结束，不能直接清除活动 cue |
| 6 | 请求被 actor 条件过滤，`0x456970` 分发 | 未建立新活动语音；不能当作开始或结束 |

`0x4566C0` 先调用 `0x63F810(owner)` 脱离原生选中字幕，然后分发 event 3/4，再清零 owner 的 BS、duration、callback，并将 audio handle 设为 -1。因此观察 event 3/4 时字段仍属于结束的那一句。

### owner 字段

| 偏移 | 类型/含义 |
| --- | --- |
| `+0x00` | 排队项头指针 |
| `+0x04` | 有符号音频 handle，-1 表示无 handle |
| `+0x08` | 当前 BS 文本 ID |
| `+0x0C` | 文字颜色 |
| `+0x10` | 原生优先级 |
| `+0x14` | 说话人名称 BS ID |
| `+0x18` | 剩余估算时长，float |
| `+0x20` | actor/property handle |
| `+0x30/+0x34` | callback userdata / callback |
| `+0x38` | 原生进度/淡入淡出标量，float |
| `+0x44` | 附带动画等资源 handle |
| `+0x48` | 原生 flags；掩码 `0x04` 表示字幕选择已处理，掩码 `0x08` 传给显示门控 |

渲染时不再解引用 owner。cue 保存 owner 数值作为身份键，并复制已验证 BS 目标文本、audio handle、priority；所有终止由事件驱动，场景初始化统一清除 cue。原生估算时长不是新增字幕的固定倒计时触发器。

## 时序、音频与暂停

- `0x457030(owner,actorOr0)` 在 `0x8BB378==0` 时跳过全部更新，包括事件和 duration 变化
- 原生 duration 每次减去 `float[0x8BB380] * float[0x7CCE00]`，后一个常量实值为 `0.01666666753590107`，即约 1/60；不是按墙钟计算
- `0x60D8F0(handle)` 是 ready 状态边界；音频请求尚未就绪时返回零
- `0x60D930(handle)` 是活动状态边界；duration 已到但音频仍活动时，`0x4571C2` 仍分发 event 2，实际结束后才分发 event 3
- 新增字幕不应仅以估算时长截断正在播放的语音，也不应在暂停期间用墙钟到期

## 绘制条件与去重

HUD 调用点原本要求 `0x964FCC==0`、`0x8BB378!=0`、`0x8AA0E8!=0`。用户字幕开关是 `0x50BD60()` 返回的 `0x91C88C`，过场和原生游戏中字幕都使用它，新增字幕必须尊重此开关。

`0x61DD90()` 返回 `0xA0A704!=0`。该状态参与序列跳过/淡出（`0x61EC70`）、序列声音清理与终止（`0x620750`、`0x626CF0`），原生字幕绘制也据此改变布局。它仅证明脚本序列正在活动，尚不足以证明全部此类序列都是电影过场；原生 `0x63F830` 在该状态下仍绘制字幕，所以新增功能不将它作为无条件抑制门控。`0x964B20` 当前仅查到两个读引用，语义不足，不单独将其命名为过场状态。

新增字幕与原生字幕应在同一 HUD 接入处仲裁：同 BS 已被原生显示时只绘制一次。跨 timed 字幕路径的去重应依赖实际字幕绘制事件或原生 HUD 分流，而不是脚本序列状态或字幕资源总数；原本无字幕的脚本对白仍应显示。多说话人保存有限数量仍活动的 cue，以优先级与稳定顺序选择当前项；高优先级结束后只恢复仍在播放的候选，不重播已经结束的文本。无 BS、未找到验证译文或已失效音频均不凭空生成字幕。

本轮否定了早期候选中“`A0A704!=0` 就全部 fallback 原生字幕”的设计。该判断会让原生 display gate 为零的脚本对白重新变成无字幕；最终候选移除此额外门控。原生 `0x638200` 在 `0xA2BD34==3` 时不进入该 HUD 路径；另一 timed 路径则查询 `0x584EC0()` 返回对象的当前时间，再比较 `0x95BFA4` 表中每项的起点与时长。离线证据只确认 HUD 同路径的单路绘制，尚未证明两套路径在所有游戏场景绝不重叠。

## 可复现的原生负对照

```powershell
python tools/replay_gameplay_caption_events.py --exe build/subtitle-008/native/BASELINE.exe --out build/subtitle-009/native/lifecycle-baseline.json
python tools/replay_gameplay_caption_events.py --exe build/subtitle-008/native/BASELINE.exe --out build/subtitle-009/native/lifecycle-red.json --require-added-captions
```

第一条实际输出：`PASS: native lifecycle 7/7; native silent-caption draw counts=0,0`，退出码 0。

第二条要求负对照具备新增字幕，实际输出：`FAIL: native lifecycle 7/7; native silent-caption draw counts=0,0`，退出码 1。

回放运行真实 `0x457030` 更新、`0x456610` 分发、`0x4566C0` 结束、`0x456730` 取消/停止、`0x63F600` 重置及原生 HUD 字幕调用。受控边界为音频设备 ready/active、空间音量/距离、GPU 提交和合成 owner/BS 表，未替换事件决策或字幕选择代码。覆盖以下七项：

1. 音频 ready/active 且 flags=0，收到 event 2，原生选中 BS 但 display gate 为零，无绘制
2. 音频 ready/active 且 flags=4，收到 event 2，但原生跳过选择，无绘制
3. 连续 event 2、估算 duration 已到但声音仍活动、声音结束后的 event 3 和 owner 清理
4. tick=0 时不更新、无事件且 owner 不变
5. 取消排队项 event 5 后主动停止活动项 event 4
6. 音频尚未 ready 时不选择原生字幕
7. 原生 HUD 重置清除选中字幕与 owner

## 剩余验收边界

- 离线绿色结果须实际执行编译后的新增 event/render/reset shim，而不是只验证一个 Python 模拟状态机
- 真实音频时序、场景/死亡/读档切换、同屏多个说话人、用户开关、过场与 gameplay 交接、不同分辨率下文字显示仍须用户游戏内验收
- BS 为零或资源内原本没有台词文本的音频不属于既有 BS 映射；需单独建立音频清单、文本来源和审校，不能用邻近字幕猜词

## 新增模块的编译产物闭环

生产候选 `build/gameplay-captions/runtime-final/SecondSight.Localization.asi` 与同目录 MAP 在相同原生输入上进行了红—绿—回滚回放：

- ASI SHA-256：`9205468bbd1d5a91427837dd3c9142ae74fd1bc44d778f014d57440565ba54f4`
- MAP SHA-256：`8cecf87c3abae1eeac913edde328ba4ab17b2b524d213a43e9a414012b401e25`

```powershell
python tools/replay_gameplay_caption_events.py --exe build/subtitle-008/native/BASELINE.exe --library build/gameplay-captions/runtime-final/SecondSight.Localization.asi --map build/gameplay-captions/runtime-final/SecondSight.Localization.map --baseline-with-library --require-added-captions --out build/gameplay-captions/events-baseline.json
python tools/replay_gameplay_caption_events.py --exe build/subtitle-008/native/BASELINE.exe --library build/gameplay-captions/runtime-final/SecondSight.Localization.asi --map build/gameplay-captions/runtime-final/SecondSight.Localization.map --require-added-captions --out build/gameplay-captions/events-modified.json
python tools/replay_gameplay_caption_events.py --exe build/subtitle-008/native/BASELINE.exe --library build/gameplay-captions/runtime-final/SecondSight.Localization.asi --map build/gameplay-captions/runtime-final/SecondSight.Localization.map --rollback --require-added-captions --out build/gameplay-captions/events-rollback.json
```

| 输入模式 | 实际字面输出 | 退出码 |
| --- | --- | --- |
| BASELINE | `FAIL: native lifecycle 11/11; native silent-caption draw counts=0,0; compiled added-caption draw counts=0,0` | 1，新增字幕要求未满足，预期红灯 |
| MODIFIED | `PASS: native lifecycle 33/33; native silent-caption draw counts=0,0; compiled added-caption draw counts=1,1` | 0 |
| ROLLBACK | `FAIL: native lifecycle 11/11; native silent-caption draw counts=0,0; compiled added-caption draw counts=0,0` | 1，恢复原生无新增字幕状态，预期红灯 |

`--rollback` 在独立 Unicorn 映射副本先安装三处新分支，再恢复并逐字节核对原始三处字节。生产 ASI 文件保持修改状态。baseline 和 rollback 都保留生产文本换行 hook，从而隔离新增字幕这一变量。

绿色回放实际执行编译后的 `GameplayCaptionEventHook`、`GameplayCaptionObserve`、`GameplayCaptionDrawHook`、`GameplayCaptionResetHook`、状态仲裁、真实生产 `wrapHook`/初始化器以及原生测量函数；不以 Python 状态机代替它们。`GameplayCaptionLookup` 的返回值作为具名合成 BS/locale 输入边界，音频设备、分配/释放、GPU 提交同样是明确的边界，因此这里不声称验证了实际资源加载、音频驱动或屏幕像素。

新增覆盖包括：有/无 callback 时完整寄存器和 EFLAGS 与原版一致；ready 过渡和重复事件去重；估算 duration 结束后仍随真实 active 状态继续；event 1/3/4 清理；event 0/5/6 不误杀；暂停恢复；多个说话人优先级与活动候选恢复；字幕开关；脚本序列状态不误拦截语音；场景重置；缺失文本/无效 handle；原生字幕 fallback；相同 BS 不重复绘制；owner 页变为不可读后仍正常绘制；640×480、1920×1080、2880×1800、3840×2160 的完整换行和布局边界。
