# 小米扫描 APK：文档裁剪与彩色增强实现分析

分析日期：2026-10-26。

后续进展：本报告记录第一阶段静态分析。电脑端现已接入四份模型并完成真实推理与导出验证，最新状态见 [电脑端实现与验证](电脑端实现与验证.md)。

## 结论

本目录 APK 中，与截图对应的功能是“扫描转 PDF”的裁剪和滤镜流程。核心采用 **本地 native 图像处理、内嵌 MNN 神经网络模型和 OpenCV**。

已经定位到完整的业务调用链，并提取出文档检测、彩色增强和两阶段曲面矫正使用的四份模型。白底效果的关键是 **模型辅助的光照估计、逐通道去光照归一化、Gamma 和直方图对比度调整**。只做全局白平衡、调亮或二值化，并不等价于这条实现。

电脑端有复现路径：运行内嵌模型，重建对应的几何和图像前后处理。当前完成的是静态分析和模型提取，尚未执行桌面 MNN 推理，也未证明桌面输出与手机逐像素一致。

## 1. 样本与分析范围

| 项目 | 结果 |
| --- | --- |
| 输入 | `base.apk` |
| SHA-256 | `a92b062f8a5bf65656f781c017d583da6caba46f9ec4e5695d1c501cac892a65` |
| 包名 | `com.xiaomi.scanner` |
| 中文应用名 | `AI扫描` |
| 应用版本 | `15.9.80` / `1322032510` |
| minSdk / targetSdk | 29 / 35 |
| 核心库 | `lib/arm64-v8a/libDocumentProcess.so` |
| 核心库大小 | 13,422,536 字节 |
| native SDK 自报版本 | `Morpho Document Ver.1.6.33 for Xiaomi 20260828_1` |
| 图像库线索 | OpenCV 3.4.8 的源文件路径与函数断言 |
| 模型引擎 | MNN |

这里分析的是用户提供的这个 APK；不把其他同名扫描产品的实现套用到它上面。

范围包括 DEX 反编译、资源对应、JNI 导出与依赖、native 关键函数反编译、模型缓冲区定位和结构检查。没有修改原 APK，没有安装应用、连接设备或发起应用业务网络请求。

工具：JADX 1.5.1、apktool 2.11.0、rabin2/radare2、Ghidra 12.1.2。本机没有 IDA，native 深入分析使用 Ghidra。JADX 全包反编译报告 16 项错误；个别方法的条件分支恢复不完整，关键数值和调用点另用 ARM64 指令及数据区交叉核对。

## 2. 截图与业务入口对应

资源中可直接对应截图：

- `scan_pdf`：扫描转PDF。
- `document_region`：智能框选。
- `Enhance`：增强。

页面链路为：

```text
DocCropActivity / DocCropVM：读图、检测边界、手动调整四角、确认裁剪
    ↓
DocumentModule：桥接文档检测和几何校正
    ↓
DocumentProcess → DocumentProcessJNI → libDocumentProcess.so
    ↓
DocRecActivity / DocRecVM：显示裁剪图和预生成的增强图，切换滤镜
    ↓
DocPreviewVM：将处理后的 Bitmap 绘制到 PdfDocument 页面并保存
```

这条图像处理链不以 OCR 识别文字、再重新排版为基础；它直接处理图片像素，因此能够保留手绘、印章和彩色图案。

### 2.1 本地图片读取与框选

`DocCropVM.dealIntent$lambda$0()` 调用 `PictureDecoder.decodeSafely(url, 4096, 4096)` 读取本地图片，再调用 `handleRecResult(false)`。

`handleRecResult()` 经 `DocumentModule.detectBitmap()` 进入：

```text
DocumentProcess.detectBitmap()
→ doScanDocument(bitmap, DocumentType.DEFAULT)
→ nativeScanDocumentBitmap(nativeObj, bitmap, 0, float[8], 0)
```

结果是四个角的八个坐标值。Java 包装层对内部点序与 `RecognizeResult.quadrangleCorners` 点序进行了重排，移植时需要保留对应关系，不能直接假定两者顺序一致。

### 2.2 裁剪后立即生成彩色增强图

`DocCropVM.recognize()` 的关键操作：

1. 将输入复制为可修改的 `ARGB_8888`。
2. 调用 `DocumentModule.rectifyBitmap()` 获取校正图。
3. 再复制校正图，调用 `DocumentProcess.doEnhance(copy, EnhanceType.COLOR, false)`。
4. 分别保存校正图和增强图，传给滤镜页面。

`DocumentModule.rectifyBitmap()` 实际调用 `doCropAndEnhanceByEnhanceType(..., RAW, false)`，因此裁剪和增强在业务层上是可以分开的。

### 2.3 四种滤镜

`DocRecVM.initDocList()` 明确建立以下映射：

| 界面 | 枚举 | 传入 native 的序号 |
| --- | --- | --- |
| 原图 | `RAW` | 0 |
| 增强 | `COLOR` | 1 |
| 黑白 | `BIN` | 2 |
| 灰度 | `GRAY` | 3 |

截图中需要复现的是 `COLOR`，使用 `BIN` 会丢失彩色信息。

滤镜切换从保存的校正图复制后处理，避免在上一次滤镜结果上反复叠加。增强图已经在裁剪后预生成，进入页面时可直接显示。

## 3. 智能框选：神经网络检测配合几何后处理

### 已确认

文档检测模型使用 `hed_model` 标识，输入名为 `hed_input`，输出名为 `img_output`。构造函数常量与检测调用交叉对应到：

- 输入：`[1, 384, 384, 3]`。
- 输出：`[1, 384, 384, 2]`。
- 模型张量名称包含 `EdgeDet/MobilenetV1/...`。
- 两个输出分支包含 `pred_edge` 和 `pred_segment`。

因此它包含基于 MobileNetV1 的边缘、文档区域预测，不能归结为只用 Canny 找轮廓。

native 检测前处理包含缩放到 384×384、颜色转换及浮点数据准备。模型之后进入 `DocFinder.cpp` 对应的后处理，可见热图阈值、几何候选、线段与框选逻辑；库内还包含 Canny 和 `FastLineDetector` 路径。

### 仍需运行验证

所有候选的选择优先级、低置信度回退条件，以及弱边缘、复杂背景下的实际误检率，不能仅凭函数名或字符串量化。桌面端需匹配颜色通道顺序、坐标缩放、点序与后处理，不能只取神经网络输出的外接矩形。

## 4. 透视校正：四点映射与输出尺寸计算

native 裁剪主体位于 ELF 相对地址 `0x6c81c`。

已找到从四个点计算边长、估计目标宽高、建立目标四角坐标、计算透视矩阵并应用透视变换的调用链：

- `0x29ac34`：OpenCV `getPerspectiveTransform` 包装入口，函数断言和源路径可验证。
- `0x29a728`：透视变换实现，由裁剪辅助函数 `0x73900` 调用。

输出宽高并非单纯写死为 A4 比例；它结合角点几何和内部比例估计。截图中的横向手绘图也不适合无条件拉伸为竖向 A4。

透视变换能够校正平面纸张拍斜形成的梯形，但不能独立消除局部弯曲。

## 5. 彩色增强：模型估计与去光照归一化

### 5.1 native 模式分发

JNI `nativeEnhanceBitmap` 的 ELF 相对地址为 `0x67ef0`，通过文档模块的虚函数进入 `0x6d41c`。

`0x6d41c` 根据模式分发：

- `COLOR` 进入彩色增强，必要时先走曲面矫正。
- `BIN` 进入黑白处理。
- `GRAY` 使用灰度颜色转换。
- SDK 还保留身份证和去摩尔纹相关分支，不属于截图的四个按钮。

### 5.2 增强模型

构造函数 `0x8f238` 绑定：

| 项目 | 值 |
| --- | --- |
| 模型标识 | `enhance_model` |
| 输入 | `img_input` |
| 输出 | `img_output` |
| 包装层输入尺寸 | `[1, 512, 512, 3]` |
| 包装层输出尺寸 | `[1, 512, 512, 3]` |

模型张量包含 `inference/generator/...`、卷积和 `Tanh`。这些名称不足以证明训练方式，不能据此声称已恢复训练源码或确定它是某种 GAN。

彩色增强主体 `0x8dd2c` 包含输入图像统计、宽高比与尺寸分支、缩放/补边、512×512 模型推理，以及输出恢复到工作图尺寸的操作。模型输出不是简单直接作为最终扫描图保存。

### 5.3 去光照的核心计算

在 `rm_light` 分支中，native 构造 `LRmFast` 处理对象，对原图、模型推理后恢复尺寸的图以及目标图进行逐通道运算。

小图串行入口 `0x8d7a4` 的整数运算已经恢复。令 `I` 为原图当前通道值，`L` 为模型输出处理后的对应值：

- 当 `L = 0`，输出 255。
- 否则，输出为 `min(255, floor((255 × I + 765) / L))`。

其中 `765 = 255 × 3`，存在小幅正偏置。大图另有并行调度路径；串行实现和调度调用点均已保留在分析目录。

**算法含义的判断：**结合该除法、模型输出尺寸恢复以及 `rm_light` 日志，模型输出在这里充当背景/光照校正图。这是从数据流得到的判断；尚未通过输出可视化检查它具体预测的每个区域。

这一逐通道归一化可以同时减弱局部阴影和纸底偏色：若纸底三个通道都接近对应的背景估计，计算结果会接近 255；深色字迹和不同颜色的绘画会保留相对于背景的差异。

因此用户感受到的“白平衡、纸底变白”，至少有一部分由局部背景归一化实现。当前分析范围内，没有证据把独立的全局白平衡算法列为必经步骤。

### 5.4 Gamma 与对比度

去光照后调用 `0x8d94c`：

1. 建立 256 级 Gamma 查找表，形式为 `255 × (v / 255)^gamma`。
2. 调用 `0x8ce58`，即源断言中标识的 `enhanceBrightContrast` 逻辑。
3. 通过直方图、两端累计像素比例和目标动态范围计算线性拉伸。

已用 ARM64 浮点寄存器加载与数据区数值交叉确认：

| 分支 | Gamma | clipHistPercent | targetRangeRatio |
| --- | --- | --- | --- |
| 常规 `rm_light` 后处理 | 1.4 | 1.4 | 1.4 |
| 另一输入统计分支 | 1.1 | 1.4 | 1.9 |

这些是当前 SDK 特定分支的参数，不代表所有图片都只经过同一固定参数链。直方图统计还包含将大图缩到长边约 720 的路径，避免在完整分辨率上重复统计。

不能把库里存在的所有滤波、锐化、LUT 函数都列为当前彩色增强的必经步骤；本报告只列已追踪到的计算。

## 6. 曲面与褶皱：存在条件触发的两阶段路径

这里必须区分两个入口：

- 独立的 JNI `nativeDewarpBitmap`（`0x69118`）没有进行实际矫正，正常可用分支记录 `DewarpBitmap is Not Supported Now` 后返回。因此仅调用 Java `doDewarp()` 不能证明图像已展平。
- 增强模块内部 `0x6d41c` 包含另一条条件触发的曲面矫正路径。它根据检测几何的角度偏差、IoU 统计和文档判断选择是否执行。

内部曲面处理主体 `0x6e844` 调用两个模型：第一次 `0x91180(..., 0)`、第二次 `0x91180(..., 1)`。模型缓冲区指针可以分别对应到提取出的第三、第四份模型。后续包含网格采样、掩码/阈值及重映射处理，并记录 `Dewarp by two steps`。

因此，这个包确实包含神经网络曲面矫正能力，且集成在增强链路内。但触发依赖几何状态，不等于对任何照片无条件执行，更不等于保证严重折痕、遮挡、污渍覆盖文字都能恢复。

## 7. 本地与网络依赖

支持本地图像处理的证据：

- Java 扫描处理链直接调用 JNI，没有在这些步骤中提交 HTTP 处理任务。
- 检测、增强与曲面模型位于 `.so` 数据段中。
- SDK 初始化从应用传入缓存路径和空字符串；已追踪的模型加载进一步使用内嵌缓冲区。
- native 依赖 `AndroidBitmap`、MNN、OpenCV、OpenCL 与线程/文件操作。

`E-imports`：完整导入表位于 `analysis/native/imports.txt`，分类摘要位于 `analysis/native/import-summary.json`。其中已识别图像像素接口、OpenCL 计算、文件与线程接口，未见直接导入的 `socket/connect/send/recv/SSL/curl` 或 `dlopen/dlsym`。

导入表检查仅用于支持已追踪的本地图像链路，不用于证明整个应用完全不联网。应用还有其他识别和业务功能，本次未对其网络行为做整体审计。

`E-exports`：JNI 和工厂导出见 `analysis/native/exports.txt`；包括扫描、裁剪、增强、曲面与辅助接口。

## 8. 已提取模型

下列大小均由 native 尺寸字段、模型加载缓冲区指针和 FlatBuffer 张量名称交叉核对。

| 文件 | `.so` 文件偏移 | 字节数 | 张量名称数 | 用途 |
| --- | --- | --- | --- | --- |
| `document_detect.mnn` | `0x48b455` | 1,285,284 | 70 | 边缘/区域检测 |
| `document_enhance.mnn` | `0x5c5100` | 3,285,696 | 166 | 彩色增强的校正图预测 |
| `document_dewarp.mnn` | `0x8e73c4` | 1,369,752 | 118 | 曲面矫正第一阶段 |
| `document_dewarp_stage2.mnn` | `0xa35a60` | 2,685,196 | 212 | 曲面处理第二阶段 |

文件保存在 `analysis/models/`，摘要、尺寸、张量列表保存在 `manifest.json`。

提取结果通过了结构检查；**未执行 MNN 运行时加载与推理验证**。不能将“提取成功”等同于“已经在桌面复现扫描效果”。

## 9. 对电脑端实现的判断

### 推荐验证顺序

1. 用已提取的增强模型与同一张原始照片，先复现光照校正图、逐通道归一化、Gamma 和对比度。检查铅笔、浅黄色、彩笔及印章是否被误消除。
2. 接入检测模型和四角后处理，再实现透视校正。允许低置信度结果进入四角人工调整。
3. 再验证内部曲面模型、触发条件与两阶段重映射。完成算法对照后增加本地目录批量读取、预览和导出。

这不是重新训练模型的起点：已有可分析的模型和前后处理链。最终效果仍取决于模型是否能被桌面运行时正确加载，以及颜色顺序、输入范围、缩放插值、补边、尺寸恢复和整数舍入是否匹配。

Android `.so` 是 ARM64 ELF，依赖 Android 图像接口，不能直接作为 Windows 或 macOS 的普通动态库加载。桌面路线应运行模型并重建外围处理。MNN 官方文档提供 Python 接口及桌面平台运行支持，具体参见 [PyMNN 完整指南](https://mnn-docs.readthedocs.io/en/latest/start/python.html)。这只支持技术可行性判断，不证明当前四份模型已经通过桌面兼容测试。

### 效果边界

- 均匀泛黄、常见局部阴影：背景估计和逐通道校正是直接对应的处理机制，实际改善程度待样本测试。
- 严重污渍：若污渍与字迹具有相似颜色和纹理，不能保证去污与保字同时成立。
- 严重褶皱：几何展平和阴影消除是两项不同处理；即使展平，也可能保留折痕造成的遮挡或损伤。
- 浅色内容：白底增强可能误伤浅色铅笔和彩笔，需要单独验证。
- 原片失焦、过曝、遮挡：缺失的真实信息不能从这条静态链路推导出可靠恢复保证。

这些边界用于定义后续验收样本，不是对该 APK 效果的实测结论。

## 10. 证据与复现入口

路径均相对于项目目录。

| 证据 | 路径 |
| --- | --- |
| 资源与 Manifest | `analysis/apktool/` |
| Java/Kotlin 反编译 | `analysis/jadx/sources/com/xiaomi/` |
| native 原始副本 | `analysis/native/libDocumentProcess.so` |
| 导入/导出/段信息 | `analysis/native/imports.txt`、`exports.txt`、`sections.txt` |
| native 字符串 | `analysis/native/rodata-strings.txt` |
| Ghidra 函数反编译 | `analysis/native/decompiled/` |
| 函数清单 | `analysis/native/decompiled/index.tsv` |
| 核心交叉引用 | `analysis/native/decompiled/core-crossrefs.tsv` |
| Gamma 参数的指令证据 | `analysis/native/color-postprocess-disassembly.txt` |
| 模型与摘要 | `analysis/models/` |
| 可重跑提取脚本 | `analysis/scripts/extract_models.py` |
| Ghidra 导出脚本 | `analysis/scripts/ExportScanner.java`、`VerifyCore.java` |
| Ghidra 项目 | `analysis/ghidra/Scanner.gpr` |

Ghidra 自动选择的 image base 为 `0x100000`。例如导出的 `0018dd2c.c` 对应 ELF 相对地址 `0x8dd2c`；模型表中列的是文件偏移，不要混用。

重跑模型提取：

```bash
cd /Users/gouwei/Desktop/sinar/saomiao
python3 analysis/scripts/extract_models.py
```

脚本在提取前校验 APK SHA-256，防止另一版本 APK 错套当前偏移。

### 本次验证状态

- [x] 核对 APK 身份、摘要、入口与截图资源。
- [x] 追踪框选、裁剪、滤镜、PDF 保存链。
- [x] 保存 native 导入与导出证据。
- [x] 追踪检测、增强、曲面处理的关键函数与调用。
- [x] 用指令和数据区核对 Gamma 等数值。
- [x] 提取四份内嵌模型，核对尺寸字段、指针及张量名称。
- [ ] 桌面 MNN 运行时加载与真实推理。
- [ ] 手机与桌面使用同一原图的阶段输出对照。
- [ ] 去阴影、保色、浅色内容与褶皱的样本验收。
