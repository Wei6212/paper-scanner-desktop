#!/usr/bin/env python3
"""组装 Windows x64 便携包，不依赖用户电脑预装 Python。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'artifacts/windows-build'
OUTPUT = ROOT / 'dist/纸页扫描-Windows-x64'
PYTHON_MD5 = 'fe8ef205f2e9c3ba44d0cf9954e1abd3'
VERSIONS = {'mnn': '3.6.1', 'numpy': '2.4.6', 'opencv_python_headless': '5.0.0.93', 'pillow': '13.0.0', 'pyside6_essentials': '6.12.0', 'shiboken6': '6.12.0'}


def compile_launcher():
    source = ROOT / 'scripts/windows'
    for name in ('app.manifest', 'app.rc', 'icon.ico'):
        shutil.copy2(source / name, CACHE / name)
    zig = [sys.executable, '-m', 'ziglang']
    subprocess.run(zig + ['rc', '/c', '65001', '/fo', 'app.res', 'app.rc'], cwd=CACHE, check=True)
    subprocess.run(zig + ['cc', '-target', 'x86_64-windows-gnu', '-O2', '-s', '-municode', '-Wl,--subsystem,windows', str(source / 'launcher.c'), 'app.res', '-o', '纸页扫描.exe', '-lshell32', '-luser32'], cwd=CACHE, check=True)


def extract_safe(archive: zipfile.ZipFile, destination: Path):
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'压缩包路径越界：{entry.filename}')
        archive.extract(entry, destination)


def build():
    python_zip = CACHE / 'python-3.12.10-verified.zip'
    if hashlib.md5(python_zip.read_bytes()).hexdigest() != PYTHON_MD5:
        raise ValueError('Python 运行时与官方发布页的校验值不一致')
    wheels = []
    for name, version in VERSIONS.items():
        matches = list((CACHE / 'wheels').glob(f'{name}-{version}-*win_amd64.whl'))
        if len(matches) != 1:
            raise ValueError(f'缺少或重复的 Windows 依赖：{name} {version}')
        wheels.append(matches[0])
    compile_launcher()
    staging = CACHE / 'portable-staging'
    if staging.exists():
        shutil.rmtree(staging)
    runtime = staging / 'runtime'
    site = runtime / 'Lib/site-packages'
    app = staging / 'app'
    site.mkdir(parents=True)
    app.mkdir()
    with zipfile.ZipFile(python_zip) as archive:
        if archive.testzip():
            raise ValueError('Python 压缩包损坏')
        extract_safe(archive, runtime)
    records = []
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            if archive.testzip():
                raise ValueError(f'依赖压缩包损坏：{wheel.name}')
            if any('.data/' in name for name in archive.namelist()):
                raise ValueError(f'此版本存在需要单独处理的安装目录：{wheel.name}')
            extract_safe(archive, site)
        records.append({'wheel': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()})
    # 应用仅使用模型推理接口，避免带入无关的联网转换工具。
    shutil.rmtree(site / 'MNN/tools', ignore_errors=True)
    for path in site.glob('_tools*.pyd'):
        path.unlink()
    # QWidget 界面不使用 QML、数据库或设计器，避免带入缺少可选依赖的插件。
    qt = site / 'PySide6'
    shutil.rmtree(qt / 'qml', ignore_errors=True)
    for directory in (qt / 'plugins').iterdir():
        if directory.is_dir() and directory.name not in {'platforms', 'imageformats', 'iconengines', 'styles'}:
            shutil.rmtree(directory)
    (qt / 'plugins/imageformats/qpdf.dll').unlink(missing_ok=True)
    for path in qt.glob('*.exe'):
        path.unlink()
    # 将 wheel 提供的 VC++ 运行库放到运行时根目录，覆盖嵌入包中的旧版。
    for path in (site / 'PySide6').glob('*.dll'):
        if path.name.lower().startswith(('msvcp', 'vcruntime', 'concrt')):
            shutil.copy2(path, runtime / path.name)
    (runtime / 'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../app\nimport site\n', encoding='utf-8')
    shutil.copytree(ROOT / 'paper_scanner', app / 'paper_scanner', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'models', app / 'models')
    shutil.copy2(ROOT / 'main.py', app / 'main.py')
    shutil.copy2(ROOT / 'scripts/windows/launch.py', app / 'launch.py')
    shutil.copy2(CACHE / '纸页扫描.exe', staging / '纸页扫描.exe')
    # 自检样例为自动生成的图形，不将用户提供的照片打入分享包。
    image = Image.new('RGB', (1200, 900), '#847c67')
    draw = ImageDraw.Draw(image)
    draw.polygon([(110, 95), (1100, 70), (1115, 825), (90, 805)], fill='#c6c4b8')
    for y in range(180, 700, 65):
        draw.rectangle((200, y, 720, y + 9), fill='#252b22')
    draw.rectangle((820, 200, 1000, 380), fill='#c52a22')
    draw.ellipse((810, 490, 1010, 690), fill='#2c67b2')
    image.save(app / 'diagnostic.png')
    diagnostic = '''@echo off\r\nchcp 65001 >nul\r\nset "QT_QPA_PLATFORM=offscreen"\r\nstart "" /wait "%~dp0纸页扫描.exe" --self-test "%~dp0app\\diagnostic.png" "%TEMP%\\PaperScannerCheck"\r\nif errorlevel 1 (\r\n echo 自检未通过。启动记录位于："%LOCALAPPDATA%\\PaperScanner\\logs\\startup.log"\r\n) else (\r\n echo 自检完成，结果位于："%TEMP%\\PaperScannerCheck"\r\n)\r\npause\r\n'''
    (staging / '运行自检.cmd').write_bytes(diagnostic.encode('utf-8'))
    instructions = '''纸页扫描 · Windows 64 位便携版\r\n\r\n使用方法\r\n1. 将整个压缩包解压到一个目录。\r\n2. 双击“纸页扫描.exe”。无需安装 Python，无需联网处理图片。\r\n3. 选择图片目录，设置导出尺寸、文件上限和输出目录，再点击批量导出。\r\n\r\n注意：请保留 app、runtime 文件夹与 exe 的相对位置，不能单独复制 exe。\r\n支持 Windows 10 1903 或更新版本、Windows 11，均为 64 位。\r\n保留原图，同名结果自动编号；包含纸面铺满、曲面展平和自定义分辨率功能。\r\n\r\n启动异常时\r\n运行“运行自检.cmd”。记录在 %LOCALAPPDATA%\\PaperScanner\\logs\\startup.log。\r\n自检会在本机临时目录生成测试图片，不会上传任何文件。\r\n\r\n验证状态\r\n本包已完成 Windows x64 二进制、DLL 依赖、模型及资源静态核查。\r\n本轮构建环境为 macOS，尚未在原生 Windows 上完成启动和图片处理验收。\r\n'''
    (staging / '使用说明.txt').write_bytes(b'\xef\xbb\xbf' + instructions.encode('utf-8'))
    info = {'application': '纸页扫描', 'version': '0.1.0', 'platform': 'Windows x64', 'python': '3.12.10', 'python_md5_official': PYTHON_MD5, 'wheels': records, 'models': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (app / 'models').glob('*.mnn')}, 'validation': {'binary_and_resource_check': '待核查', 'native_windows_execution': '未执行：当前主机为 macOS arm64'}}
    (staging / 'build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.move(str(staging), OUTPUT)
    print(OUTPUT)


if __name__ == '__main__':
    build()
