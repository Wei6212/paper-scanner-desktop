"""打包后验证原生界面、模型加载和文件导出。"""
import json
import os
from pathlib import Path
import sys
import tempfile


def run(source: Path, destination: Path):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow, STYLE, configure_application
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    configure_application(app)
    window = MainWindow()
    temporary = tempfile.TemporaryDirectory(prefix='paper-scanner-check-')
    window.settings = QSettings(str(Path(temporary.name) / 'settings.ini'), QSettings.Format.IniFormat)
    window.size_mode.setCurrentIndex(2)
    window.limit_check.setChecked(True)
    window.max_mb.setValue(0.2)
    window.output_path.setText(str(destination))
    window.curve_check.setChecked(True)
    window.show()
    state = {'phase': 'preview', 'passed': False}

    def finish():
        if window.worker is not None:
            QTimer.singleShot(50, finish)
            return
        if state['phase'] == 'preview':
            if window.last_result is None:
                state['error'] = window.message.text()
                window.close()
                app.quit()
                return
            state['phase'] = 'export'
            window.start_export()
            QTimer.singleShot(50, finish)
            return
        state['passed'] = window.batch_ok == 1 and window.batch_failed == 0
        state['message'] = window.message.text()
        window.grab().save(str(destination / '打包应用验证.png'))
        (destination / '验证结果.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print(json.dumps(state, ensure_ascii=False), flush=True)
        window.close()
        app.quit()

    def timeout():
        state['error'] = '验证超时'
        window.close()

    window.add_files([source])
    QTimer.singleShot(50, finish)
    QTimer.singleShot(60000, timeout)
    app.exec()
    temporary.cleanup()
    return 0 if state['passed'] else 1
