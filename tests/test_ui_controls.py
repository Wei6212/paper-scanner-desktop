"""检查控件渲染、点击行为和设置栏布局，覆盖两种 Qt 基础样式。"""
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QSpinBox, QStyle,
    QStyleOptionComboBox, QStyleOptionSpinBox,
)

from paper_scanner import ui
from paper_scanner.ui import configure_application


@pytest.fixture(scope='session')
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app
    app.closeAllWindows()


@pytest.fixture(params=['Fusion', 'Windows'])
def application(qt_application, request):
    app = qt_application
    configure_application(app)
    app.setStyle(request.param)
    yield app


def assert_arrow(widget, rect, disabled=False):
    image = widget.grab().toImage()
    scale = image.devicePixelRatio()
    color = QColor('#a7ab9f' if disabled else '#526b3e')
    # 缩放和抗锯齿可能改变边缘像素，不要求颜色逐字节相同。
    matches = 0
    for x in range(int(rect.left() * scale), int((rect.right() + 1) * scale)):
        for y in range(int(rect.top() * scale), int((rect.bottom() + 1) * scale)):
            pixel = image.pixelColor(x, y)
            if max(abs(a - b) for a, b in zip(pixel.getRgb()[:3], color.getRgb()[:3])) <= 12:
                matches += 1
    assert matches >= 3, '箭头区域未绘制预期图标'


@pytest.mark.parametrize('widget_type', [QSpinBox, QDoubleSpinBox])
def test_spin_arrows_render_and_step(application, widget_type):
    widget = widget_type()
    widget.setRange(0, 100)
    widget.setValue(50)
    widget.resize(160, 36)
    widget.show()
    application.processEvents()
    option = QStyleOptionSpinBox()
    widget.initStyleOption(option)
    up = widget.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxUp, widget)
    down = widget.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxDown, widget)
    try:
        assert_arrow(widget, up)
        assert_arrow(widget, down)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=up.center())
        assert widget.value() == 51
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=down.center())
        assert widget.value() == 50
        widget.setValue(widget.minimum())
        assert_arrow(widget, down, disabled=True)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=down.center())
        assert widget.value() == widget.minimum()
        widget.setValue(widget.maximum())
        assert_arrow(widget, up, disabled=True)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=up.center())
        assert widget.value() == widget.maximum()
        widget.setEnabled(False)
        assert_arrow(widget, up, disabled=True)
        assert_arrow(widget, down, disabled=True)
    finally:
        widget.close()


def test_combo_arrow_renders_and_opens(application):
    widget = QComboBox()
    widget.addItems(['JPEG', 'PNG'])
    widget.resize(160, 36)
    widget.show()
    application.processEvents()
    option = QStyleOptionComboBox()
    widget.initStyleOption(option)
    arrow = widget.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, widget)
    try:
        assert_arrow(widget, arrow)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=arrow.center())
        application.processEvents()
        assert widget.view().isVisible()
        QTest.keyClick(widget.view(), Qt.Key.Key_Down)
        QTest.keyClick(widget.view(), Qt.Key.Key_Return)
        assert widget.currentText() == 'PNG'
        widget.setEnabled(False)
        assert_arrow(widget, arrow, disabled=True)
    finally:
        widget.hidePopup()
        widget.close()


@pytest.mark.parametrize('size', [(1360, 900), (1120, 760)])
def test_settings_panel_fits_without_horizontal_scroll(application, monkeypatch, tmp_path, size):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(ui, 'QSettings', lambda *args: settings)
    window = ui.MainWindow()
    window.resize(*size)
    window.show()
    application.processEvents()
    scroll = window.findChild(QScrollArea)
    panel = scroll.parentWidget()
    splitter = panel.parentWidget()
    initial_sizes = splitter.sizes()
    try:
        # 包含最宽的自定义宽高组合，并验证用户拖窄右栏后仍完整显示。
        for mode in range(window.size_mode.count()):
            window.size_mode.setCurrentIndex(mode)
            window.limit_check.setChecked(True)
            window.width_input.setValue(30000)
            window.height_input.setValue(30000)
            for narrow in (False, True):
                if narrow:
                    splitter.setSizes([210, window.width(), 1])
                else:
                    splitter.setSizes(initial_sizes)
                application.processEvents()
                assert scroll.horizontalScrollBar().maximum() == 0
                assert not scroll.horizontalScrollBar().isVisible()
                assert scroll.widget().width() == scroll.viewport().width()
                assert panel.width() >= panel.minimumSizeHint().width()
                for widget in (window.strength_label, window.strength, window.black_white, window.black_threshold,
                               window.stroke_radius, window.dimensions, window.format):
                    if widget.isVisible():
                        position = widget.mapTo(scroll.widget(), widget.rect().topRight())
                        assert position.x() < scroll.viewport().width()
        splitter.setSizes([210, window.width(), 0])
        application.processEvents()
        assert panel.width() >= panel.minimumSizeHint().width() > 0
    finally:
        window.close()
        window.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_black_white_controls_and_settings(application, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / 'black_white.ini'), QSettings.Format.IniFormat)
    # 即使旧版记录了开启状态，新窗口也必须默认关闭。
    settings.setValue('black_white', True)
    monkeypatch.setattr(ui, 'QSettings', lambda *args: settings)
    window = ui.MainWindow()
    try:
        assert not window.scan_options().black_white
        assert not window.black_threshold.isEnabled()
        assert not window.stroke_radius.isEnabled()
        window.black_white.setChecked(True)
        assert window.black_threshold.isEnabled()
        assert window.stroke_radius.isEnabled()
        window.black_threshold.setValue(200)
        window.stroke_radius.setValue(2)
        options = window.scan_options()
        assert options.black_white and options.black_threshold == 200 and options.stroke_radius == 2
        window._save_settings()
    finally:
        window.close()
        window.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    restored = ui.MainWindow()
    try:
        assert not restored.black_white.isChecked()
        assert not restored.black_threshold.isEnabled()
        assert not restored.stroke_radius.isEnabled()
        assert restored.black_threshold.value() == 200
        assert restored.stroke_radius.value() == 2
    finally:
        restored.close()
        restored.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_black_white_toggle_refreshes_preview_and_merges_pending_changes(application, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / 'preview.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(ui, 'QSettings', lambda *args: settings)
    path = tmp_path / '淡字.png'
    Image.new('RGB', (40, 30), (125, 125, 125)).save(path)
    entered = threading.Event()
    release = threading.Event()
    calls = []
    from paper_scanner.engine import Scanner
    process = Scanner.process

    def controlled_process(scanner, source, options, *args):
        calls.append(options.black_white)
        if len(calls) == 1:
            entered.set()
            if not release.wait(5):
                raise TimeoutError('首轮预览未释放')
        return process(scanner, source, options, *args)

    def wait_for(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert predicate(), '等待预览状态超时'

    monkeypatch.setattr(Scanner, 'process', controlled_process)
    window = ui.MainWindow()
    try:
        # 没有图片时切换只更新控件，不启动任务。
        window.black_white.click()
        window.black_white.click()
        assert window.worker is None
        window.auto_crop.setChecked(False)
        window.auto_enhance.setChecked(False)
        window.add_files([path])
        wait_for(entered.is_set)
        assert window.worker is not None and window.black_white.isEnabled()
        window.black_white.click()
        window.black_white.click()
        window.black_white.click()
        assert calls == [False]
        assert window.preview_pending
        assert not window.black_threshold.isEnabled()
        assert not window.quality.isEnabled()
        assert not window.export_button.isEnabled()
        release.set()
        wait_for(lambda: window.worker is None and window.last_result is not None)
        assert calls == [False, True]
        assert window.last_result.image.mode == '1'
        assert window.black_threshold.isEnabled()
        window.black_white.click()
        wait_for(lambda: window.worker is None)
        assert calls == [False, True, False]
        assert window.last_result.image.mode == 'RGB'
        assert window.last_result.image.getpixel((0, 0)) == (125, 125, 125)
        assert not window.black_threshold.isEnabled()
    finally:
        release.set()
        if window.worker is not None:
            window.cancel()
            wait_for(lambda: window.worker is None)
        window.close()
        window.deleteLater()
        application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
