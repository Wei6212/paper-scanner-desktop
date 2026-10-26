# 纸页扫描：AI 项目说明

本文供维护代码或调用程序处理图片的 AI 阅读。仓库约定见 [AGENTS.md](AGENTS.md)，用户功能介绍见 [README.md](README.md)。项目实际行为以当前源码和测试为准，历史验证记录不能替代本次任务的验证。

## 项目用途与边界

这是本地文档扫描桌面工具，使用 Python、PySide6、MNN、OpenCV、NumPy 和 Pillow。图片在本机完成处理，无需上传服务器。

提供两种使用方式：

- 桌面界面：导入图片、预览、手动调整四角、旋转和批量导出。
- 命令行：自动检测纸张、透视校正、彩色增强、可选曲面展平、缩放与批量导出，适合脚本和智能体调用。

输入支持 JPEG、PNG、BMP、TIFF、WebP，TIFF 只读取第一页。输出支持 JPEG、PNG，不支持 PDF 输入或导出，也没有 OCR 接口。原图和既有结果不覆盖，导出时重新编码，不保留原始 EXIF 等元数据。

如果任务仅要求扫描或转换图片，优先调用现有 CLI，不需要修改项目代码。不要将文件整理理解为删除或移动原图；CLI 只读取输入并写出结果。

## 按任务查找代码

| 文件或目录 | 职责 |
| --- | --- |
| `main.py` | 启动分流：无参数打开 GUI；保留 `--self-test` 自检；其他参数进入 CLI |
| `paper_scanner/cli.py` | 参数校验、输入枚举、顺序批处理、JSON / CSV 和退出码 |
| `paper_scanner/ui.py` | PySide6 窗口、图片画布、四角调整、界面设置和导出交互 |
| `paper_scanner/jobs.py` | GUI 的 `QThread` 后台队列、进度信号、取消和 CSV 记录 |
| `paper_scanner/engine.py` | `Scanner`、`ScanOptions`、模型加载、读取、检测、透视校正、增强和展平 |
| `paper_scanner/edges.py` | 纸边背景精修与内容保护 |
| `paper_scanner/exporting.py` | `ExportOptions`、尺寸计算、编码、体积限制和不覆盖保存 |
| `paper_scanner/thumbnails.py` | 队列缩略图处理 |
| `paper_scanner/selfcheck.py` | 打包后的界面、模型和导出自检 |
| `paper_scanner/assets/` | Qt 控件箭头等界面资源 |
| `models/` | 检测、增强、两阶段曲面展平，共四份 `.mnn` 模型 |
| `tests/` | 引擎、导出、纸边、画布、控件、缩略图及 CLI 测试 |
| `scripts/build_app.py` | macOS 应用打包 |
| `scripts/build_opencv_minimal.py` | 为 macOS / Windows 构建精简 OpenCV，不覆盖开发环境 |
| `scripts/portable_dependencies.py` | 精简扩展校验、Windows Qt DLL 依赖闭包及非运行资源裁剪 |
| `scripts/build_windows_portable.py` | Windows x64 便携包组装与两个入口的交叉编译 |
| `scripts/windows/launcher.c` | Windows 启动器，在当前进程加载嵌入式 Python 并传递参数 |
| `scripts/windows/launch.py` | Windows 本地 DLL、Qt 路径、日志和异常处理 |
| `scripts/check_windows_portable.py` | Windows 包 PE、依赖、清单、源码、文档和模型静态核查 |
| `scripts/smoke_ui.py` | 实际 GUI 与后台队列流程检查 |
| `scripts/verify_models.py` | 真实模型推理及中间结果检查 |
| `docs/` | 调用说明、打包说明、实现与验证记录 |

## 开发环境与常用命令

Python 要求为 `>=3.11,<3.13`，依赖声明在 `pyproject.toml`，锁定结果在 `uv.lock`。不要无理由升级依赖或重写锁文件。

已安装 `uv` 时，在仓库根目录创建或同步开发环境：

```bash
uv sync --frozen
```

已有可用 `.venv` 时直接使用；同步环境会安装依赖，并可能移除环境中未声明的包，不要为了阅读项目而重新同步。

macOS / Linux 开发环境中的常用命令：

```bash
.venv/bin/python main.py
.venv/bin/python main.py --help
.venv/bin/python -m pytest -q tests/test_cli.py
.venv/bin/python -m pytest -q
git diff --check
```

Windows 开发环境将 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。Windows 用户便携版自带运行时，无需安装开发环境。测试覆盖范围和是否能运行，还取决于当前平台可用的 MNN、Qt 依赖。

## AI 如何调用命令行

### Windows 便携版

在完整解压的便携包目录执行：

```bat
纸页扫描-cli.exe -i "D:\photo" -o "E:\output" -s 90 -e 50 --json --quiet
```

`纸页扫描-cli.exe` 为控制台入口，便于调用方等待完成并捕获结果；不带参数显示帮助。`纸页扫描.exe` 带同样参数也可批处理，不带参数打开界面。两个入口必须与 `app`、`runtime` 目录一起保留。

### 源码调用

在配置好依赖的仓库根目录执行：

```bash
.venv/bin/python main.py -i ./samples -o ./artifacts/AI调用结果 -s 90 -e 50 --json --quiet
```

调用时遵守以下约定：

1. 用参数列表启动进程，避免把路径拼成 shell 命令；等待进程结束，并分别捕获 stdout 与 stderr。
2. 添加 `--json` 后，从 UTF-8 stdout 读取一份 JSON；进度和模型诊断在 stderr，不要合并两个流。`--quiet` 不保证诊断流为空。
3. 同时检查进程退出码和 JSON 中的结果。部分成功会返回 1，已导出的文件仍然有效。
4. 读取 `files` 中的实际输出路径，不要按输入名称推算，因为同名文件会自动编号，扩展名也可能改变。
5. 不重复执行整批任务来查询结果；再次执行会重新导出并创建新编号的文件。

| 参数或行为 | 约定 |
| --- | --- |
| `-i` / `-o` | 输入图片或目录、输出目录，均必填 |
| `-s 90` | 按校正后宽高的 90% 导出，范围 1～200，默认 100 |
| `-e 50` | 增强强度 50%，范围 0～100，默认 100 |
| `--black-white` | 在校正与增强之后转纯黑白，默认关闭；不受 `-e 0` 影响 |
| `--black-threshold 180` | 灰度低于阈值转黑，其余转白；整数 1～255，默认 180 |
| `--stroke-radius 1` | 黑白模式的笔画加粗半径，整数 0～3 像素；0 不加粗，默认 1 |
| `--no-crop -e 0` | 关闭检测裁剪与增强，适合单纯缩放或转换格式 |
| `--width` / `--height` | 等比例适配最大宽高，不能与 `-s` 同用 |
| `-r` / `--recursive` | 包含子目录，默认只处理当前层 |
| `--max-mb` | 以实际字节数限制单张体积，必要时降低 JPEG 质量并缩图 |
| `--dewarp` | 开启曲面展平，默认关闭 |
| 输出位置 | 不能与输入目录相同；可以放在输入目录下面，扫描时自动排除 |

JSON 协议版本为 `schema_version: 1`。顶层包含 `status`、`exit_code`、`total`、`succeeded`、`failed`、`files`、`record`、`error`。

| 退出码 | 含义 |
| --- | --- |
| 0 | 图片全部成功，或正常显示帮助 |
| 1 | 图片部分或全部失败、记录写入失败、运行异常 |
| 2 | 参数或输入错误，包括没有支持的图片 |
| 130 | 用户中断，已完成结果保留 |

Windows 运行时缺失等 Python 启动前错误可能仅返回 stderr 和退出码 1；调用方需要处理 stdout 为空或无法解析的情况。所有参数、字段含义及完整 Python 示例见 [命令行使用说明](docs/命令行使用说明.md)。

## 修改实现时需要保持的约束

- `Scanner` 记录创建线程，只能在该线程使用。GUI 经 `Worker` 后台处理，CLI 在当前线程顺序处理，不要跨线程共享引擎实例。
- 处理算法修改放在 `engine.py` / `edges.py`，尺寸、编码、保存修改放在 `exporting.py`；GUI 和 CLI 直接复用，不复制另一套算法。
- 黑白文字使用 `engine.binarize_text`，输出 Pillow `1` 模式；PNG 缩放后重新二值化，JPEG 不保证纯黑白。加粗半径作用于校正后完整分辨率，不能推断完全缺失的笔画。
- CLI 不导入 GUI，不创建 `QApplication`；`--help` 不应加载 Qt、OpenCV 或模型。
- JSON 模式隔离 Python 及原生依赖的 stdout，包括解释器退出时的缓冲日志；新增日志应写入 stderr。
- `save_unique` 使用排他创建和临时文件替换。不要改成覆盖写入；异常和 Ctrl+C 时应清理当前未完成的输出。
- 输入限制为边长最多 30000 像素、总像素最多 8000 万，输出也有总像素限制。不要移除尺寸检查或文件体积检查。
- 无法可靠识别纸边、曲面模型输出不合理时，应遵循引擎现有降级和提示逻辑，不编造识别结果。
- 打包时保留四份模型、Qt 必需资源和源码的相对位置；修改 Windows 入口时同时考虑 GUI、CLI、自检及中文路径。

## 验证与交付

按改动范围选择验证：CLI 参数、协议或批处理改动运行 `tests/test_cli.py`；处理引擎、导出或界面改动运行对应测试，影响较广时运行全量测试。模型相关测试会执行本地真实模型，不要把模拟结果当成推理验证。

Windows 构建需要额外构建工具和缓存输入，不能只凭当前 `.venv` 就假定齐全。具体准备步骤见 [Windows 打包说明](docs/Windows打包说明.md)。构建及核查命令：

```bash
.venv/bin/python scripts/build_windows_portable.py
.venv/bin/python scripts/check_windows_portable.py
```

两个平台打包前都需按 [打包体积优化](docs/打包体积优化.md)构建对应平台的精简 OpenCV；缺少或校验失败时停止，不回退到通用版。构建脚本重新生成 `dist/纸页扫描-Windows-x64/`，会替换该生成目录；不要在其中保存需要保留的用户数据。`check_windows_portable.py` 为静态检查，不执行 Windows 程序。macOS 包使用 `scripts/build_app.py`，构建同样会更新生成产物。

提交应包含代码、必要测试和对应文档。`dist/`、`artifacts/`、`.venv/`、`build/` 等生成目录不进入 Git；便携包的分发与源码推送是不同操作。

交付时说明改动位置、影响范围、实际执行的验证及未验证的平台。2026-10-26 的开发验证记录为 macOS arm64 上 107 项测试通过，其中 CLI 测试 29 项；Windows 包完成静态核查，尚未进行 Windows 实机验收。后续修改应以新的验证结果为准。
