#!/usr/bin/env python3
"""离线核查 Windows 便携包，不将静态检查当作 Windows 运行验收。"""
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'dist/纸页扫描-Windows-x64'
SYSTEM_DLLS = set('''advapi32 authz bcrypt cabinet comdlg32 crypt32 d2d1 d3d11
d3d12 d3d9 d3dcompiler_47 dnsapi dwmapi dwrite dxgi gdi32 icuuc imagehlp
imm32 iphlpapi kernel32 mpr mscms msi msvcrt ncrypt netapi32 ntdll odbc32
ole32 oleaut32 propsys psapi rpcrt4 secur32 setupapi shell32 shlwapi
uiautomationcore user32 userenv uxtheme version winhttp winmm ws2_32
wtsapi32'''.split())


def is_system(name):
    return (name.startswith(('api-ms-win-', 'ext-ms-win-'))
            or name == 'winspool.drv'
            or name.removesuffix('.dll') in SYSTEM_DLLS)


def check():
    runtime = PACKAGE / 'runtime'
    site = runtime / 'Lib/site-packages'
    required = [PACKAGE / '纸页扫描.exe', PACKAGE / '纸页扫描-cli.exe',
                PACKAGE / '命令行使用说明.md', PACKAGE / 'app/paper_scanner/cli.py', runtime / 'python312.dll',
                runtime / 'python3.dll', runtime / 'python312.zip',
                site / 'cv2.pyd', site / 'OpenCV-LICENSE.txt', site / 'OpenCV-NOTICES.txt', site / 'zlib-LICENSE.txt',
                site / '_mnncengine.cp312-win_amd64.pyd',
                site / 'PySide6/plugins/platforms/qwindows.dll',
                site / 'PySide6/plugins/platforms/qoffscreen.dll',
                PACKAGE / 'app/main.py', PACKAGE / 'app/launch.py',
                PACKAGE / 'app/diagnostic.png']
    for path in required:
        if not path.is_file():
            raise ValueError(f'缺少资源：{path}')
    pth = (runtime / 'python312._pth').read_text().splitlines()
    assert pth == ['python312.zip', '.', 'Lib/site-packages', '../app', 'import site']
    with zipfile.ZipFile(runtime / 'python312.zip') as archive:
        assert archive.testzip() is None
        assert 'encodings/__init__.pyc' in archive.namelist()
    for source in (ROOT / 'paper_scanner').glob('*.py'):
        assert source.read_bytes() == (PACKAGE / 'app/paper_scanner' / source.name).read_bytes()
    for source in (ROOT / 'paper_scanner/assets').glob('*.png'):
        assert source.read_bytes() == (PACKAGE / 'app/paper_scanner/assets' / source.name).read_bytes()
    assert (ROOT / 'main.py').read_bytes() == (PACKAGE / 'app/main.py').read_bytes()
    assert (ROOT / 'scripts/windows/launch.py').read_bytes() == (PACKAGE / 'app/launch.py').read_bytes()
    assert (ROOT / 'docs/命令行使用说明.md').read_bytes() == (PACKAGE / '命令行使用说明.md').read_bytes()
    for path in (PACKAGE / 'app').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    info_path = PACKAGE / 'build-info.json'
    info = json.loads(info_path.read_text())
    opencv = info['opencv_minimal']
    assert opencv['target'] == 'windows-x64'
    assert opencv['modules'] == ['core', 'flann', 'geometry', 'imgproc', 'python3']
    assert hashlib.sha256((site / 'cv2.pyd').read_bytes()).hexdigest() == opencv['sha256']
    assert not (site / 'cv2').exists(), '仍带入通用 OpenCV 包'
    assert not list(site.rglob('*ffmpeg*')), '仍带入视频编解码库'
    assert not list((site / 'PIL').glob('_avif*.pyd')), '仍带入 AVIF 扩展'
    for name in ('QtQuick.pyd', 'QtQml.pyd', 'QtDesigner.pyd', 'Qt6Quick.dll', 'Qt6Qml.dll'):
        assert not (site / 'PySide6' / name).exists(), f'仍带入未使用的 Qt 模块：{name}'
    assert len(info['models']) == 4
    for name, expected in info['models'].items():
        model = PACKAGE / 'app/models' / name
        assert hashlib.sha256(model.read_bytes()).hexdigest() == expected
        assert model.read_bytes() == (ROOT / 'models' / name).read_bytes()
    files = [p for p in PACKAGE.rglob('*') if p.is_file()]
    assert not any(p.suffix in {'.apk', '.dylib', '.so'} or p.name == '.DS_Store' for p in files)
    assert not (site / 'MNN/tools').exists()
    search_dirs = [runtime, site, site / 'PySide6', site / 'shiboken6',
                   site / 'numpy.libs']
    report = []
    for path in files:
        if path.suffix.lower() not in {'.exe', '.dll', '.pyd'}:
            continue
        pe = pefile.PE(str(path), fast_load=False)
        assert pe.FILE_HEADER.Machine == 0x8664, f'并非 x64：{path}'
        imports = {entry.dll.decode('ascii').lower()
                   for kind in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                   for entry in getattr(pe, kind, [])}
        local = {p.name.lower() for directory in [path.parent, *search_dirs]
                 for p in directory.iterdir() if p.is_file()}
        missing = sorted(name for name in imports if name not in local and not is_system(name))
        assert not missing, f'{path.relative_to(PACKAGE)} 缺少 DLL：{missing}'
        if path.name in {'纸页扫描.exe', '纸页扫描-cli.exe'} and path.parent == PACKAGE:
            assert pe.OPTIONAL_HEADER.Subsystem == (3 if path.stem.endswith('-cli') else 2)
            manifests = []
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                if entry.id == 24:
                    for resource in entry.directory.entries:
                        for language in resource.directory.entries:
                            data = language.data.struct
                            manifests.append(pe.get_data(data.OffsetToData, data.Size).decode('utf-8'))
            assert len(manifests) == 1
            manifest = ET.fromstring(manifests[0])
            code_page = manifest.find('.//{http://schemas.microsoft.com/SMI/2019/WindowsSettings}activeCodePage')
            assert code_page is not None and code_page.text == 'UTF-8'
        if path == runtime / 'python312.dll':
            assert b'Py_Main' in {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        report.append({'path': str(path.relative_to(PACKAGE)), 'imports': sorted(imports)})
        pe.close()
    info['validation']['binary_and_resource_check'] = f'通过：{len(report)} 个 x64 PE 文件，DLL、UTF-8 清单、Python 入口、源码和四份模型齐全'
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    report_path = ROOT / 'artifacts/windows-build/pe-dependencies.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(info['validation']['binary_and_resource_check'])


if __name__ == '__main__':
    check()
