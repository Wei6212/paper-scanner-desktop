"""验证画布缩放、平移和放大后的四角编辑。"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PIL import Image
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from paper_scanner.ui import ImageCanvas, MainWindow


@pytest.fixture(scope='session')
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(params=[False, True])
def canvas(app, request):
    widget = ImageCanvas(editable=request.param)
    widget.resize(400, 400)
    widget.show()
    app.processEvents()
    widget.set_image(Image.new('RGB', (2400, 1600)),
                     [[.1, .1], [.9, .1], [.9, .9], [.1, .9]])
    yield widget
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def mouse(widget, kind, point, button, buttons):
    QApplication.sendEvent(widget, QMouseEvent(kind, point, widget.mapToGlobal(point),
                                              button, buttons, Qt.KeyboardModifier.NoModifier))


def drag(widget, start, end):
    mouse(widget, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    mouse(widget, QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    mouse(widget, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)


def test_full_resolution_fit_and_native_pixels(canvas):
    assert canvas.image.width() == 2400
    assert canvas.target.width() == pytest.approx(400 - 2 * canvas.image_margin)
    canvas.set_zoom(1)
    assert canvas.target.width() == 2400
    assert canvas.target.height() == 1600
    canvas.fit_image()
    assert canvas.fit_mode
    assert canvas.offset == QPointF()
    assert canvas.target.width() == pytest.approx(400 - 2 * canvas.image_margin)


def test_wheel_keeps_image_point_under_pointer(canvas):
    canvas.set_zoom(.5)
    anchor = QPointF(245, 230)
    before = (anchor - canvas.target.topLeft()) / canvas.zoom
    event = QWheelEvent(anchor, anchor, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(canvas, event)
    QTest.qWait(160)
    after = (anchor - canvas.target.topLeft()) / canvas.zoom
    assert canvas.zoom == pytest.approx(.625)
    assert after.x() == pytest.approx(before.x())
    assert after.y() == pytest.approx(before.y())


def wheel(widget, angle=120, pixels=0, anchor=None):
    anchor = anchor if anchor is not None else QPointF(200, 200)
    event = QWheelEvent(anchor, widget.mapToGlobal(anchor), QPoint(0, pixels), QPoint(0, angle),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.ScrollUpdate, False)
    QApplication.sendEvent(widget, event)
    return event


def test_wheel_has_intermediate_frames_and_accumulates_quick_scrolls(canvas):
    canvas.set_zoom(.5)
    assert wheel(canvas).isAccepted()
    QTest.qWait(40)
    assert .5 < canvas.zoom < .625
    wheel(canvas)
    wheel(canvas)
    QTest.qWait(160)
    assert canvas.zoom == pytest.approx(.5 * 1.25 ** 3)


def test_small_high_resolution_scrolls_take_priority_and_reverse(canvas):
    canvas.set_zoom(.5)
    for _ in range(12):
        wheel(canvas, angle=120, pixels=2)
    QTest.qWait(160)
    assert canvas.zoom == pytest.approx(.5 * 1.25 ** .2)
    for _ in range(12):
        wheel(canvas, angle=-120, pixels=-2)
    QTest.qWait(160)
    assert canvas.zoom == pytest.approx(.5)


def test_zoom_limit_reverses_without_consuming_excess_scrolls(canvas):
    canvas.set_zoom(8)
    for _ in range(5):
        wheel(canvas)
    wheel(canvas, angle=-120)
    QTest.qWait(160)
    assert canvas.zoom == pytest.approx(8 / 1.25)


@pytest.mark.parametrize('action', ['fit', 'native', 'clear', 'pan'])
def test_direct_actions_cancel_pending_wheel_animation(canvas, action):
    canvas.set_zoom(.5)
    wheel(canvas)
    if action == 'fit':
        canvas.fit_image()
    elif action == 'native':
        canvas.set_zoom(1)
    elif action == 'clear':
        canvas.set_image()
    else:
        drag(canvas, QPointF(200, 200), QPointF(220, 210))
    zoom = canvas.zoom
    offset = QPointF(canvas.offset)
    QTest.qWait(160)
    assert canvas.zoom == zoom
    assert canvas.offset == offset


def test_wheel_ignores_empty_and_zero_delta(canvas):
    canvas.set_zoom(.5)
    assert not wheel(canvas, angle=0).isAccepted()
    canvas.set_image()
    assert not wheel(canvas).isAccepted()


def test_drag_pans_without_changing_corners_and_stays_bounded(canvas):
    canvas.set_zoom(1)
    corners = canvas.corners.copy()
    start = canvas.target.topLeft()
    changes = []
    canvas.corners_changed.connect(changes.append)
    drag(canvas, QPointF(200, 200), QPointF(250, 230))
    assert canvas.target.topLeft() == start + QPointF(50, 30)
    np.testing.assert_array_equal(canvas.corners, corners)
    assert changes == []
    drag(canvas, QPointF(200, 200), QPointF(10000, 10000))
    assert canvas.target.left() == pytest.approx(canvas.image_margin)
    assert canvas.target.top() == pytest.approx(canvas.image_margin)
    assert canvas.pan_start is None


def test_zoom_limits_and_empty_state(canvas):
    canvas.set_zoom(1e6)
    assert canvas.zoom == 8
    canvas.set_zoom(0)
    assert canvas.zoom == .01
    canvas.set_image()
    canvas.zoom_in()
    canvas.zoom_out()
    canvas.fit_image()
    assert canvas.image is None
    assert canvas.target.isEmpty()


def test_refresh_preserves_view_and_different_size_resets(canvas):
    canvas.set_zoom(1)
    drag(canvas, QPointF(200, 200), QPointF(250, 230))
    position = QPointF(canvas.offset)
    canvas.set_image(Image.new('RGB', (2400, 1600)))
    assert canvas.zoom == 1
    assert canvas.offset == position
    canvas.set_image(Image.new('RGB', (1600, 2400)))
    assert canvas.fit_mode
    assert canvas.offset == QPointF()


def test_resize_and_double_click(canvas, app):
    canvas.set_zoom(1)
    canvas.resize(500, 450)
    app.processEvents()
    assert canvas.zoom == 1
    mouse(canvas, QEvent.Type.MouseButtonDblClick, QPointF(200, 200),
          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    assert canvas.fit_mode
    canvas.resize(600, 500)
    app.processEvents()
    assert canvas.zoom == pytest.approx((600 - 2 * canvas.image_margin) / 2400)


def test_corner_coordinates_after_zoom_and_pan(app):
    canvas = ImageCanvas(editable=True)
    canvas.resize(400, 400)
    canvas.show()
    app.processEvents()
    canvas.set_image(Image.new('RGB', (1000, 1000)),
                     [[.4, .4], [.6, .4], [.6, .6], [.4, .6]])
    canvas.set_zoom(1)
    drag(canvas, QPointF(200, 200), QPointF(220, 230))
    point = canvas.target.topLeft() + QPointF(.4 * canvas.target.width(), .4 * canvas.target.height())
    changes = []
    canvas.corners_changed.connect(changes.append)
    drag(canvas, point, point + QPointF(50, 30))
    np.testing.assert_allclose(canvas.corners[0], [.45, .43])
    assert len(changes) == 1
    np.testing.assert_allclose(changes[0][0], [.45, .43])
    canvas.close()
    canvas.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_toolbar_controls_are_independent(app):
    window = MainWindow()
    window.show()
    app.processEvents()
    native_buttons = [next(button for button in canvas.parentWidget().findChildren(QPushButton)
                           if button.text() == '100%')
                      for canvas in (window.original_canvas, window.output_canvas)]
    assert len(native_buttons) == 2
    assert all(not button.isEnabled() for button in native_buttons)
    for canvas in (window.original_canvas, window.output_canvas):
        canvas.set_image(Image.new('RGB', (2400, 1600)))
    original_zoom = window.original_canvas.zoom
    native_buttons[1].click()
    assert window.output_canvas.zoom == 1
    assert window.original_canvas.zoom == original_zoom
    native_buttons[0].click()
    assert window.original_canvas.zoom == 1
    # 清理窗口时不写入用户已有设置。
    window._save_settings = lambda: None
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def key(widget, value, modifiers=Qt.KeyboardModifier.NoModifier, release=True):
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, value, modifiers))
    if release:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyRelease, value, modifiers))


def test_corner_nudge_uses_source_pixels_at_any_zoom(canvas):
    canvas.set_zoom(4)
    canvas.select_corner(0)
    before = canvas.corners.copy()
    zoom = canvas.zoom
    key(canvas, Qt.Key.Key_Right)
    key(canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    if canvas.editable:
        np.testing.assert_allclose(canvas.corners[0] - before[0], [1 / 2399, 10 / 1599])
        np.testing.assert_array_equal(canvas.corners[1:], before[1:])
        assert canvas.selected_corner == 0
    else:
        np.testing.assert_array_equal(canvas.corners, before)
    assert canvas.zoom == zoom


def test_corner_navigation_reveals_offscreen_handle(canvas):
    canvas.set_zoom(4)
    for index in range(4):
        canvas.select_corner(index)
        point = canvas.target.topLeft() + QPointF(canvas.corners[index][0] * canvas.target.width(),
                                                  canvas.corners[index][1] * canvas.target.height())
        assert canvas.rect().contains(point.toPoint())
        assert canvas.zoom == 4


def test_key_edits_emit_once_after_release(canvas):
    if not canvas.editable:
        return
    changes = []
    canvas.corners_changed.connect(changes.append)
    canvas.select_corner(0)
    key(canvas, Qt.Key.Key_Right, release=False)
    QTest.qWait(230)
    assert changes == []
    QApplication.sendEvent(canvas, QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
    key(canvas, Qt.Key.Key_Down)
    QTest.qWait(230)
    assert len(changes) == 1
    np.testing.assert_allclose(changes[0][0], [.1 + 1 / 2399, .1 + 1 / 1599])


def test_corner_nudge_stays_in_image_and_ignores_missing_selection(canvas):
    before = canvas.corners.copy()
    key(canvas, Qt.Key.Key_Right)
    np.testing.assert_array_equal(canvas.corners, before)
    canvas.corners[0] = [0, 0]
    canvas.select_corner(0)
    key(canvas, Qt.Key.Key_Left)
    key(canvas, Qt.Key.Key_Up)
    np.testing.assert_array_equal(canvas.corners[0], [0, 0])
    canvas.set_image()
    key(canvas, Qt.Key.Key_Right)
    assert canvas.selected_corner is None
    assert not canvas.corner_update_timer.isActive()


def test_resized_result_can_preserve_zoom_and_normalized_center(canvas):
    canvas.set_zoom(1)
    drag(canvas, QPointF(200, 200), QPointF(250, 230))
    before = (QPointF(200, 200) - canvas.target.topLeft())
    center = np.array([before.x() / canvas.target.width(), before.y() / canvas.target.height()])
    canvas.set_image(Image.new('RGB', (2300, 1500)), preserve_view=True)
    after = QPointF(200, 200) - canvas.target.topLeft()
    assert canvas.zoom == 1
    np.testing.assert_allclose([after.x() / canvas.target.width(), after.y() / canvas.target.height()], center)


def test_refresh_retains_selected_corner(canvas):
    canvas.set_zoom(2)
    canvas.select_corner(2)
    corners = canvas.corners.copy()
    offset = QPointF(canvas.offset)
    canvas.set_image(Image.new('RGB', (2400, 1600)), corners)
    assert canvas.selected_corner == 2
    assert canvas.zoom == 2
    assert canvas.offset == offset


def test_close_cancels_pending_corner_preview(app):
    window = MainWindow()
    window._save_settings = lambda: None
    window.show()
    app.processEvents()
    canvas = window.original_canvas
    canvas.set_image(Image.new('RGB', (2400, 1600)),
                     [[.1, .1], [.9, .1], [.9, .9], [.1, .9]])
    canvas.select_corner(0)
    key(canvas, Qt.Key.Key_Right)
    assert canvas.corner_edit_pending
    changes = []
    canvas.corners_changed.connect(changes.append)
    window.close()
    QTest.qWait(230)
    assert not canvas.corner_update_timer.isActive()
    assert changes == []
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
