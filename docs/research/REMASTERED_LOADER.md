# Remastered 材质加载器：离线兼容性分析

本页只分析用户提供的 DLL 字节、导入/导出和静态调用链。没有执行 `LoadLibrary`、启动游戏、安装模组或验证画面。路径均相对本项目根目录；地址为 DLL 首选基址下的 VA，不是游戏 EXE 地址。

## 输入身份与证据

| 项目 | 已观察值 |
|---|---|
| 文件 | `ReMade With Second Sight Remastered Textures/dinput8.dll` |
| 大小 | 620,544 字节 |
| SHA-256 | `8aa884f7a6f4a4fa5294f457c0480149dc684479c9adbd8617c14c539d47f947` |
| 类型/首选基址 | x86 PE32 DLL / `0x10000000` |
| PE 入口 | `0x1004F4D3`，CRT dispatcher 最终调用 `0x1000F530` |
| 导出 | 只有 `DirectInput8Create`，VA `0x1000F450` |
| 静态分析 | pefile 2024.8.26、Capstone 5.0.7；未使用运行时反射/调用 |

本地证据在 `build/remastered-assessment-20261117/native/loader-static.json` 与 `loader-focused-disassembly.txt`。前者记录输入 hash、完整导入/导出和十四段代码的文件偏移/hash；后者保留这些范围的汇编。REA 由主调查绑定了输入身份；本页深层控制流依据为上述 PE/Capstone 结果，不冒称已运行 Ghidra。

## 1. 根目录 `dinput8.dll` 的冲突是确定的

`DirectInput8Create` 在 `0x1000F48E..0x1000F4DB` 使用 `GetSystemDirectoryA` 拼接 `\\dinput8.dll`，加载系统库并获取同名函数，随后转发原参数。发现的转发链不是本地 `dinput8_original.dll` 或另一份 ASI Loader。

`0x1004F408` 调用的模块 `DllMain` 位于 `0x1000F530`。PROCESS_ATTACH 分支会：

1. 保存模块句柄、禁用线程通知。
2. 调用 `AllocConsole`，重定向 stdout/stderr，并设置工具控制台标题。
3. 初始化 detour 管理器，加载 `d3d9.dll`。
4. 对 `Direct3DCreate9` / `Direct3DCreate9Ex` 安装钩子并启用。

未发现 `InitializeASI` 导出或字面 `.asi` 扫描；已追踪的初始化/转发路径也没有加载其他 ASI 的步骤。因此直接用这份文件覆盖现有 Ultimate ASI Loader，不是保留 FusionFix 与汉化模块的安装方法。

**候选方案（High-confidence deduction，不是实机通过）：**保留根目录 UAL，把这份 DLL 的独立副本以唯一 `.asi` 文件名交给 UAL 加载，材质目录保留在游戏工作目录。它的图形初始化在 DllMain 而不是 DirectInput8Create 内，因此无需通过其 DirectInput 导出才能开始注册钩子。该判断仍依赖 UAL 的插件加载规则、加载时机和下述 D3D9 链接兼容性；本轮没有把文件改名或安装来代替验证。

## 2. 它不只是被动贴图文件

模块通过 API 和 D3D9 对象方法安装广泛钩子。已追踪的关键位置：

| 模块位置 | 目标/行为 |
|---|---|
| `0x1000F5BC..0x1000F5F0` | Direct3DCreate9 / Direct3DCreate9Ex |
| `0x10007ED0`、`0x10007F20` | 创建接口后钩住 CreateDevice / CreateDeviceEx |
| `0x10006BA0`、`0x10006C00` | 创建设备前清除 BehaviorFlags 的 `0x10` 位；不是完全透明转发 |
| `0x10007CB0..0x10007EB4` | 注册 Reset、Present、EndScene、SetTexture，以及多个绘制、shader、状态方法钩子 |
| `0x1000A2C0..0x1000A347` | GetCursorPos / SetCursorPos 钩子 |
| `0x1000AD90` | 窗口按键/输入转发与覆盖层处理 |

在整个 `.text` 的线性反汇编（跳过不可解码数据）中，没有发现直接绝对内存操作指向 `0x00400000..0x00AFFFFF`。这支持“主要使用通用 API/设备钩子”的判断，但不证明不存在间接地址操作或所有兼容冲突。

固定 FusionFix 的 `Renderer.ixx` 明确调用 `D3D9Options::HookCreation()`，设置 frame 回调、beforeReset 回调，并在 frame 中处理限帧、光标和覆盖层。因此双方共享 D3D9 创建、每帧、重置和输入层，必须验证 detour 顺序、转发链、焦点/鼠标与设备重置，不能只依据“没有改同一游戏文字地址”判定兼容。来源：[FusionFix 固定 Renderer 源码](https://github.com/ThirteenAG/WidescreenFixesPack/blob/7bce79ffaeee61f95db59a68b35a150cd8644223/source/SecondSight.FusionFix/Renderer.ixx)。

静态导入还包括 **32 位 `d3dx9_43.dll`、`XINPUT1_3.dll`**（后者有 ordinal 2、4）。这些依赖的实际解析/加载成功不在本次观察范围。

## 3. `tex_XXXXXXXX` 不是原始 DDS 的 CRC

关键函数是 `0x10007630`。调用顺序和数据来源已静态确认：

```text
D3DXSaveTextureToFileInMemory(&buffer, 3, texture, NULL)
    ↓ 成功
buffer->GetBufferSize() / GetBufferPointer()
    ↓ 整段序列化结果
32-bit FNV-1a
    ↓ 8 位大写十六进制
Remaster_Textures/tex_%08X.dds（优先）或 .png
```

微软定义 `D3DXIFF_PNG = 3`，`D3DXIFF_DDS = 4`；该 API 将纹理转换为指定图像文件格式，并输出缓冲区。因此这里哈希的是 **D3DX 生成的 PNG 文件字节**，不是原始 DDS 文件、裸像素或文件名。[枚举定义](https://learn.microsoft.com/en-us/windows/win32/direct3d9/d3dximage-fileformat)、[API 参数与转换说明](https://learn.microsoft.com/en-us/windows/win32/direct3d9/d3dxsavetexturetofileinmemory)。

`0x100076B7..0x100076DF` 的算法可直接写成：

```python
def replacement_id(d3dx_png_bytes: bytes) -> int:
    value = 0x811C9DC5
    for byte in d3dx_png_bytes:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value
```

任意 PNG 编码器的压缩、过滤或元数据不同都会改变文件字节。用 Pillow 重新生成 PNG，或者直接对 DDS 做 CRC32/FNV/SHA，不构成本模块命中或不命中的证明。中文图集的潜在 hash 碰撞也需要同样的 D3DX 序列化输入，不能仅按本地 DDS 文件 hash 排除。

当前汉化图集由独立模块提供，但进入 D3D9 后仍可能经过材质模块的 Stage 0 拦截。因此“资源路径不同”不等于图形层完全隔离。新字形图集和原字库都要纳入用户联合测试。

## 4. 替换范围、默认值与体验因素

- `0x1000A870` 的 SetTexture 适配只收集 **Stage 0、类型 3 的 2D 纹理**；其他 stage/type 走原函数。这是已追踪路径的范围，不等于所有游戏材质都覆盖。
- `0x100940C0` 初始字节为 `01`：纹理替换默认启用。调试覆盖层状态初始为零。
- Present 路径 `0x100086B0` 从待处理集合中每次最多选择 3 个纹理，经 `0x10007630` 序列化/hash/查文件。初次场景可能逐帧出现替换，实际卡顿与速度未测。
- `0x1000AD9C..0x1000AE08` 对 WM_KEYDOWN 处理 Insert（切覆盖层）、Home（切纹理替换）、End（切另一个绘制调试开关）。具体游戏/其他模组按键冲突待测。
- 相对路径是 `Remaster_Textures/`，没有观察到按 DLL 自身路径拼接的逻辑；候选集成必须保证游戏工作目录正确，而不是随意把材质移入 `scripts/`。
- 加载 DLL 会尝试创建工具控制台；这是代码事实，实际窗口状态未观察。
- DDS 加载优先使用 `D3DXCreateTextureFromFileExA`，失败后有自定义 DDS/DX10 header 分支；存在 BC1/2/3、ATI1/2、BC7U 等 FourCC 路径。代码分支存在不代表所有显卡/驱动都接受相关格式，具体包的纹理头统计应与实机结果分开。

## 5. 缓存、回收与大纹理

不能把所有容器都称为“缓存泄漏”。静态控制流区分出三类对象：

| 容器 | 已追踪生命周期 |
|---|---|
| `0x10099D48`，本帧可见原纹理集合 | SetTexture 首次加入时 AddRef；Present 末的 `0x10006930` 逐项 Release 并 clear。原纹理这一层有逐帧平衡。 |
| `0x10099DC8`，原纹理指针→替换纹理映射；`0x10099D68`，已处理指针集合 | 替换成功后持有创建的替换纹理；已追踪的明确逐项 Release + clear 位于覆盖层 **Reload All Replacements** 按钮 `0x10009B80..0x10009BA4`。重新启用纹理替换还会清已处理集合。 |
| `0x10099DE8`，render-target/绘制统计对象 | `0x100073E0` 有超过 300 帧未使用后的回收；这不是上一行的替换纹理映射。 |

Reset 钩子 `0x1000A270` 处理覆盖层设备资源及原 Reset，再刷新渲染目标信息，没有观察到清除替换映射/已处理集合。设备 detour 注册表也没有纹理对象 Release 钩子。上述限定路径中未发现随原纹理释放或关卡切换自动删除对应替换项的机制。

由此存在两项 **High-confidence deduction**：替换纹理可能跨场景累积；原纹理指针被回收并复用时，长期保存的指针 key 可能命中陈旧项。它们不是本轮已复现的内存泄漏或显示故障。实际驱动显存管理、加载范围和场景生命周期还需用户测试。

SetTexture 路径只判断 Stage 0 和 GetType()==3，没有读取 `GetLevelDesc().Usage` 来排除 `D3DUSAGE_RENDERTARGET`，因此 **2D render-target 纹理没有被这条路径明确排除**。图集中看起来像整帧画面的内容，不能只凭截图就断言没有用途，但应单独验证命中对象与效果。

原游戏 EXE 的 PE Characteristics 为 `0x010E`，未设置 `IMAGE_FILE_LARGE_ADDRESS_AWARE` 的 `0x20` 位。结合 32 位宿主和长期替换缓存，大量 8192×8192 材质应作为单独的内存/稳定性验收项，不默认加入第一轮中文 PoC。单张全 mip 的 8192² DXT5 仅压缩纹理数据就约 85.3 MiB；磁盘总大小既不等于同一时刻显存占用，也不代表低运行内存成本。本轮不改 EXE 的 LAA 标志。

## 6. 推荐的联合验收顺序

1. 保留原 PoC 001，先确认 FusionFix + 汉化三个场景的基线。
2. 另做联合副本，保持 UAL、FusionFix 和 Localization 原 hash；材质加载器作为独立候选模块，材质目录位于游戏工作目录。
3. 用户手动验证菜单、开场/实际字幕、PDA，再比较同一场景材质开关前后；同时检查控制台、键鼠和覆盖层。
4. 验证读档/关卡切换、Alt-Tab/设备重置、不同窗口模式、纹理加载延迟及显存/进程内存。
5. 单独移除候选材质模块即可回到已知 PoC 文件组合；不要覆盖根目录 UAL 来实现切换。

本轮结论：**存在保留 UAL 的集成候选，直接覆盖安装确定有加载器冲突；完整三方共存尚待用户实机验收。**
