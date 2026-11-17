# PDA 资源格式与离线重建

本文记录 PC 版 `data/pdaps_?.raw` 的独立静态分析。所有地址均为下列原 EXE 的虚拟地址；文件结构偏移均从 RAW 文件起点计算。未启动游戏，运行时中文显示由用户验收。

## 已验证输入

| 输入 | 大小 | SHA-256 |
| --- | ---: | --- |
| `secondsight.EXE` | 5,484,544 | `4092a8d1fb042dffe9fb95e2185f32cb80390299145e8d453a5e909a06d35fda` |
| `pdaps_a.raw` / `pdaps_e.raw` | 79,622 | `f684ffe987026172b5a69f82e11ee6426190bf629939596cad3f6571b098f6d7` |

EXE 为 x86 PE，ImageBase 为 `0x400000`。以下函数范围中的文件偏移等于 VA 减去 ImageBase。原资源、原图像与提取的完整字符串不入库；合成测试不需要原游戏。

## 已验证结构

各整数为 little-endian。文件没有已知 magic；解析成功不等于版本匹配，修改前仍须核对来源哈希和原字符串。

### 32 字节头

| 偏移 | 类型 | 用途 | a/e 原值 |
| --- | --- | --- | ---: |
| `0x00` | u32 | 页面/组描述表偏移 | `0x20` |
| `0x04` | u32 | 索引表偏移 | `0x1CDC` |
| `0x08` | u32 | 图像描述表偏移 | `0x1DE0` |
| `0x0C` | u32 | 内部标识符指针表偏移 | `0x240` |
| `0x10` | u32 | 页面/组数量 | 68 |
| `0x14` | u32 | 索引项数量 | 65 |
| `0x18` | u32 | 图像数量 | 10 |
| `0x1C` | u32 | 内部标识符数量 | 101 |

前四项及页面、图像、标识符数量由原重定位函数 `0x5804E0–0x58060F` 直接访问。`0x14` 的数量解释与六份资源中的索引区间长度吻合；索引项的位域语义仍待确认，工具逐字节保留。

### 页面、行、内容段

```text
Page[page_count], stride = 8
  +0 u32 row_count
  +4 u32 rows_offset

Row[row_count], stride = 8
  +0 u32 segments_offset
  +4 i16 segment_count
  +6 u16 metadata                # 未解读的原字段，保留

Segment[segment_count], stride = 8
  +0 u32 value
  +4 i32 tag
```

`tag` 的处理规则：

- `-3`：`value` 是不重定位的数值，不是字符串。实档有 `0x10` 等值，不能按十张图像的下标检查；具体业务语义未定。
- `-2`：`value` 指向图像描述表中的一个 8 字节记录。六份资源各有十个这样的引用，不是空字符串。
- 其他已见值：`value` 指向 NUL 结尾显示字符串，`0` 保留为空指针。`-1` 常见于普通文字，非负 tag 与链接关系相关的解释仍属推断。

关键反汇编证据：`0x580565/0x58058C` 按有符号 16 位读取段数；`0x580572–0x58057C` 比较 tag 是否为 `-3`，仅该值跳过地址重定位。`-2` 虽然需要重定位，但目标是图像记录而非文字。

### 其他表与不透明区域

- 索引表：`u32[index_count]`。例如 `0x00040036` 含高位信息，不按纯页面编号重写。
- 图像表：每记录为 `u32 runtime_or_unknown; u32 image_offset`。原第一字段为零；loader 重定位第二字段后调用 `0x413A00`。
- a/e 的十个图像数据起点为 `0x1E30 + i * 0x1410`，末尾为 `0xE6D0`。工具不重编码图像，只检查描述记录/最低头部边界并保留全部原始字节；图像头后载荷长度和纹理语义未完整解析。
- 内部标识符表：`u32[identifier_count]` 指向 NUL 结尾机器 ID。a/e 的 ID 字符串池从 `0x13278` 开始。这些 ID 与显示文本分开，工具不开放翻译接口。

## 稳定定位与最小任务页

工具按结构坐标生成 `pNNN.rNNN.sNNN`，分别表示从零开始的 page、row、segment。它不是游戏原生字符串 ID；不同资源版本必须重新核对，不能只凭编号套用。

下表适用于上述哈希的 a/e 资源，四项 tag 均为 `-1`：

| 结构 ID | 指针字段偏移 | 原字符串偏移 | 原文 | 中文 POC 建议 |
| --- | --- | --- | --- | --- |
| `p055.r000.s000` | `0x188C` | `0x11D7B` | Objectives | 任务目标 |
| `p055.r001.s000` | `0x1894` | `0x11D86` | Isolation | 隔离 |
| `p055.r002.s000` | `0x189C` | `0x11D90` | Escape. | 逃离。 |
| `p055.r003.s000` | `0x18A4` | `0x11D98` | Get out of the isolation cell. | 离开隔离室。 |

最后一项为 30 字节，数据范围 `[0x11D98, 0x11DB6)`，NUL 位于 `0x11DB6`。译文由 `locales/<locale>/` 管理；上表只说明定位关系，不把中文逻辑写进通用工具。

## 重建接口与保护

`tools/pda_resources.py` 提供：

- `PdaResource(data)`：读取头、指针表、显示段、标识符、图像引用；校验边界、数量、对齐、表重叠、终止符。
- `rebuild(replacements, expected_sha256=..., glyph_marker=...)`：验证原哈希及每项原文，按指针字段顺序追加新字符串，仅改选中项的 4 字节指针。无修改时返回逐字节相同数据。
- `replace(replacements, glyph_marker=...)`：供已在外层固定资源版本的构建器使用的便捷接口，仍逐项校验原文字节；也可传 `expected_sha256`。

同一原字符串的多个指针可以单独翻译。若多个结构 ID 共用同一个指针字段，须同时列出所有受影响 ID 且目标一致。工具保留旧字符串、全部机器 ID、未知元数据、索引、图片和未选中的引用。

原始 C0 控制码（含换行）、`0x7F`、`0x0B + opcode`、常见 printf 和花括号占位符按原顺序严格比对。实档观察到 VT opcode `E/J/I/G/2/4/K`；尚未逐一确认所有语义。工具既不改写 opcode，也不自动归一化空格。

采用自定义字形传输时，调用者须显式批准 marker。例如：

```python
from pda_resources import GlyphMarker, PdaResource, Replacement

source = original_path.read_bytes()
pda = PdaResource(source)
result = pda.rebuild(
    {segment_id: Replacement(expected_original_bytes, encoded_target_bytes)},
    expected_sha256=verified_source_sha256,
    glyph_marker=GlyphMarker(prefix=b"\x1f", digits=4, max_id=atlas_glyph_count - 1),
)
output_path.write_bytes(result)  # output_path 必须是副本路径
```

批准项仅让**格式完整、ID 在范围内**的新增 marker 不参与控制码比对；原 VT/占位符仍须保留。若原文已有该 prefix 则拒绝，避免把原控制码误当作新字形。整数简写 `glyph_marker=0x1F` 表示四位十进制、ID `0..9999`；正式构建宜按实际 atlas 缩小范围。

命令行不覆盖现有输出：

```powershell
python tools/pda_resources.py inspect SOURCE.raw --output build/pda-inspect.json
python tools/pda_resources.py rebuild SOURCE.raw replacements.json build/pda-modified.raw
python -m unittest discover -s tests -p test_pda_resources.py -v
```

替换清单为 `format=second-sight-pda-replacements-v1` 的 JSON 对象，包含 `source_sha256` 与 `replacements` 数组；每项为 `id`、`expected_hex`、`replacement_hex`。可选 `glyph_marker` 对象为 `prefix_hex`、`digits`、`max_id`。这些 hex 字段描述实际二进制资源接口，不声称文件编码就是 Unicode。

## 加载与运行时接入证据

1. `0x5822C0` 选择语言，`0x58230B` 调 `0x49FF40` 注册 PDA 资源。
2. `0x49FF46` 先调 `0x49F580` 查缓存；未命中则在 `0x49FF74` 调 `0x49E490` 查询大小。并非统一走 `0x49DDF0`。
3. `0x583BAC` 调 `0x49F580`，后者只遍历 `0x915A58` 起的资源记录表，无读盘行为。
4. `0x583BB1` 取记录 `+0x10` 的内存指针，`0x583BB5` 调原 PDA 重定位函数 `0x5804E0`，`0x583BBD` 把返回值写入 `0x965208`。

因此，仅拦普通文件大小/读取函数不保证覆盖 PDA 缓存路径。最小接入点是原 call `0x583BB5`，原字节为 `E8 26 C9 FF FF`。原函数为 x86 cdecl，参数 `[esp+4]` 是资源基址；返回 EAX 为同一基址，保留 EBX/EBP/ESI/EDI，末尾为 `ret`。caller 在 call 后执行 `add esp,0x14` 清理此前累积参数。

可在 wrapper 中先调用原重定位一次，再核对目标字段及原字符串，把显示指针换为进程期稳定的译文指针。此方案不需要打包整份 PDA 原图像，也不修改图像/机器 ID。原重定位没有已处理标记，不能针对同一数据额外执行第二次。静态扫描仅发现一个直接 call 进入 `0x5804E0`；`0x583B60` 的直接调用点为 `0x5457A3/0x545BD4/0x545E39`。这些证据不等于已确认缓存释放时序。

## 离线验证与待用户验收

六份本地资源均通过解析和无修改的 byte-identical roundtrip：

| 资源 | 页面数 | 显示段数 | 内部 ID 数 |
| --- | ---: | ---: | ---: |
| a / e | 68 | 447 | 101 |
| f | 68 | 455 | 101 |
| g | 68 | 451 | 101 |
| i | 68 | 453 | 101 |
| s | 68 | 454 | 101 |

合成测试覆盖增长、无修改复原、别名独立性、共享指针冲突、坏计数/偏移/终止符、原哈希/原文、控制码、marker 格式/ID 范围、内部 ID 与图片字节保留。

尚待验证：

- 中文 marker 的绘制、测宽、换行、截断以及 PDA 页面实际显示。
- `0x580660` 的逐词复制与 `0x5806F0` 的换行缓冲区容量；marker 每字增加字节数，文件可增长不代表无限长句能在游戏中使用。
- 长文、非空格断行、控制码插值、链接选中、跨页与任务状态切换。
- FusionFix 同时加载时的 hook/状态生命周期，及用户下载的其他 Mod。

当前工具证明的是离线结构可重建、可回滚；运行时验收由用户手动进行。
