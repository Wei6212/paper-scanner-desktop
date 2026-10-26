#!/usr/bin/env python3
"""将当前程序与本地模型打包成 macOS 应用。"""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys

from portable_dependencies import minimal_opencv

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--opencv-dir', type=Path,
                    default=ROOT / f'artifacts/opencv-minimal/darwin-{platform.machine().lower()}/python')
opencv_dir = parser.parse_args().opencv_dir.resolve()
minimal_opencv(opencv_dir, f'darwin-{platform.machine().lower()}')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(ROOT))
from PIL import Image
from PySide6.QtWidgets import QApplication
from paper_scanner.ui import app_icon

app = QApplication([])
assets = ROOT / 'artifacts'
assets.mkdir(exist_ok=True)
png = assets / 'icon.png'
app_icon(1024).pixmap(1024, 1024).save(str(png))
icon = assets / 'icon.icns'
Image.open(png).save(icon, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--onedir', '--name', '纸页扫描', '--osx-bundle-identifier', 'local.paperscanner.desktop', '--icon', str(icon), '--add-data', f'{ROOT / "models"}:models', '--hidden-import', '_mnncengine', '--add-binary', f'{Path(sys.prefix) / "lib/libMNN.dylib"}:.', '--exclude-module', 'MNN.tools', '--exclude-module', 'MNN.llm', '--hidden-import', 'MNN.nn', '--hidden-import', 'MNN.expr', '--exclude-module', 'pytest', '--exclude-module', 'tkinter', '--exclude-module', 'matplotlib', '--exclude-module', 'PySide6.QtNetwork', '--add-data', f'{ROOT / "paper_scanner/assets"}:paper_scanner/assets', str(ROOT / 'main.py')]
command[3:3] = ['--clean', '--paths', str(opencv_dir),
                '--exclude-module', 'PIL.AvifImagePlugin', '--exclude-module', 'PIL._avif',
                '--add-data', f'{opencv_dir / "OpenCV-LICENSE.txt"}:.',
                '--add-data', f'{opencv_dir / "OpenCV-NOTICES.txt"}:.',
                '--add-data', f'{opencv_dir / "zlib-LICENSE.txt"}:.',
                '--add-data', f'{opencv_dir / "opencv-build.json"}:.']
subprocess.run(command, cwd=ROOT, check=True)
print(ROOT / 'dist/纸页扫描.app')
