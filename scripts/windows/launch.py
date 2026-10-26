"""便携版入口：载入本地 DLL，记录启动异常，保持所有图片处理在本机执行。"""
import ctypes
from datetime import datetime
import faulthandler
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'
SITE = RUNTIME / 'Lib' / 'site-packages'
DLL_HANDLES = []
LOG = None
CLI = len(sys.argv) > 1 and not (len(sys.argv) == 4 and sys.argv[1] == '--self-test')


def prepare():
    global LOG
    directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PaperScanner' / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    LOG = (directory / 'startup.log').open('a', encoding='utf-8', buffering=1)
    if not CLI:
        sys.stdout = sys.stderr = LOG
    else:
        # 管道由调用方持有；命令行结果不能被启动日志截走。
        if sys.stdout is None:
            sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        if sys.stderr is None:
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    faulthandler.enable(LOG)
    print(f'\n--- 启动 {datetime.now().isoformat(timespec="seconds")} ---', file=LOG)
    print('程序目录：', ROOT, file=LOG)
    for path in [RUNTIME, SITE, SITE / 'PySide6', SITE / 'shiboken6', SITE / 'numpy.libs', SITE / 'cv2']:
        if path.is_dir():
            DLL_HANDLES.append(os.add_dll_directory(str(path)))
    os.environ['QT_PLUGIN_PATH'] = str(SITE / 'PySide6' / 'plugins')
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(SITE / 'PySide6' / 'plugins' / 'platforms')
    # Py_Main 与模型在同一进程中，清单应使 CP_ACP 为 UTF-8。
    if ctypes.windll.kernel32.GetACP() != 65001:
        raise RuntimeError('当前 Windows 版本不支持应用的 UTF-8 路径模式，请使用 Windows 10 1903 或更新版本。')


try:
    prepare()
    runpy.run_path(str(ROOT / 'app' / 'main.py'), run_name='__main__')
except SystemExit:
    raise
except Exception:
    details = traceback.format_exc()
    if LOG:
        LOG.write(details)
    if CLI:
        print(details, file=sys.stderr)
    else:
        ctypes.windll.user32.MessageBoxW(None, '应用启动失败。\n\n请将整个文件夹重新解压后重试。\n详细记录位于：%LOCALAPPDATA%\\PaperScanner\\logs\\startup.log\n\n' + str(sys.exc_info()[1]), '纸页扫描', 0x10)
    raise SystemExit(1)
