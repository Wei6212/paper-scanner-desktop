#!/usr/bin/env python3
"""从固定版本源码构建扫描所需的 OpenCV，输出独立目录，不替换开发环境。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'artifacts/opencv-minimal'
SOURCE_COMMIT = '40738fb16ceddb5fb3fea747585f7ce6abb0605b'


def executable(name):
    local = Path(sys.executable).parent / (name + ('.exe' if os.name == 'nt' else ''))
    found = str(local) if local.is_file() else shutil.which(name)
    if not found:
        raise ValueError(f'缺少构建工具：{name}，请先在构建环境安装 cmake、ninja')
    return found


def cmake_options():
    return {
        'CMAKE_BUILD_TYPE': 'Release',
        'BUILD_LIST': 'core,flann,geometry,imgproc,python3',
        'BUILD_SHARED_LIBS': 'OFF',
        'BUILD_opencv_python3': 'ON',
        'BUILD_opencv_apps': 'OFF',
        'BUILD_TESTS': 'OFF',
        'BUILD_PERF_TESTS': 'OFF',
        'BUILD_EXAMPLES': 'OFF',
        'BUILD_DOCS': 'OFF',
        'BUILD_JAVA': 'OFF',
        'WITH_FFMPEG': 'OFF',
        'WITH_AVIF': 'OFF',
        'WITH_JPEG': 'OFF',
        'WITH_PNG': 'OFF',
        'WITH_TIFF': 'OFF',
        'WITH_WEBP': 'OFF',
        'WITH_OPENEXR': 'OFF',
        'WITH_OPENJPEG': 'OFF',
        'WITH_JASPER': 'OFF',
        'WITH_GSTREAMER': 'OFF',
        'WITH_QT': 'OFF',
        'WITH_GTK': 'OFF',
        'WITH_OPENCL': 'OFF',
        'WITH_IPP': 'OFF',
        'WITH_ITT': 'OFF',
        'WITH_LAPACK': 'OFF',
        'WITH_EIGEN': 'OFF',
        'WITH_CAROTENE': 'OFF',
        'WITH_KLEIDICV': 'OFF',
        'WITH_UNIFONT': 'OFF',
        'CPU_DISPATCH': '',
        'OPENCV_PYTHON3_INSTALL': 'OFF',
        'OPENCV_SKIP_PYTHON_LOADER': 'ON',
        'PYTHON3_LIMITED_API': 'ON',
        'PYTHON3_LIMITED_API_VERSION': '0x03070000',
        'PYTHON_DEFAULT_EXECUTABLE': sys.executable,
        'PYTHON3_EXECUTABLE': sys.executable,
        'PYTHON3_INCLUDE_DIR': sysconfig.get_path('include'),
        'PYTHON3_INCLUDE_PATH': sysconfig.get_path('include'),
        'PYTHON3_LIBRARY': str(Path(sysconfig.get_config_var('LIBDIR') or sys.base_prefix)
                               / (sysconfig.get_config_var('LDLIBRARY') or 'python3.lib')),
        'PYTHON3_NUMPY_INCLUDE_DIRS': np.get_include(),
    }


def windows_options(build: Path, sdk: Path, site: Path):
    if not (sdk / 'include/Python.h').is_file() or not (sdk / 'libs/python3.lib').is_file():
        raise ValueError('Windows Python SDK 必须包含 include/Python.h 和 libs/python3.lib')
    numpy_include = site / 'numpy/_core/include'
    if not (numpy_include / 'numpy/arrayobject.h').is_file():
        raise ValueError('缺少 Windows NumPy wheel 中的头文件')
    result = {
        'PYTHON3_INCLUDE_DIR': str(sdk / 'include'),
        'PYTHON3_INCLUDE_PATH': str(sdk / 'include'),
        'PYTHON3_LIBRARY': str(sdk / 'libs/python3.lib'),
        'PYTHON3_LIBRARIES': str(sdk / 'libs/python3.lib'),
        'PYTHON3_NUMPY_INCLUDE_DIRS': str(numpy_include),
        'PYTHON3_CVPY_SUFFIX': '.pyd',
        'CPU_BASELINE': 'SSE2',
        'WITH_MSMF': 'OFF',
        'WITH_DSHOW': 'OFF',
        'CMAKE_CXX_FLAGS': '-D_USE_MATH_DEFINES',
    }
    if os.name != 'nt':
        # 交叉编译时只运行宿主 Python 生成绑定，不执行目标 PE。
        for name, command in [('cc', 'cc'), ('cxx', 'c++')]:
            wrapper = build / f'zig-{name}'
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable)
                               + f' -m ziglang {command} -target x86_64-windows-gnu "$@" -fno-lto -fno-sanitize=all\n')
            wrapper.chmod(0o755)
            result['CMAKE_C_COMPILER' if name == 'cc' else 'CMAKE_CXX_COMPILER'] = str(wrapper)
        for command in ('ar', 'ranlib'):
            wrapper = build / f'zig-{command}'
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable)
                               + f' -m ziglang {command} "$@"\n')
            wrapper.chmod(0o755)
            result[f'CMAKE_{command.upper()}'] = str(wrapper)
        result.update({
            'CMAKE_SYSTEM_NAME': 'Windows',
            'CMAKE_SYSTEM_PROCESSOR': 'AMD64',
            'CMAKE_SIZEOF_VOID_P': '8',
            'CMAKE_C_SIZEOF_DATA_PTR': '8',
            'CMAKE_CXX_SIZEOF_DATA_PTR': '8',
            'CMAKE_ASM_COMPILER': str(build / 'zig-cc'),
            'CMAKE_CROSSCOMPILING': 'ON',
            'CMAKE_TRY_COMPILE_TARGET_TYPE': 'STATIC_LIBRARY',
        })
    return result


def build(args):
    source = args.source.resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != SOURCE_COMMIT:
        raise ValueError(f'需要 OpenCV 5.0.0 固定提交 {SOURCE_COMMIT}，实际为 {commit}')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('OpenCV 源码存在修改，请使用干净的固定版本源码')
    target = args.target
    if target == 'native':
        target = 'windows-x64' if os.name == 'nt' else f'{platform.system().lower()}-{platform.machine().lower()}'
    directory = CACHE / target
    build_dir = directory / 'build'
    output = directory / 'python'
    build_dir.mkdir(parents=True, exist_ok=True)
    options = cmake_options()
    if sys.platform == 'darwin' and target != 'windows-x64':
        # 不随构建主机的系统版本抬高最低部署版本。
        options['CMAKE_OSX_DEPLOYMENT_TARGET'] = '13.0'
    if target == 'windows-x64':
        options.update(windows_options(build_dir, args.python_sdk.resolve(), args.windows_site.resolve()))
    options['CMAKE_MAKE_PROGRAM'] = executable('ninja')
    command = [executable('cmake'), '-S', str(source), '-B', str(build_dir), '-G', 'Ninja']
    command += [f'-D{key}={value}' for key, value in options.items()]
    subprocess.run(command, check=True)
    configured = set(re.findall(r'^#define HAVE_OPENCV_(\w+)',
                               (build_dir / 'opencv2/opencv_modules.hpp').read_text(), re.MULTILINE))
    if configured != {'CORE', 'FLANN', 'GEOMETRY', 'IMGPROC'}:
        raise ValueError(f'OpenCV 实际启用模块不匹配：{sorted(configured)}')
    if 'opencv_python3' not in (build_dir / 'build.ninja').read_text():
        raise ValueError('OpenCV 未启用 Python 绑定')
    subprocess.run([executable('cmake'), '--build', str(build_dir), '--target', 'opencv_python3',
                    '--parallel', str(args.jobs)], check=True)
    candidates = list((build_dir / 'lib').rglob('cv2*.pyd' if target == 'windows-x64' else 'cv2*.so'))
    if len(candidates) != 1:
        raise ValueError(f'OpenCV Python 扩展数量异常：{candidates}')
    output.mkdir(parents=True, exist_ok=True)
    extension = output / ('cv2.pyd' if target == 'windows-x64' else 'cv2.abi3.so')
    shutil.copy2(candidates[0], extension)
    if sys.platform == 'darwin' and target != 'windows-x64':
        subprocess.run(['strip', '-x', str(extension)], check=True)
    # 二进制分发同时保留上游许可。
    shutil.copy2(source / 'LICENSE', output / 'OpenCV-LICENSE.txt')
    shutil.copy2(source / '3rdparty/zlib/LICENSE', output / 'zlib-LICENSE.txt')
    notices = [(source / 'COPYRIGHT').read_text()]
    for name in ('modules/flann/include/opencv2/flann/defines.h', 'modules/geometry/src/shapedescr.cpp'):
        notices.append((source / name).read_text().split('*/', 1)[0] + '*/\n')
    (output / 'OpenCV-NOTICES.txt').write_text('\n'.join(notices), encoding='utf-8')
    manifest = {'opencv': '5.0.0', 'source_commit': commit, 'target': target,
                'modules': ['core', 'flann', 'geometry', 'imgproc', 'python3'], 'cmake_options': options,
                'extension': extension.name, 'bytes': extension.stat().st_size,
                'sha256': hashlib.sha256(extension.read_bytes()).hexdigest()}
    (output / 'opencv-build.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'精简 OpenCV：{extension}，{extension.stat().st_size / 1024**2:.2f} MiB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=CACHE / 'source')
    parser.add_argument('--target', choices=['native', 'windows-x64'], default='native')
    parser.add_argument('--python-sdk', type=Path, default=CACHE / 'python-sdk/tools')
    parser.add_argument('--windows-site', type=Path,
                        default=ROOT / 'dist/纸页扫描-Windows-x64/runtime/Lib/site-packages')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 2, 4))
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error('--jobs 必须为正整数')
    build(arguments)
