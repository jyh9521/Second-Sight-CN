# ReMade 高清材质包：上游与加载方案依据

核查日期：2026-11-17。本记录只核查作者公开资料和 UAL 官方说明；没有启动游戏、加载模组 DLL、安装材质或修改用户提供的文件。具体本地文件身份及冲突由同轮离线评估补充。

## 1. 项目与版本

对应项目是 Tobit2o-Tobsick 发布的 [Second Sight Remastered Mod（Nexus mods/2）](https://www.nexusmods.com/secondsight/mods/2?tab=description)，不是同作者另一个 ReShade 调色预设。当前作者页标题为 V1.2，版本字段为 **1.2.1**，最后更新为 **2026-11-01**；更新说明由作者宣称修复部分崩溃并完成约 97% 材质。这些是上游声明，不是本项目实测覆盖率或稳定性结论。

作者下载项 [ReMade with Second Sight Remastered Textures](https://www.nexusmods.com/secondsight/mods/2?tab=files) 的名称，与用户目录名称对应；其说明要求 `Remaster_Textures` 与 `dinput8.dll`、游戏 EXE 同级。读取到的文件页缓存仍显示 2026-08-09 的 v1、3.1 GB，以及单独 DLL 下载项 0.1.0 / 606 KB。因此：**页面版本、下载项版本和本地 DLL 版本应分别记录；目录名或约 606 KB 大小不构成二进制版本证明。**

本轮网页读取曾同时返回旧 Beta 页面与新页面。通过当前[评论页](https://www.nexusmods.com/secondsight/mods/2?tab=posts)进入作者说明后取得新版本内容；[更新日志页](https://www.nexusmods.com/secondsight/mods/2?tab=logs)也显示 1.2.1。不要继续引用旧搜索摘要为“最新版本”。

作者在 Nexus 链接到其 [itch.io 项目](https://benedictbutnotpapst.itch.io/second-sight-remastered-mod-v10)。该页说明 ReMade 用于 D3D9 运行时纹理提取与替换，并将大体积材质下载指回 Nexus；本轮取得的 itch 缓存标题仍为 V1.0，不用于推翻 Nexus 当前版本字段。

## 2. 作者说明确立的边界

作者描述的是 **D3D9 运行时纹理替换器 + 材质目录**，不是直接重打原 PAK。作者也指出频繁切换替换材质可能触发崩溃。ImageMagick、放大工具和纹理工具是制作材质的依赖，不是玩家使用现成包的必需项。[作者说明](https://www.nexusmods.com/secondsight/mods/2?tab=description)

在本轮取得的作者说明、评论、更新日志、下载项说明及其链接的 itch 页面中，没有找到以下保证：

- 与 Second Sight FusionFix 的特定版本共存；
- ReMade 自身会扫描并加载 `.asi`；
- 把其 DLL 改名为 `.asi` 即可正常初始化；
- 对 UAL `dinput8Hooked.dll` 链载布局的专项支持；
- ReMade 原生 DLL 的公开源码仓库。

“没有找到”仅限本轮这些资料和针对 `Tobit2o / Tobsick / ReMade / Remaster_Textures` 的搜索，不等于证明源码或其他说明从未存在。作者的 GUI PowerShell 工具也不等于 ReMade 原生 DLL 源码。

## 3. UAL 10.0.2 提供的候选机制

与当前测试包版本相符的 [Ultimate ASI Loader v10.0.2 官方 README](https://github.com/ThirteenAG/Ultimate-ASI-Loader/blob/v10.0.2/readme.md)明确记载：

- 可通过 `<dllname>Hooked.dll` 加载原 DLL；对于当前代理名称，候选名称为 `dinput8Hooked.dll`。
- ASI 可以放在游戏根目录或 `scripts`、`plugins`、`update`；加载器使用 `LoadLibrary`，随后调用导出的 `InitializeASI`。
- 插件初始化时机和 DLL 入口限制仍然重要；改扩展名不会自动修正插件自己的初始化设计。

由此得到的是**待验证的布局候选**，而非已验证安装方案：

```text
游戏目录/
  dinput8.dll                   # 保留当前 UAL 10.0.2
  dinput8Hooked.dll             # 候选：用户提供的 ReMade DLL 副本
  Remaster_Textures/            # 用户提供的材质
  scripts/
    SecondSight.FusionFix.asi   # 保留当前 FusionFix
    SecondSight.Localization.asi
```

这个方案保留 UAL 对 FusionFix 与汉化模块的加载职责，避免直接覆盖现有代理。但 UAL 的通用链载能力**不证明** ReMade 在此布局中可用；还需离线确认 ReMade 的导出转发、系统 DLL 查找、初始化触发和路径计算，以及与 FusionFix 的 D3D9 钩子顺序。最终由用户手动检查显示、设备重置和关卡切换。

不把“DLL 可以使用 `.asi` 扩展名”推导成“任意 DLL 改名后均适配”。若本地 ReMade 的静态证据更适合独立 ASI 方式，再单独记录其依据与测试状态。

## 4. 仓库与后续验收

作者当前页面对重新上传、修改、资产使用及衍生版本分别列出许可条件。因此当前工程宜保持“**用户自行提供高清包，本仓库只保存兼容工具和元数据**”，不要把第三方 DLL 或全套 DDS 随 GitHub 源码/Release 一并发布。[作者许可字段](https://www.nexusmods.com/secondsight/mods/2?tab=description)

下一轮应先保留“FusionFix + 中文 PoC”基线，再对独立副本评估加入 ReMade 后的变化：中文图集是否被识别为替换目标、英文 UI 是否受材质影响、菜单与字幕/PDA、切关及设备重置。静态避开同名文件冲突只是第一步，运行时共存继续标记为待用户验收。
