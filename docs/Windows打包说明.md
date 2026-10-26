# Windows 便携版

## 使用

当前精简版分发文件：`dist/纸页扫描-Windows-x64-精简版.zip`，同时包含 GUI 和命令行入口。

完整解压后双击“纸页扫描.exe”。程序包含 Python、Qt、MNN、图像处理库及四份模型，无需朋友另装 Python。图片处理在本机执行。不要只发送 exe，也不要直接在压缩包中运行。

目标系统为 Windows 10 1903 及更新版本、Windows 11，x64。启动异常时运行“运行自检.cmd”，日志在 `%LOCALAPPDATA%\PaperScanner\logs\startup.log`，自检结果在 `%TEMP%\PaperScannerCheck`。

### 命令行批处理

便携包同时包含 `纸页扫描-cli.exe`，适合脚本和智能体调用；不显示图形界面，处理完成后返回退出码：

```bat
纸页扫描-cli.exe -i "D:\photo" -o "E:\output" -s 90 -e 50 --json --quiet > result.json 2> processing.log
```

原来的 `纸页扫描.exe` 带相同参数也可处理；交互式终端调用 GUI 程序时可能提前返回提示符，自动化推荐使用控制台入口。完整参数、JSON 字段和退出码见[命令行使用说明](命令行使用说明.md)，该文档也随便携包分发。

## 实现

- 使用 CPython 3.12.10 官方 Windows amd64 嵌入式运行时，固定六份 Windows wheel 版本。
- 使用 Zig 从同一份 C 源码交叉编译 GUI、控制台两个启动器，在同一进程载入 `python312.dll` 并调用 `Py_Main`，通过 `python312._pth` 定位本地应用和依赖。
- exe 清单启用 UTF-8，避免 MNN Windows 文件加载代码采用 `CP_ACP` 时误解中文模型路径；不修改系统区域或全局编码设置。
- 显式配置本地 DLL 和 Qt 插件路径，包含 VC++ 运行库，移除应用未使用的 QML、数据库、设计器插件及 MNN 转换工具。
- 命令行保留父进程传入的 stdout / stderr，缺少句柄时尝试连接父控制台；启动异常写入 stderr 并返回 1。图形模式继续记录启动日志并显示错误弹窗。
- 分享包只包含程序、运行依赖、模型及合成自检样例，不包含 APK、逆向分析材料、用户照片或开发环境。

## 复现构建

当前打包默认使用精简 OpenCV，需先按[打包体积优化](打包体积优化.md)准备源码、构建工具和 Python SDK，执行 `scripts/build_opencv_minimal.py --target windows-x64`。缺少精简构建时打包会停止。下列嵌入式运行时和 wheel 仍作为固定输入使用，通用 OpenCV 扩展会在组装时被替换。

构建脚本使用本项目开发环境中的 Pillow，另需构建工具 `ziglang==0.17.0`、`pefile==2024.8.26`；它们不会加入用户运行包。

缓存目录为 `artifacts/windows-build`，需要以下输入：

1. `python-3.12.10-verified.zip`：官方 `python-3.12.10-embed-amd64.zip` 的完整副本；脚本核对官方 MD5 `fe8ef205f2e9c3ba44d0cf9954e1abd3`。
2. `wheels/`：MNN 3.6.1、NumPy 2.4.6、opencv-python-headless 5.0.0.93、Pillow 13.0.0、PySide6-Essentials 6.12.0、shiboken6 6.12.0，全部为 Windows amd64 且兼容 CPython 3.12。

依次执行：

```bash
.venv/bin/python scripts/build_windows_portable.py
.venv/bin/python scripts/check_windows_portable.py
```

构建程序复制源码、模型和命令行文档，重新编译两个启动器并组装目录。核查脚本验证全部 PE 文件为 x64、导入 DLL 可从配置目录或系统解析、GUI 与控制台子系统、UTF-8 清单、Python 入口、源码和文档一致性、四模型校验值及标准库 ZIP 完整性。核查记录写入 `build-info.json` 和构建缓存中的 `pe-dependencies.json`。

将生成目录压缩为同名 ZIP，保留顶层文件夹。压缩包文件名采用 UTF-8，解压时须保留全部子目录。

## 本轮验证与限制

- 在 macOS arm64 的 Python 3.12.13 环境运行同版本应用依赖，21 项测试通过；四模型、真实界面线程、50% 缩放及 0.2 MB 导出自检通过。
- Windows 包完成二进制与资源静态核查，ZIP 完整性另行检查。
- 当前没有可用的 Windows 主机，尚未进行原生 Windows 的启动、交互及图片处理验收。Mac 上的测试不能证明 Windows 运行结果。

## Windows 11 箭头缺失修复（2026-10-26）

本次修复包：`dist/纸页扫描-Windows-x64-箭头修复.zip`，完整解压后使用。

数字输入框的上下箭头、分辨率和格式下拉箭头曾依赖 Qt 默认绘制。界面已设置边框、背景和下拉按钮等局部 QSS，默认箭头与自定义样式混用时出现空白或残缺；在本地 Qt 6.12 的 Fusion 样式下可复现。

`paper_scanner/ui.py` 现在明确指定箭头图片、按钮位置、尺寸和输入区右边距，并处理禁用、最小值、最大值、悬停和按下状态。四份 PNG 位于 `paper_scanner/assets/`，通过 Qt 搜索路径载入；Windows 构建随源码复制，macOS 构建也显式包含该目录，不依赖字体符号或 SVG 插件。

验证命令：

```bash
.venv/bin/python -m pytest -q
QT_SCALE_FACTOR=1.5 .venv/bin/python -m pytest -q tests/test_ui_controls.py
QT_SCALE_FACTOR=2 .venv/bin/python -m pytest -q tests/test_ui_controls.py
```

本次全量 41 项测试通过。新增 6 项控件检查覆盖 Fusion、Windows 两种 Qt 基础样式下的实际箭头像素、点击增减、边界禁用和下拉选择，并检查 100%、150%、200% 缩放。界面截图保存在 `artifacts/Windows箭头修复-设置面板.png`。这些验证在 macOS 的 offscreen 平台完成，Windows 11 实机显示仍需验收。

## 无界面命令行（2026-10-26）

新增 `paper_scanner/cli.py`，使用与界面相同的扫描、增强、展平和导出实现。原 GUI 入口保持双击启动界面；新增控制台入口，支持 JSON、CSV、退出码及单张失败后继续处理。JSON 模式同时重定向 Python、CRT 和 Win32 标准输出，避免模型诊断混入结果。

macOS arm64、Python 3.11.15 开发环境下，29 项命令行测试及全量 107 项测试通过。实际执行 `-s 90 -e 50 --json --quiet` 后，样本导出为 1498×1016、569557 字节，JSON 可独立解析，CSV 记录正常；证据保存在 `artifacts/命令行功能验证/`。该尺寸和体积仅对应当前样本与参数。

本次已重新构建两个 Windows x64 启动器，并核查源码、模型、文档、依赖、PE 子系统和 UTF-8 清单。Windows 实机运行尚未执行，尤其需要验收终端连接、stdout / stderr 重定向、退出码与 Ctrl+C。

## 依据

- [Python 3.12.10 官方发布与运行时校验值](https://www.python.org/downloads/release/python-31210/)
- [Python Windows 嵌入式发行包](https://docs.python.org/3.12/using/windows.html#the-embeddable-package)
- [Microsoft：应用 UTF-8 代码页清单](https://learn.microsoft.com/en-us/windows/apps/design/globalizing/use-utf8-code-page)
- [Qt 6.12 Windows 平台要求](https://doc.qt.io/qt-6.12/windows.html)
- [Microsoft：Windows 内置 ICU 组件](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-)
- [Microsoft：标准句柄、重定向与 GUI 进程控制台](https://learn.microsoft.com/en-us/windows/console/getstdhandle)
- [Microsoft：start 的等待选项](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/start)
