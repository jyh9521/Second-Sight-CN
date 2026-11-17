# 严格目录句末校验修复

## 范围与结论

本次处理严格目录校验报告中的 **27 条记录、45 处句末规则违例及 6 处歧义字符**。22 条目标文本仅调整句末标点；6 条记录增加精确语境标注，其中 BS 3275 与前一组重叠。规则唯一来源仍是 [STYLE](../locales/zh-CN/STYLE.md)，本次未修改个人规则、角色映射、术语表、稳定 ID、源文指纹、原生控制码、内部标识或既有审校状态。

- 修复前：`EDITORIAL FAIL: errors=51; punctuation + glossary; no game execution`，退出 2。
- 修复后：`EDITORIAL PASS: errors=0; punctuation + glossary; no game execution`，退出 0。
- [待处理队列](../locales/zh-CN/policy-review.json) 重新生成后为 0 项；它是输出，不是校验器输入或放行名单。
- 这仅关闭本轮逐句标点阻塞，不等于整条译文、对白角色、游戏布局或新字幕功能已经验收。GitHub 实际运行状态由 CI 记录独立描述。

## 原版依据和审校决定

源文来自固定 GOG 输入的只读 `export_catalog.py` 导出；EXE、主 BS 和 PDA 成员分别经过现有 hash 守卫。版本身份以 [项目合同](PROJECT_CONTRACT.md#输入身份) 和构建器常量为准，不把英文片段复制到公开目录作为完整原版资源。

45 处明确句号均按各自逻辑句子判断，而非因为整条记录含逗号就保留。删掉句末句号后，相邻逻辑句之间保留一个普通空格；原 LF/TAB 和 VT 按钮码不改动、不增加换行。句中逗号及顿号、问号、感叹号、省略号和内部命令串保持原样；没有为了过检查添加逗号。

| 语境记录 | 判断与处理 |
|---|---|
| BS 1363/1365/1367/1369/1370/6509/59/6121 | 存档、载入、光盘和覆盖提示；逐句省略符合条件的句号，保留按钮及提问 |
| BS 313/314 | 版权/发行说明不是剧情文本；逐句处理，保留公司名、年份、引号及原换行；活跃消费者仍待确认 |
| BS 3275 | 病历室通行条件和找持卡人的 UI 指示；两处句末句号处理，姓名缩写点保留 |
| BS 3779 | 终端状态两句；保留省略号、原换行及 `MEDFAC:pr_data/>` |
| PDA p046.r001.s000 | 冷战说明的首句不含逗号；后句含逗号，保留原有句号 |
| PDA p050.r004.s000、p051.r002.s000、p051.r005.s000、p053.r005.s000、p054.r002.s000、p054.r003.s000、p054.r006.s000 | 能力介绍/操作说明而非人物对白；逐句判断并保留所有原生按钮码 |
| PDA p058.r002.s000、p063.r002.s000 | 武器说明；只改报告命中的无逗号句，其他句末及数值不动 |

6 处歧义是**非句号用途/组合语法的语境解析**，不是标点规则豁免：

| BS ID | 源文证据与用途 | 目标显示 |
|---|---|---|
| 2411 | 游戏标题中 `'92` 的年份省写，不是未闭合引号 | 保留撇号 |
| 3275 | 源文持卡者姓名为 `Dr. F. Giddler`，`F.` 是姓名首字母 | 保留缩写点 |
| 3632 | 原 BS 3631/3632/3633 相邻终端消息片段；3632 留下 `(code`，3633 原字节为 `#15)`，hash `e1238c150116ce2199b22094bbb6dc25df26528e68bf1538b4b7fdd34cf7bc3a` | 保留开括号，不擅自加闭括号；实际运行组合未验证 |
| 4067 | 西翼房间标签中 `Wilde, J.` 是姓与姓名首字母 | 保留缩写点和成对括号 |
| 4509 | `1)` 为镜头操作列表第一项编号 | 保留 `1）` |
| 4510 | `2)` 为房间选择列表第二项编号 | 保留 `2）` |

## 适配合同与回归

[punctuation-context.json](../locales/zh-CN/punctuation-context.json) 是本项目的精确语境记录。每项包含资源组/稳定 ID、原始 CP1252 源 SHA-256、当前 UTF-8 目标 SHA-256、源/目标单字符半开区间 `[start,end)`、字符、用途和证据。索引按 Unicode 字符计数，不按 UTF-8 字节数。

[audit_locale_policy.py](../tools/audit_locale_policy.py) 在调用现有语言策略前验证绑定，仅把已确认的那一个字符投影为中性字符；实际目录和游戏显示文本不变。源文已绑定时再次验证源区间和语法；离线未带原文的 CI 依赖固定原始源指纹。未知用途、跨度超过一字符、重复位置、无证据、缺失记录、源/目标变更均拒绝旧判断。新的句末句号仍由原策略拦截，不能把整条记录、整个文件或整类文本跳过。该文件进入 `catalog_files` 构建输入指纹清单。

[回归测试](../tests/test_punctuation_context.py) 覆盖精确绑定、源/目标变化、重复/越界范围、未知用途、全记录跳过企图、ASCII 真句末点伪装、控制码偏移及保留显示。原始歧义文本不带绑定仍报 6 个 review；“姓名缩写 + 真句末句号”仍报 violation。构建门禁测试向一次性目录实际加入违例，确认在字体依赖/资源处理前拒绝；没有把 gate mock 成成功。

## 验证层级与复现

从仓库根目录执行，以下命令已运行；全程未启动、操作或附加游戏：

```powershell
python -X utf8 tools/translation_checks.py --locale-dir locales/zh-CN
python -X utf8 tools/audit_locale_policy.py --locale-dir locales/zh-CN
python -X utf8 -m unittest discover -s tests
```

输出分别为 `EDITORIAL PASS: errors=0; punctuation + glossary; no game execution`、`SENTENCE_POLICY PASS: records=0; violations=0; review=0; mutations=0; game_launched=false`、`Ran 241 tests` / `OK`，退出码均 0。本地另对修订目录执行真实原版 source-bound 导出和 `translation_checks.py --data`：`EXPORT PASS: BS=5957; PDA=447; local bilingual review only; game not launched`，然后 `EDITORIAL PASS`，均退出 0。

| 验证层级 | 本轮实际覆盖 |
|---|---|
| G1 数据 | 6,406 条文本的稳定 ID、原始源绑定、元数据及原生 token 序列相对基线不变；只改 22 个 target。严格 policy 审计覆盖 1,940 条非剧情记录（含图像文字），4,467 条既有 narrative 分类仍按既有规则处理，未重审分类 |
| 人工内容审校 | 仅本次报告中 27 条的句末/点号用途；不是全文翻译审校，不增加已全审或已运行记录数 |
| G2 离线资源 | 真实原版源绑定检查通过；本子任务没有重建发行包或重新验证资源布局 |
| G3 游戏内 | 本轮新增 0；排版、字幕功能和显示效果留待独立候选验证 |
| G4 发行包 | 本子任务未打包、安装或发布 |

本地证据目录 `build/editorial-repair-009/`（Git 忽略）：`baseline/` 保存未修改目录，`modified/` 保存已修订副本，`rollback-copy/` 由独立恢复脚本恢复。`verification-commands.json` 和 `VERIFICATION.txt` 保存实际命令、绝对输入、完整标准输出/错误输出及退出码。`MODIFIED_FILE.json` 为已修改 PDA 文件的核对副本，`DIFF_FILE.patch` 为本轮文件差异，`ROLLBACK.sh` 只恢复该隔离副本，不写工作目录和原版游戏。

隔离恢复先检查全部输入 hash，再恢复基线并移除仅本轮新增的上下文文件。实际结果：`ROLLBACK PASS: isolated locale restored byte-for-byte; modified catalog retained; game_launched=false`（退出 0）。恢复副本重新出现原始 `errors=51`、`records=27; violations=45; review=6`（退出 2）；这证明恢复的是原阻塞状态，而不是把回滚误报为校验通过。工作目录和修改副本保持新版，原始源文件和个人规则不变。

## 记录指纹

仅证明本轮审校身份；不是全内容或运行验收标签。源 hash 使用原 CP1252 字节；前/后 hash 使用目标 UTF-8 字节。6 处语境字符的精确区间见上方 JSON；同值前后 hash 表示只增加语义判断而未改显示。

| 记录 | 原始源 SHA-256 | 目标修改前 SHA-256 | 目标修改后 SHA-256 |
|---|---|---|---|
| `bs:1363` | `8eb478e6321e09166f96be4dbd764fcce9e2d72672b53902006f77835f589e98` | `812fb3faec63e9c801d87dfc563dfe4de1e086c1a0c2b26e43470dedeb441736` | `de06c4d8df2c7d7d71c60c5cb9f8330de9af97fc67c5ce5fdd346ead4edb5820` |
| `bs:1365` | `7eede22af29e24805696a4f10f038672ee36903029698165ef7f4ec0579d0711` | `a74eaa471845d3440ea4a1fe24da1ff88e5f69d8cabfffa9288eabec23132856` | `4fa17f9033030576c5596a0c2819d64ca346399a0dd9a6dfa0a900d6b61c461d` |
| `bs:1367` | `29f2ff17bd373af4eaf60af2e3597eeea46de790d713a10a1c742b090d7ebb8f` | `acc759accbae627dd77b63e5713bbefee63c5458c1790777c1fb8212ad3cb825` | `f39da923c1f348afe28143b6443b60e9c7d0c74506272e36d49c46526fca5e23` |
| `bs:1369` | `b6ed1a09e9c8c6e15e63c9164a8cb4862c425058a47e2bd020bea3c316203b72` | `9cbde85eec1d7bdbe2fa93616517ae05cdebd62225e0b389a802b04d07e4e3d3` | `0db1d98db2cd1a1ff69c006bad0df29ed964a57361a392a3f64d02a32482a4ed` |
| `bs:1370` | `be0e997a8417fd2d423ca2bc6f9dc95968f5814729f91d2fdb9fa7ca12ec31d1` | `f11ab0288ff9744dab2845f9329c78a2f38a6563b77f877efbe391dd84b3502f` | `4b4a1ad87b252290dbb97cbbd033df905af326b28b25e54ca5093c253d8a2957` |
| `bs:2411` | `2297b77a55fbb701725492df2ba9eac23dc208e9341a15fab5a6aaf748a058f9` | `269a428d2fa3bc7359c49dd768888bb77bbd3122e39399e4b1a4e6e07d9f7899` | `269a428d2fa3bc7359c49dd768888bb77bbd3122e39399e4b1a4e6e07d9f7899` |
| `bs:313` | `4405c8cb554f61ed17aa187f092ef523d82e45fca4f935c855a210282ca5b91b` | `c448fe5b57abe915d6eef7a2277eebd0cedf9b2df35680b7f55b40540e75b813` | `93590db08eddfb6beae85115eb66cbd06a9e78d35c9ca18b320b0d50fb0e870e` |
| `bs:314` | `5e750e62e50e083362268be91dd88ec8458ec25c6718afc3e81bb40fe792eb93` | `80ab4b9a9bf1adafa021e3d64fba8e6e2394d3bab3080fd8f79fdedda235d49c` | `2f553355bd459d46ab06e3c3a5f0950e162290b0e49df599892408673c050862` |
| `bs:3275` | `b65e04fbb46183377df733475af36cd1651acc0b2b4a8379cd97f0b9b246aa92` | `f81fe251f495c961202b3f1a8d85b0b60d7b81c1174d8b1f987e6d8e4335182f` | `3be92b07e6f24d65a1f193856c9f9596bfbdf91d268832552796435c95775070` |
| `bs:3632` | `7820ddd984f54103adb2dbf15c21fffcd53c2fabdc8b985adfbf32702e85bbf7` | `0e81086e6cd541833026ecab23ff81a358fff37d4475a77b4d124ea225053ba4` | `0e81086e6cd541833026ecab23ff81a358fff37d4475a77b4d124ea225053ba4` |
| `bs:3779` | `33636430cc6da601006f235e0f88e438c0a345f76e169621babf343935ad3982` | `8a7cfe4640c686ef9f26e22205a9df332047f6064b7bd65f8ab1229e67259a30` | `bed5fd3384a8784b01b0436fce4ab340435aeb4f3b3cd436545cf1ee6403c140` |
| `bs:4067` | `4db41af9f22b476fe3024bfa5fa3e9b06121c494f43b7356ded34fc92216ab7c` | `bb882bba240b253a323fb8ef150dc973427387b712f4b7894063c70c57345846` | `bb882bba240b253a323fb8ef150dc973427387b712f4b7894063c70c57345846` |
| `bs:4509` | `323e9754b724b1dc20a40ea4354f60da859b2fdac271772d52c85fe8c99a1cbc` | `59d4bfcb73ad3d1dab91f520e4718c54aed7c987259bd84464bb92d99ff29686` | `59d4bfcb73ad3d1dab91f520e4718c54aed7c987259bd84464bb92d99ff29686` |
| `bs:4510` | `b32b07968d0d80a9c154553cc2d7c730b14f515b28f6d353d974fe4ba866857b` | `af5281f46e181f8855a4ab19350e034eb662409bece3840ab6b58c9995e8b5e9` | `af5281f46e181f8855a4ab19350e034eb662409bece3840ab6b58c9995e8b5e9` |
| `bs:59` | `d3923cdc97c7cac27aa6e89ca8e91c55b913adbab71afa9e0031878b25b5ccfd` | `df107b7a4aa6cc81943546c8e68d6fc9ddef6552bca84fbeb5ce29443d27bfc6` | `4b2d5dc977bda1b219ac95e757c157c707a7e3f2b2c610e17d6097e6ebabf2ad` |
| `bs:6121` | `f1f755a5e68698527a53905e8d7d1ddae0906292d8b3d3a2eabcce39d64ee74a` | `65a07741ef59bab59f0952430047277940a6763d11b2c33edd6953d45cceff98` | `3a2685210fa972f50228c655ce7be7dd3601db8ddd9f76ab4136e7d97edc50ce` |
| `bs:6509` | `9596e93fa99f483e49d81faa7491939bc10d884c9f5a3e4775dda8282c9965e1` | `99127d993c3b42a08516bd13e9b28d9f075212e6bc2f33043ec4d92455ac8ee8` | `170852e7a401b60234881efc90d731ad6f180ef6f73c544cb42ec4c0d9add91f` |
| `pda:p046.r001.s000` | `c4938dfa0a9a73db44919eb1c9a6430c706277a30e5525c48a78ed84c3cbb845` | `ebf18f1816ce4b64db762a82777026fb06b1f70f5b3e2e7adf6dee9d78164731` | `44712f0b6e5b4f2d91e9da90db67ecb7ccb7a4a77c6b9fec56921945d9120fb4` |
| `pda:p050.r004.s000` | `62ccef2414f867a4c96803f07540b65637d1fc209845d1e5b6fce42c5026c837` | `67114ae29757e709bd2d3768b273dd4db382e9c75a946a18a8da085d512cce04` | `a6e0932384d89c068fc355de2699d3414dfbd4c999a3ed2e6ce1e751956c9d03` |
| `pda:p051.r002.s000` | `47378feef6fd5b706362a8d706d82fba4e0ce3ebc2e3c5b15a2597354510c900` | `44141869aa674fce92c1539344e3c1d23da2438a611c597054fbe5d7e073b62a` | `1660374197b967890541073198e11d4b8db077af6e7556718d604a0ffad4e438` |
| `pda:p051.r005.s000` | `19c80c9f325e2456ff2cc2db89eaf05acf72c9969a0eef70c76d067f2c969f3a` | `701175887f988b1f673c8b7f1a13f76b3260a38f4424bfb258c49cc5f1c9ddb0` | `918f3e0e964581e7cf2c368d4b9022029d171b7a2c2cb3a2ce535abc940bac76` |
| `pda:p053.r005.s000` | `fa7c06d73745748273f397f0f0f81847940863dbf964735d5f4ea59a4b8f6608` | `1c678593ef02600f471cdd6f4a5add7327bbe84986f2aeb1bf123f1a33f47014` | `4d2194c644b47398df32eed52915db1ad1f8f76824e59167c51c8b8b87c14f64` |
| `pda:p054.r002.s000` | `0a3c812837a019533ef5fc15903531d0f6d156822924da9b73918921df813c40` | `1ad455ce920aef3b98ab7fee8825b7843bdbda35e8e13fb3949ae872af74a02e` | `637c306349cd9188f9fc4ad72f5962d0e7710570e04a3385867a5a2160fc992a` |
| `pda:p054.r003.s000` | `b621b87aae776a6c9fe6a0c12575ca9156053bb873f65505e182bcddfdae0bd1` | `6b0189abf252da39638809b0efd3f4358f2b51fefad899db65d17121111685e8` | `05a1d7fed5ed24b2a4ddfd4cc911dd530ab8aed867064b78bd5a7ab3358a57fa` |
| `pda:p054.r006.s000` | `ccd1a68907d6b9fd18854d00ed22a0a26a9da5d0714e810a87427a67094821b2` | `9e5eeea3e16c652c44e76aebf6603b29f483e36fb7919f39fac12100d8fd9949` | `266ff60ecacc11dcfd42fbc207ba2f65375c56a2852e5a512cf50589db119958` |
| `pda:p058.r002.s000` | `f3bcf4e4a8e5d3d13c898c502a81560fa84b7acbd5c98c973f23a38a012f7692` | `02c5c641491cff77a44a2d4f6ad6e2c4015ef61a2c1ec22c98b9c4326472b998` | `580159d82420c59def4eea31c22d547d355bb11736bf9a34619680cefc7beb09` |
| `pda:p063.r002.s000` | `2d033eac30a9ab73a0f4a84507284f0c3a8252a03ad7d938a32a24483ac5b093` | `2eff183c27bcb51115451c1d03e1d8df5d70e573c66c1cdd7099554d46d46699` | `8650d46e8a8c688fceb15ee2548fc4c11f45025f6f53d6f2e999fdd3e68e82d2` |
