# 许可与分发边界

本项目提供独立编写的本地化工具、技术说明和原创译文，不拥有《Second Sight》原作或第三方修复项目的版权。

## 项目自有内容

| 内容 | 许可 |
|---|---|
| 本项目原创代码、脚本和相关原创工程文档 | [MIT](LICENSE) |
| 本项目原创译文 | [CC BY-SA 4.0](LICENSE-translations.md) |
| 游戏原文、原始资源及第三方内容 | 各自权利人的许可，不因进入本项目而改用上述许可 |

本页不替代许可证正文。版权与署名以对应文件为准；不要删除来源、许可文件或更改记录。

## 原版游戏文件

使用者自行提供原版游戏。完整 EXE、PAK、音频、视频、贴图、字体及其完整修改副本不提交到 Git，也不随测试包或 Release 再分发。

本地 `build/` 可以保存用户文件的隔离副本和验证证据；它被忽略并不代表其内容可以公开发布。发行应优先采用原创模块、构建器、结构化译文及必要差分，并在打包时再次检查是否混入原始资产。

测试夹具使用合成数据，不从原始封包截取完整资源充当测试素材。源码仓库也不上传完整提取后的英文文本池。

## FusionFix 与 Ultimate ASI Loader

用户提供的 `FusionFix/` 是本地依赖目录，不纳入本项目自有代码或翻译许可。源码参考以[固定上游提交](https://github.com/ThirteenAG/WidescreenFixesPack/tree/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix)为准。

初始核查发现：上游仓库根 `license` 为 GPLv3，本地二进制版本资源的许可文字则写 MIT。二者存在差异，不能仅凭 DLL 元数据把整套上游代码声明为 MIT。若后续复制、修改或分发上游内容，先核对具体文件的适用许可，保留来源与修改记录，再按对应条件组织发布。

当前路线是独立本地化模块，不把阅读上游代码自动视为已复用上游实现；实际依赖和引入的代码须单独登记。

## 字体与其他模组

004 及此前 PoC 使用 **Noto Sans CJK SC Regular 2.004**，字体元数据版权为 `© 2014-2021 Adobe (http://www.adobe.com/).`，商标通知为 `Noto is a trademark of Google Inc.`。来源为 [notofonts/noto-cjk 固定提交](https://github.com/notofonts/noto-cjk/tree/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans)，采用 [SIL Open Font License 1.1](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)。

| 输入 | 固定值 |
|---|---|
| 提交 | `f8d157532fbfaeda587e826d4cd5b21a49186f7c` |
| 文件 | `Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf` |
| 字体 SHA-256 | `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b` |
| `Sans/LICENSE` SHA-256 | `6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2` |

构建器首次从该提交下载字体和许可证，后续复用缓存；每次校验 hash。生成的图集基于该字体，不改标为项目 MIT 内容。语言包输出保留 `OFL.txt`，使用图集的测试包也必须保留许可、上述版权/商标通知与来源信息；当前通知从各 locale 的 font.json 生成 `FONT-NOTICE.txt`，打包器将它与 `OFL.txt` 一并复制。完整字体缓存位于忽略的 `build/dependencies/`；不依赖 Windows 本机字体。

更换字体或扩大字库前，重新核对来源、版本、覆盖、许可与必要署名，不能把当前选择的结论直接套到其他字体。

ReMade 模组由用户自行提供。PoC 002 按用户要求，将本机已有游戏、FusionFix 和 ReMade 复制到仅供本地测试的隔离目录；这不是公开分发包。兼容模组不等于取得其再分发授权。GitHub 仅提交集成工具、测试与说明，不上传完整游戏、模组 DLL 或高清材质；公开发行继续单独核对所有第三方许可。

## 发布前检查

- 每个第三方依赖均有版本、来源、许可与必要通知。
- 原创代码和译文分开标记；没有用项目许可覆盖原作内容。
- 包内没有原版或完整重建游戏文件、提取资源、私人路径/日志或凭据。
- 字体与依赖的再分发条件已核对；只发布实际有权发布的部分。
- 构建清单、输入身份、回滚方法和验证状态与发布内容一致。

## 启动兼容模块

`src/startup_compat.*` 是本项目独立编写、语言无关的适配代码；不修改或复制 FusionFix 实现。`assets/fusionfix-startup-contracts.json` 保存来自固定上游源码的机械字节签名和位置，来源提交及用途在文件内记录，不视作本项目原创逆向发现。相关源码、作者 ThirteenAG/上游贡献者及许可边界见前述 FusionFix 小节。完整原游戏、FusionFix、ReMade 和崩溃转储仍只保留本地；公开提交仅含原创适配器、机械契约、合成测试与说明。

## 新构建的思源黑体

用户选择思源黑体后，中文源码配置改用 [Source Han Sans SC Regular 2.005](https://github.com/adobe-fonts/source-han-sans/tree/6c709ca72d3d7c46ab42ebecc1a26e7d69595a37)，许可为该提交的 [SIL OFL 1.1](https://github.com/adobe-fonts/source-han-sans/blob/6c709ca72d3d7c46ab42ebecc1a26e7d69595a37/LICENSE.txt)。版权通知为 Copyright 2014-2025 Adobe，保留字体名 Source。字体/许可固定 hash 见 `locales/zh-CN/font.json`；构建输出原许可和从该配置生成的通知，不沿用旧 Noto 商标说明。未修改上游字体二进制，只生成所需字形的纹理子集；完整原英文字库不提交。004 保留旧字体用于对照，新构建状态见[编辑基线](docs/FONT_AND_EDITORIAL.md)。

## 采用的工程基准

本次采用用户提供的汉化工程基准 Revision 2.1 文档与参考 Python 检查器，来源文件与 hash 见 [localization-baseline.json](assets/localization-baseline.json)。源许可为 MIT、Copyright (c) 2026 jyh9521，与仓库现有 MIT 署名一致；保留原许可证。项目适配修改及未采用模板见[采用记录](docs/BASELINE_ADOPTION.md)。这不改变游戏、字体、模组或译文各自的许可。
