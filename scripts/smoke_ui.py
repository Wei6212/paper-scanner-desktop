"""通过真实工作线程验证目录、预览、尺寸、体积上限及批量错误隔离。"""
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import QTimer, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from paper_scanner.ui import MainWindow, STYLE, configure_application

root = Path(__file__).resolve().parents[1]
app = QApplication([])
configure_application(app)
window = MainWindow()
window.resize(1360, 900)
window.show()
workspace = tempfile.TemporaryDirectory(prefix='paper-scanner-smoke-')
window.settings = QSettings(str(Path(workspace.name) / 'settings.ini'), QSettings.Format.IniFormat)
source = Path(workspace.name) / '输入'
source.mkdir()
shutil.copy2(root / 'samples/手绘文档原图.jpg', source / '01_文档.jpg')
shutil.copy2(root / 'samples/手绘文档原图.jpg', source / '02_文档.jpg')
(source / '03_损坏.jpg').write_bytes(b'broken image')
output = root / 'artifacts/界面导出验证'
output.mkdir(parents=True, exist_ok=True)
window.output_path.setText(str(output))
window.size_mode.setCurrentIndex(1)
window.limit_check.setChecked(True)
window.max_mb.setValue(0.2)
state = {'phase': 'preview', 'error': None}


def tick():
    try:
        if window.worker is not None or window.original_canvas.corner_update_timer.isActive():
            QTimer.singleShot(50, tick)
            return
        if state['phase'] == 'preview':
            assert window.last_result is not None
            window.grab().save(str(root / 'artifacts/界面扫描预览.png'))
            for canvas, image in ((window.original_canvas, window.last_result.original),
                                  (window.output_canvas, window.last_result.image)):
                assert canvas.image.width() == image.width
                assert canvas.image.height() == image.height
                canvas.set_zoom(1)
                assert canvas.target.width() == image.width
            app.processEvents()
            window.grab().save(str(root / 'artifacts/界面画布缩放.png'))
            window.original_canvas.select_corner(0)
            state['corner_before'] = window.original_canvas.corners[0].copy()
            state['offset_before'] = window.original_canvas.offset
            state['result_before'] = window.last_result
            state['phase'] = 'fine_adjust'
            QTest.keyClick(window.original_canvas, Qt.Key.Key_Right)
            QTimer.singleShot(50, tick)
            return
        if state['phase'] == 'fine_adjust':
            assert window.last_result is not state['result_before']
            assert window.original_canvas.zoom == window.output_canvas.zoom == 1
            assert window.original_canvas.offset == state['offset_before']
            assert window.original_canvas.selected_corner == 0
            expected = state['corner_before'][0] + 1 / (window.last_result.original.width - 1)
            assert abs(window.original_canvas.corners[0][0] - expected) < 1e-6
            window.grab().save(str(root / 'artifacts/界面放大微调.png'))
            window.original_canvas.fit_image()
            window.output_canvas.fit_image()
            state['phase'] = 'export'
            window.start_export()
            QTimer.singleShot(50, tick)
            return
        assert window.batch_ok == 2 and window.batch_failed == 1
        files = sorted(output.glob('*_扫描*.jpg'))
        assert len(files) >= 2
        for path in files:
            assert path.stat().st_size <= 200_000
            with Image.open(path) as image:
                assert image.width <= 1165 and image.height <= 790
        assert window.export_button.isEnabled()
        assert window.original_canvas.editable
        window.grab().save(str(root / 'artifacts/界面批量导出.png'))
        print('界面验证通过：真实模型预览、放大后逐像素微调并保留双侧视图、70%导出、0.2MB上限、两张成功、一张损坏隔离、按钮恢复', flush=True)
    except Exception as error:
        state['error'] = error
        print('界面验证失败：',repr(error),flush=True)
    window.close()
    app.quit()


window.file_list.blockSignals(True)
window.load_folder(source)
window.file_list.setCurrentRow(0)
window.file_list.blockSignals(False)
window.select_item(0)
QTimer.singleShot(50, tick)
QTimer.singleShot(60000, app.quit)
app.exec()
workspace.cleanup()
if state['error']:
    raise state['error']
if state['phase'] != 'export':
    raise RuntimeError('界面验证超时')
