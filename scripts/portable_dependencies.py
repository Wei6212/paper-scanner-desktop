"""裁剪便携包中的开发资料和未使用模块，保留运行时依赖闭包。"""
import hashlib
import json
from pathlib import Path
import shutil


def minimal_opencv(directory: Path, target: str):
    manifest_path = directory / 'opencv-build.json'
    if not manifest_path.is_file():
        raise ValueError(f'缺少精简 OpenCV，请先运行 scripts/build_opencv_minimal.py：{directory}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['target'] != target or manifest['modules'] != ['core', 'flann', 'geometry', 'imgproc', 'python3']:
        raise ValueError(f'精简 OpenCV 平台或模块不匹配：{manifest_path}')
    expected_name = 'cv2.pyd' if target == 'windows-x64' else 'cv2.abi3.so'
    if manifest['extension'] != expected_name:
        raise ValueError(f'精简 OpenCV 文件名异常：{manifest_path}')
    extension = directory / expected_name
    if hashlib.sha256(extension.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError(f'精简 OpenCV 校验失败：{extension}')
    if not all((directory / name).is_file() for name in ('OpenCV-LICENSE.txt', 'OpenCV-NOTICES.txt', 'zlib-LICENSE.txt')):
        raise ValueError('精简 OpenCV 缺少许可文件')
    return extension, manifest


def imported_dlls(path: Path) -> set[str]:
    import pefile

    with pefile.PE(str(path), fast_load=True) as binary:
        binary.parse_data_directories(directories=[1, 13])
        return {entry.dll.decode('ascii').lower()
                for kind in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                for entry in getattr(binary, kind, [])}


def prune_windows_dependencies(site: Path):
    qt = site / 'PySide6'
    plugins = qt / 'plugins'
    for directory in plugins.iterdir():
        if directory.is_dir() and directory.name not in {'platforms', 'imageformats', 'iconengines', 'styles'}:
            shutil.rmtree(directory)
    (plugins / 'imageformats/qpdf.dll').unlink(missing_ok=True)
    for path in (plugins / 'platforms').glob('*.dll'):
        if path.name not in {'qwindows.dll', 'qoffscreen.dll', 'qminimal.dll'}:
            path.unlink()

    # 插件也可能引入 Qt 模块；按 PE 导入递归保留，避免只按业务 import 删 DLL。
    local = {path.name.lower(): path for path in qt.glob('*.dll')}
    pending = [qt / f'{name}.pyd' for name in ('QtCore', 'QtGui', 'QtWidgets')]
    pending += list(plugins.rglob('*.dll'))
    # 此库由 Qt 动态加载，保留低配置显卡的软件渲染回退。
    pending.append(qt / 'opengl32sw.dll')
    kept = set()
    while pending:
        path = pending.pop()
        if path in kept:
            continue
        if not path.is_file():
            raise ValueError(f'缺少 Qt 运行资源：{path}')
        kept.add(path)
        pending.extend(local[name] for name in imported_dlls(path) if name in local)
    for path in qt.iterdir():
        if path.is_dir():
            if path.name not in {'plugins', 'support'}:
                shutil.rmtree(path)
        elif path.suffix.lower() in {'.dll', '.pyd'}:
            if path not in kept:
                path.unlink()
        elif path.suffix not in {'.py', '.typed'}:
            path.unlink()

    # NumPy 的测试套件不参与扫描；保留 numpy.testing，避免破坏公共运行接口。
    for path in sorted((site / 'numpy').rglob('tests'), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
    # 产品支持的输入与输出均不包含 AVIF，Pillow 会跳过缺失的格式插件。
    for pattern in ('_avif*.pyd', 'AvifImagePlugin.py'):
        for path in (site / 'PIL').glob(pattern):
            path.unlink()
    for directory in ('include', 'lib'):
        shutil.rmtree(site / 'shiboken6' / directory, ignore_errors=True)
    for package in ('PySide6', 'shiboken6'):
        for path in (site / package).rglob('*.pyi'):
            path.unlink()
