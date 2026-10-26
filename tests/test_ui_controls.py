"""检查箭头实际渲染及点击行为，覆盖两种 Qt 基础样式。"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QSpinBox, QStyle,
    QStyleOptionComboBox, QStyleOptionSpinBox,
)

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
