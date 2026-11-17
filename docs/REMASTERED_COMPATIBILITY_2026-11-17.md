# ReMade 高清材质包兼容性评估

日期：2026-11-17。对象为用户提供的 `ReMade With Second Sight Remastered Textures/`。本轮仅读取文件、解码图片和静态分析 DLL；没有启动游戏、执行材质 DLL、安装材质，原安装和 PoC 001 未被改写。

## 结论

**可以考虑兼容，建议作为可选高清层；不直接覆盖当前测试包，也不作为中文汉化的基础依赖。**

它不是简单的 PAK 材质覆盖包，而是 **ReMade D3D9 纹理拦截器 + 按内容 hash 命名的 DDS**。与 BS/PDA 译文的数据层没有文件覆盖，但代理 DLL、D3D9 钩子、字体纹理和缓存存在需要单独验证的交叉点。

| 项目 | 结论 | 证据等级 |
|---|---|---|
| 文件完整性 | 5,110 张 DDS 的结构、mipmap 载荷长度及 Pillow 像素解码全部通过 | 已验证：离线 |
| 直接覆盖安装 | 会替换当前 UAL `dinput8.dll`；本地 ReMade 没有发现 ASI 扫描器 | 已验证：文件身份；静态初始化分析 |
| 与中文文本数据 | 包内没有 EXE、PAK、BS 或 PDA RAW 替换 | 已验证：完整目录清点 |
| 与中文字库 | 仍需实测；按纹理内容识别，使用独立资源名并不自动隔离 | 静态机制 + 待验收 |
| 与 FusionFix | 同时接触 Direct3D 创建、Present、Reset、输入/光标等路径 | 静态交叉点，运行时共存待验收 |
| 体积与稳定性 | 108 张 8K 资源及长期替换缓存值得优先排查 | 文件事实 + 静态风险，不是崩溃实测 |

## 1. 本地输入身份

| 项目 | 结果 |
|---|---|
| 文件数 | 5,111：1 个 DLL + 5,110 个 DDS |
| 总大小 | 8,266,671,416 字节，约 7.70 GiB |
| DLL | x86，620,544 字节；只导出 `DirectInput8Create` |
| DLL SHA-256 | `8aa884f7a6f4a4fa5294f457c0480149dc684479c9adbd8617c14c539d47f947` |
| DLL 版本资源 | 无 `RT_VERSION`；REA 只发现一个 manifest 资源 |
| DDS 格式 | 4,993 个 DXT5，117 个 DXT1 |
| DDS 命名 | 全部符合 `Remaster_Textures/tex_XXXXXXXX.dds` |
| 完整性 | 5,110 个全部解码；全部 mip 载荷长度吻合，零尾随字节 |
| 不同 DDS 内容 | 4,968 份 SHA-256；相同内容的不同 hash 文件名不自动删除 |
| 清单摘要 | `2ee7e2b39b9e56f3c55ab396157775f18bb5adbd411aab983a654d235281da5a` |

REA 静态资源证据：`ev_20cb533200bc0926de7395cc3a2f0b75d2cbaa31ff45d80f328f6f511c1b26a9`。导入表显示 `d3dx9_43.dll`、`XINPUT1_3.dll`；本机 `SysWOW64` 下两文件存在，版本分别为 `9.29.952.3111`、`9.18.944.0000`。文件存在不替代实际模块加载测试。

作者当前页面与本地二进制版本不可混为一谈；上游页面有缓存差异，详见[上游资料](research/REMASTERED_UPSTREAM.md)。本报告只对上述 SHA-256 对应输入负责。

## 2. 加载器冲突与候选布局

PoC 001 根目录的 `dinput8.dll` 是 UAL 10.0.2（SHA-256 `63b465dbc1bf9c5ab4e33c3ccad099d9edb702f2c51587ac8d4f196497396437`），负责加载 FusionFix 和汉化 ASI。ReMade 的同名 DLL 是另一套实现，直接复制覆盖会移除这条现有加载入口。

候选方案优先保留 UAL，研究其官方的 `dinput8Hooked.dll` 链载；其次再考虑将 ReMade 副本作为独立 ASI。本地 ReMade 在 `DllMain` 的进程附加阶段开始初始化，转发输入时使用系统目录里的真正 `dinput8.dll`，所以两种方案都有进一步验证价值；**尚未安装或证明任一种布局可共存**。UAL 的机制依据见[固定 v10.0.2 官方说明](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/readme.md)。

拟议测试布局（不是当前 PoC 001 的实际内容）：

```text
game/
  dinput8.dll                   # 仍为 UAL
  dinput8Hooked.dll             # 待验证：ReMade 副本
  Remaster_Textures/            # 用户提供
  scripts/
    SecondSight.FusionFix.asi
    SecondSight.Localization.asi
```

ReMade 用当前工作目录相对路径寻找 `Remaster_Textures/`，不是按 DLL 自身目录定位。后续用户启动测试副本时需明确工作目录。其初始化含控制台申请；显示行为仍待观察。

## 3. 与中文菜单、字幕和 PDA 的关系

本包没有改写 BS/PDA/游戏 EXE，当前汉化的指针替换方式可以保持独立。但 ReMade 拦截 stage 0 的二维纹理，筛选没有明确排除 render-target 纹理，也不按 `textures/localization/` 路径隔离中文字库。

纹理键来自 **D3DX 将纹理序列化成 PNG 后，对整个 PNG buffer 做 32 位 FNV-1a**；不是原始 DDS 的 CRC32，也不是文件路径 hash。DLL 内算法常量为初值 `0x811C9DC5`、乘数 `0x01000193`。因此：

- 本轮没有声称“六页中文字库与高清目录零 hash 冲突”。
- 原 DDS SHA、Pillow 输出的 PNG hash，都不能替代 D3DX 实际序列化结果。
- 需要用户截图确认中文/英文/数字/按键图标、字幕和 PDA，不能只检查菜单标题。

详细地址、初始化及图形钩子见[本地 DLL 静态研究](research/REMASTERED_LOADER.md)。FusionFix 的共享图形状态和消息处理也要一并检查，避免只解决同名文件就宣告兼容。

## 4. 8K 资源与内存

108 张 `8192×8192` 资源共 **5,905,595,616 字节（约 5.50 GiB），占整个包 71.44%**；其中 84 张 DXT1、24 张 DXT5。单张完整 mip 链压缩载荷约为 42.67 MiB / 85.33 MiB；解码到 RGBA 的顶层图像为 256 MiB。这些是文件/格式计算，不是实际显存监测结果，亦不表示所有图像同时驻留。

本轮视觉抽样的前八张 8K 图中，多张呈现带黑边的完整游戏场景，还有大面积透明图。它们可能是缩略图、界面画面或渲染结果；用途尚未与原资源映射，不能直接认定全部无用，也不能把它们一概当作高细节场景表面材质。后续值得先确认用途，再考虑 2K/4K 可选档或排除不必要的替换。

当前固定 GOG EXE 的 PE `Characteristics=0x010E`，未设置 `LARGE_ADDRESS_AWARE`。微软记录的相应 32 位进程用户地址空间上限为 2 GB；这与显存是不同概念。[微软内存限制文档](https://learn.microsoft.com/en-us/windows/win32/memory/memory-limits-for-windows-releases)

静态分析还发现：每帧可见原纹理集合会释放，但“原纹理指针 → 替换纹理”缓存及已处理集合长期保存；已追踪到的显式清空在覆盖层的 `Reload All Replacements` 路径，Reset 路径没有清理同一缓存。因此存在跨场景累积、地址复用/陈旧映射的待测风险，**不将它写成已经观察到内存泄漏或崩溃**。

本轮不修改 LAA。顺手应用所谓 4GB 补丁会改变 EXE hash，当前汉化模块会按设计拒绝未知身份；如后续确有需求，应另建版本配置和验证流程，而不是删掉 hash 检查。

## 5. 后续顺序

1. 先由用户完成现有“FusionFix + 中文 PoC 001”的三类界面测试，保留基线。
2. 再准备另一个可回滚副本，优先验证 UAL 链载，不覆盖已交付基线。
3. 先对比启动、输入/光标、中文与未翻译字体；再测切关、读档、窗口/全屏切换、长时间内存趋势。
4. 最后判断原包、筛选包或降分辨率可选档。当前不预先承诺所有 5,110 张均应保留或默认启用。

本地 DLL 中 `Insert` 对应覆盖层开关、`Home` 对应替换开关；这些是静态键值，不是本轮已经操作过的功能。作者提示频繁切换可能崩溃，首轮优先按整次运行比较，不把反复开关当作稳定性验证捷径。[作者说明](https://www.nexusmods.com/secondsight/mods/2?tab=description)

## 6. 复现与仓库状态

```powershell
python -X utf8 tools/assess_texture_pack.py --pack-root 'ReMade With Second Sight Remastered Textures' --out build/remastered-assessment-local --decode
python -X utf8 -m unittest discover -s tests -v
```

本轮结果：`TEXTURE PACK PASS: files=5111; DDS=5110; bytes=8266671416; decoded=True; errors=0; no game launched`；共 56 项合成测试通过。完整清单、DDS 元数据、视觉抽样和静态摘录在忽略目录 `build/remastered-assessment-20261117/`。

用户材质目录已加入 `.gitignore`。只提交评估、检查工具与合成测试，不上传第三方 DLL/DDS。原材质包、原安装和 PoC 001 保留现状；本轮没有建立联合运行通过结论。
