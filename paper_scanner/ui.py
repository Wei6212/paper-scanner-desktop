"""原生桌面界面：目录队列、四角编辑、扫描预览和导出设置。"""
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image
from PySide6.QtCore import QAbstractAnimation, QDir, QEasingCurve, QEvent, QPoint, QPointF, QRectF, QSettings, QSignalBlocker, Qt, QTimer, QVariantAnimation, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from . import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_VERSION
from .engine import ScanOptions
from .exporting import ExportOptions, encode_image
from .jobs import WorkItem, Worker
from .thumbnails import ThumbnailLoader

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

STYLE = '''
QWidget { font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue"; font-size: 13px; color: #292d28; }
QMainWindow, QWidget#root { background: #f5f4f0; }
QFrame#header { background: #fbfbf8; border-bottom: 1px solid #dedfd7; }
QLabel#title { font-size: 24px; font-weight: 600; }
QLabel#subtitle, QLabel#muted { color: #5f6858; font-size: 13px; }
QLabel#section { font-size: 14px; font-weight: 600; }
QLabel#eyebrow { color: #757c6b; font-size: 11px; }
QFrame#panel { background: #fbfbf8; border: 1px solid #e0e2d9; border-radius: 8px; }
QPushButton { background: #fff; border: 1px solid #d6dacd; border-radius: 5px; padding: 8px 12px; font-weight: 500; }
QPushButton:hover { background: #edf0e6; border-color: #a7b49a; }
QPushButton:pressed { background: #dfe7d6; }
QPushButton:focus { border: 1px solid #65804b; }
QPushButton:disabled { color: #a7ab9f; background: #eeefe9; border-color: #e1e4d9; }
QPushButton#primary { color: #fff; background: #384b2d; border-color: #384b2d; padding: 11px; }
QPushButton#primary:hover { background: #4a603b; }
QPushButton#primary:disabled { background: #acb5a4; border-color: #acb5a4; }
QPushButton#quiet { background: transparent; border: 0; color: #5d6c51; padding: 4px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #fff; border: 1px solid #d9ddd2; border-radius: 4px; padding: 7px; min-height: 17px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #71865e; }
QLineEdit:read-only { color: #757c70; background: #f4f5ef; }
QComboBox, QSpinBox, QDoubleSpinBox { padding-right: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; border: 0; width: 24px; }
QComboBox::down-arrow { image: url(scanner_icons:arrow-down.png); width: 10px; height: 6px; }
QComboBox::down-arrow:disabled { image: url(scanner_icons:arrow-down-disabled.png); }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: padding; subcontrol-position: top right; width: 24px; border: 0; border-left: 1px solid #d9ddd2; border-top-right-radius: 3px; background: #f4f5ef; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: padding; subcontrol-position: bottom right; width: 24px; border: 0; border-left: 1px solid #d9ddd2; border-top: 1px solid #d9ddd2; border-bottom-right-radius: 3px; background: #f4f5ef; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #e8eddf; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #dfe7d6; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(scanner_icons:arrow-up.png); width: 10px; height: 6px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(scanner_icons:arrow-down.png); width: 10px; height: 6px; }
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off { image: url(scanner_icons:arrow-up-disabled.png); }
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off { image: url(scanner_icons:arrow-down-disabled.png); }
QListWidget { background: #fbfbf8; border: none; outline: none; }
QListWidget::item { padding: 0; border-bottom: 1px solid #eceee6; border-radius: 3px; }
QListWidget::item:selected { background: #e8eddf; color: #354b25; }
QListWidget::item:hover { background: #f0f2e9; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #b6c0ab; border-radius: 3px; background: #fff; }
QCheckBox::indicator:checked { background: #57723f; border-color: #57723f;  }
QProgressBar { background: #e7eade; border: none; border-radius: 3px; height: 5px; max-height: 5px; }
QProgressBar::chunk { background: #69834f; border-radius: 3px; }
QSlider::groove:horizontal { height: 4px; border-radius: 2px; background: #dfe4d6; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #526b3e; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollArea { border: none; background: transparent; }
QWidget#settings_content, QWidget#qt_scrollarea_viewport { background: #fbfbf8; }
QComboBox QAbstractItemView { background: #fff; color: #292d28; selection-background-color: #e8eddf; selection-color: #354b25; }
QScrollBar:vertical { width: 7px; background: transparent; }
QScrollBar::handle:vertical { background: #d5dacb; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #303a29; color: #fff; border: none; padding: 6px; }
'''


def label(text, object_name=None, wrap=False):
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    return widget


def pil_qimage(image: Image.Image):
    image = image.convert('RGB')
    raw = image.tobytes()
    return QImage(raw, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()


def app_icon(size=256):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('#384b2d'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * .22, size * .22)
    painter.setBrush(QColor('#fafbf4'))
    painter.drawRoundedRect(QRectF(size * .26, size * .19, size * .48, size * .62), size * .025, size * .025)
    pen = QPen(QColor('#7b9560'), size * .035, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    for y, x in ((.39, .62), (.51, .62), (.63, .53)):
        painter.drawLine(QPointF(size * .37, size * y), QPointF(size * x, size * y))
    painter.end()
    return QIcon(pixmap)


class ImageCanvas(QWidget):
    corners_changed = Signal(object)
    zoom_changed = Signal(float)
    corners_available = Signal(bool)

    def __init__(self, editable=False, parent=None):
        super().__init__(parent)
        self.image = None
        self.editable = editable
        self.image_margin = 24 if editable else 0
        self.corners = None
        self.drag_index = None
        self.selected_corner = None
        self.corner_edit_pending = False
        self.corner_update_timer = QTimer(self)
        self.corner_update_timer.setSingleShot(True)
        self.corner_update_timer.setInterval(200)
        self.corner_update_timer.timeout.connect(self._commit_corner_edit)
        self.pan_start = None
        self.zoom = 1.0
        self.fit_mode = True
        self.offset = QPointF()
        self.target = QRectF()
        self.wheel_anchor = QPointF()
        self.zoom_animation = QVariantAnimation(self)
        self.zoom_animation.setDuration(120)
        self.zoom_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.zoom_animation.valueChanged.connect(lambda zoom: self._apply_zoom(zoom, self.wheel_anchor))
        self.setMinimumSize(180, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if editable else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName('原图四角编辑' if editable else '扫描结果预览')
        self.setToolTip('鼠标移到画布上，直接滚动滚轮连续缩放；拖动平移，双击适应窗口。选中原图角点后，方向键微调 1 像素，Shift + 方向键调整 10 像素。')

    def set_image(self, image=None, corners=None, preserve_view=False):
        self.zoom_animation.stop()
        previous_size = self.image.size() if self.image is not None else None
        self.corner_update_timer.stop()
        self.corner_edit_pending = False
        self.image = pil_qimage(image) if image is not None else None
        self.corners = np.array(corners, dtype=float) if corners is not None else None
        self.drag_index = None
        self.pan_start = None
        if self.image is None or previous_size is None or (self.image.size() != previous_size and not preserve_view):
            self.fit_mode = True
            self.offset = QPointF()
            self.selected_corner = None
        elif preserve_view:
            self.offset = QPointF(self.offset.x() * self.image.width() / previous_size.width(),
                                  self.offset.y() * self.image.height() / previous_size.height())
        if self.corners is None:
            self.selected_corner = None
        self.corners_available.emit(self.corners is not None)
        self._update_target()
        self._update_cursor()
        self.update()

    def _fit_zoom(self):
        return min(max(1, self.width() - 2 * self.image_margin) / self.image.width(),
                   max(1, self.height() - 2 * self.image_margin) / self.image.height())

    def _update_target(self):
        if self.image is None:
            self.target = QRectF()
            self.zoom_changed.emit(0)
            return
        if self.fit_mode:
            self.zoom = self._fit_zoom()
            self.offset = QPointF()
        width, height = self.image.width() * self.zoom, self.image.height() * self.zoom
        # 限制平移范围，让图片边缘和四角始终可以移回视野。
        limit_x = max(0, (width - self.width()) / 2 + self.image_margin)
        limit_y = max(0, (height - self.height()) / 2 + self.image_margin)
        self.offset = QPointF(np.clip(self.offset.x(), -limit_x, limit_x),
                              np.clip(self.offset.y(), -limit_y, limit_y))
        self.target = QRectF((self.width() - width) / 2 + self.offset.x(),
                             (self.height() - height) / 2 + self.offset.y(), width, height)
        self.zoom_changed.emit(self.zoom)

    def set_zoom(self, zoom, anchor=None):
        self.zoom_animation.stop()
        self._apply_zoom(zoom, anchor)

    def _clamp_zoom(self, zoom):
        return float(np.clip(zoom, min(.01, self._fit_zoom()), max(8.0, self._fit_zoom())))

    def _apply_zoom(self, zoom, anchor=None):
        if self.image is None:
            return
        anchor = QPointF(anchor) if anchor is not None else QPointF(self.rect().center())
        zoom = self._clamp_zoom(zoom)
        ratio = zoom / self.zoom
        center = QPointF(self.width() / 2, self.height() / 2)
        self.offset = (anchor - center) * (1 - ratio) + self.offset * ratio
        self.zoom = zoom
        self.fit_mode = False
        self._update_target()
        self._update_cursor()
        self.update()

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.25)

    def fit_image(self):
        self.zoom_animation.stop()
        self.fit_mode = True
        self._update_target()
        self._update_cursor()
        self.update()

    def resizeEvent(self, event):
        self.zoom_animation.stop()
        self._update_target()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor('#eaece4'))
        if self.image is None:
            painter.setPen(QColor('#b5beaa'))
            center = self.rect().center()
            page = QRectF(center.x() - 30, center.y() - 58, 60, 78)
            painter.setBrush(QColor('#f6f7f1'))
            painter.drawRoundedRect(page, 3, 3)
            for y in (-32, -20, -8):
                painter.drawLine(center.x() - 17, center.y() + y, center.x() + 17, center.y() + y)
            painter.setPen(QColor('#858e7a'))
            painter.drawText(QRectF(8, center.y() + 40, self.width() - 16, 55), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, '选择本地图片\n在这里查看' + ('原图与框选' if self.editable else '扫描结果'))
            return
        painter.drawImage(self.target, self.image)
        if self.editable and self.corners is not None:
            points = [QPointF(self.target.x() + p[0] * self.target.width(), self.target.y() + p[1] * self.target.height()) for p in self.corners]
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path.closeSubpath()
            outside = QPainterPath()
            outside.addRect(self.target)
            painter.fillPath(outside.subtracted(path), QColor(20, 30, 12, 80))
            painter.setPen(QPen(QColor('#91b46d'), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            for index, point in enumerate(points):
                selected = index == self.selected_corner
                painter.setBrush(QColor('#91b46d' if selected else '#fdfef8'))
                radius = 9 if selected else 7
                painter.drawEllipse(point, radius, radius)
        painter.end()

    def _near_corner(self, point):
        if self.corners is None or self.target.isEmpty():
            return None
        positions = self.corners * [self.target.width(), self.target.height()] + [self.target.x(), self.target.y()]
        distances = np.linalg.norm(positions - [point.x(), point.y()], axis=1)
        index = int(np.argmin(distances))
        return index if distances[index] < 20 else None

    def mousePressEvent(self, event):
        if self.image is None:
            return
        self.zoom_animation.stop()
        if self.editable and event.button() == Qt.MouseButton.LeftButton:
            self.drag_index = self._near_corner(event.position())
            if self.drag_index is not None:
                self.selected_corner = self.drag_index
                self.corner_update_timer.stop()
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                self.update()
        if self.drag_index is None and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_index is not None and not self.target.isEmpty():
            point = event.position()
            self.corners[self.drag_index] = np.clip([(point.x() - self.target.x()) / self.target.width(), (point.y() - self.target.y()) / self.target.height()], 0, 1)
            self.update()
        elif self.pan_start is not None:
            self.offset += event.position() - self.pan_start
            self.pan_start = event.position()
            self._update_target()
            self.update()
        else:
            self._update_cursor(event.position())

    def _update_cursor(self, point=None):
        if self.image is None:
            cursor = Qt.CursorShape.ArrowCursor
        elif self.pan_start is not None:
            cursor = Qt.CursorShape.ClosedHandCursor
        elif self.editable and point is not None and self._near_corner(point) is not None:
            cursor = Qt.CursorShape.SizeAllCursor
        else:
            cursor = Qt.CursorShape.OpenHandCursor
        self.setCursor(cursor)

    def mouseReleaseEvent(self, event):
        if self.drag_index is not None and event.button() == Qt.MouseButton.LeftButton:
            self.drag_index = None
            self.corner_edit_pending = True
            self._commit_corner_edit()
        self.pan_start = None
        self._update_cursor(event.position())

    def select_corner(self, index):
        if self.image is None or self.corners is None:
            return
        self.zoom_animation.stop()
        self.selected_corner = index
        point = self.target.topLeft() + QPointF(self.corners[index][0] * self.target.width(),
                                                self.corners[index][1] * self.target.height())
        if not QRectF(self.rect()).adjusted(28, 28, -28, -28).contains(point):
            self.fit_mode = False
            self.offset = QPointF((.5 - self.corners[index][0]) * self.target.width(),
                                  (.5 - self.corners[index][1]) * self.target.height())
            self._update_target()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def keyPressEvent(self, event):
        directions = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                      Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if (event.key() not in directions or not self.editable or self.corners is None
                or self.selected_corner is None or self.drag_index is not None):
            super().keyPressEvent(event)
            return
        self.corner_update_timer.stop()
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        delta = np.array(directions[event.key()]) * step / [max(1, self.image.width() - 1), max(1, self.image.height() - 1)]
        before = self.corners[self.selected_corner].copy()
        self.corners[self.selected_corner] = np.clip(before + delta, 0, 1)
        self.corner_edit_pending |= not np.array_equal(before, self.corners[self.selected_corner])
        self.update()
        event.accept()

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.corner_edit_pending:
            if not event.isAutoRepeat():
                self.corner_update_timer.start()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._commit_corner_edit()
        super().focusOutEvent(event)

    def _commit_corner_edit(self):
        self.corner_update_timer.stop()
        if self.corner_edit_pending:
            self.corner_edit_pending = False
            self.corners_changed.emit(self.corners.copy().tolist())

    def wheelEvent(self, event):
        if self.image is None or self.drag_index is not None or self.pan_start is not None:
            event.ignore()
            return
        delta = event.pixelDelta().y() or event.angleDelta().y()
        if not delta:
            event.ignore()
            return
        # 连续滚动时累计目标比例，避免上一帧尚未完成就丢失滚动量。
        target = self.zoom_animation.endValue() if self.zoom_animation.state() == QAbstractAnimation.State.Running else self.zoom
        target = self._clamp_zoom(target * 1.25 ** max(-8, min(8, delta / 120)))
        self.zoom_animation.stop()
        self.wheel_anchor = event.position()
        with QSignalBlocker(self.zoom_animation):
            self.zoom_animation.setStartValue(self.zoom)
            self.zoom_animation.setEndValue(target)
        self.zoom_animation.start()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_index = None
            self.pan_start = None
            self.fit_image()
            event.accept()


class FileListDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # 文字由行内控件显示，列表仍负责选中和悬停背景。
        option.text = ''


class FileNameLabel(QLabel):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        text = '\n'.join(self.fontMetrics().elidedText(line, Qt.TextElideMode.ElideMiddle, self.width())
                         for line in self.text().splitlines())
        painter.drawText(self.contentsRect(), self.alignment(), text)


class FileRow(QWidget):
    clicked = Signal()

    def __init__(self, item, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 6, 9)
        layout.setSpacing(6)
        self.thumbnail = QLabel('…')
        self.thumbnail.setFixedSize(40, 40)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.thumbnail.setStyleSheet('background: #eaece4; border-radius: 3px; color: #757c6b;')
        self.thumbnail.hide()
        layout.addWidget(self.thumbnail)
        self.name_label = FileNameLabel()
        self.name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.name_label, 1)
        self.remove_button = QPushButton('移除')
        self.remove_button.setObjectName('quiet')
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.setToolTip('仅从队列移除，保留原文件和已导出结果')
        layout.addWidget(self.remove_button)
        self.refresh(item)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def refresh(self, item):
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.setText(item.text())
        self.name_label.setStyleSheet(f'color: {item.foreground().color().name()};' if item.foreground().style() != Qt.BrushStyle.NoBrush else '')
        self.setToolTip(item.toolTip())
        self.remove_button.setAccessibleName(f'移除 {item.text().splitlines()[0]}')
        item.setSizeHint(self.sizeHint())

    def show_thumbnail(self, enabled, item):
        self.thumbnail.setVisible(enabled)
        if not enabled:
            self.clear_thumbnail()
        item.setSizeHint(self.sizeHint())

    def clear_thumbnail(self):
        self.thumbnail.clear()
        self.thumbnail.setText('…')
        self.thumbnail.setToolTip('')

    def set_thumbnail(self, image):
        if image.isNull():
            self.thumbnail.setText('—')
            self.thumbnail.setToolTip('无法生成缩略图')
            return
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(2)
        self.thumbnail.setPixmap(pixmap)


class MainWindow(QMainWindow):
    preview_ready = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1360, 900)
        self.setMinimumSize(1120, 760)
        self.setAcceptDrops(True)
        self.settings = QSettings('PaperScanner', '纸页扫描')
        self.items: list[WorkItem] = []
        self.worker = None
        self.last_result = None
        self.close_when_done = False
        self.batch_ok = self.batch_failed = 0
        self.is_exporting = False
        self.preview_pending = False
        self.source_folder = None
        self.thumbnail_loader = ThumbnailLoader(self)
        self.thumbnail_loader.ready.connect(self._thumbnail_ready)
        self.thumbnail_rows = {}
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.setInterval(50)
        self.thumbnail_timer.timeout.connect(self._load_visible_thumbnails)
        self._build()
        self._restore()
        self._update_options()

    def _build(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        head = QHBoxLayout(header)
        head.setContentsMargins(24, 18, 24, 17)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(42, 42))
        head.addWidget(icon)
        title = QVBoxLayout()
        title.setSpacing(3)
        title.addWidget(label(APP_NAME, 'title'))
        title.addWidget(label('本地图片 · 文档校正 · 彩色增强', 'subtitle'))
        head.addLayout(title)
        head.addStretch()
        head.addWidget(label('所有图片均在本机处理', 'muted'))
        self.about_button = QPushButton('关于')
        self.about_button.clicked.connect(self.show_about)
        head.addWidget(self.about_button)
        outer.addWidget(header)
        body = QVBoxLayout()
        body.setContentsMargins(22, 16, 22, 16)
        body.setSpacing(14)
        source_row = QHBoxLayout()
        self.source_label = QLineEdit()
        self.source_label.setReadOnly(True)
        self.source_label.setPlaceholderText('选择一个图片目录，或将图片和文件夹拖入窗口')
        self.source_button = QPushButton('选择目录')
        self.source_button.clicked.connect(self.choose_folder)
        self.add_button = QPushButton('添加图片')
        self.add_button.clicked.connect(self.choose_files)
        source_row.addWidget(self.source_label, 1)
        source_row.addWidget(self.source_button)
        source_row.addWidget(self.add_button)
        body.addLayout(source_row)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setObjectName('panel')
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 14, 12, 12)
        top = QHBoxLayout()
        self.count_label = label('图片队列 · 0', 'section')
        top.addWidget(self.count_label)
        top.addStretch()
        self.clear_button = QPushButton('清空')
        self.clear_button.setObjectName('quiet')
        self.clear_button.clicked.connect(self.clear_files)
        top.addWidget(self.clear_button)
        left_layout.addLayout(top)
        self.file_list = QListWidget()
        self.file_list.setItemDelegate(FileListDelegate(self.file_list))
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.currentRowChanged.connect(self.select_item)
        self.file_viewport = self.file_list.viewport()
        self.file_viewport.installEventFilter(self)
        self.file_list.verticalScrollBar().valueChanged.connect(self._schedule_thumbnails)
        left_layout.addWidget(self.file_list, 1)
        self.thumbnail_check = QCheckBox('显示缩略图')
        self.thumbnail_check.setToolTip('按需加载可见图片的 40×40 缩略图；关闭后释放缩略图缓存。')
        self.thumbnail_check.toggled.connect(self._toggle_thumbnails)
        left_layout.addWidget(self.thumbnail_check)
        self.recursive = QCheckBox('包含子目录')
        self.recursive.toggled.connect(self.reload_folder)
        left_layout.addWidget(self.recursive)
        split.addWidget(left)
        center = QWidget()
        preview_layout = QVBoxLayout(center)
        preview_layout.setContentsMargins(2, 0, 2, 0)
        preview_layout.setSpacing(10)
        bar = QHBoxLayout()
        bar.addWidget(label('图像工作区', 'section'))
        bar.addStretch()
        self.rotate_button = QPushButton('旋转 90°')
        self.rotate_button.clicked.connect(self.rotate)
        self.reset_button = QPushButton('重新框选')
        self.reset_button.clicked.connect(self.reset_corners)
        bar.addWidget(self.rotate_button)
        bar.addWidget(self.reset_button)
        preview_layout.addLayout(bar)
        comparison = QSplitter(Qt.Orientation.Horizontal)
        self.original_canvas, self.output_canvas = ImageCanvas(True), ImageCanvas()
        self.original_canvas.corners_changed.connect(self.corners_changed)
        for name, canvas in (('原图 · 拖动四角调整', self.original_canvas), ('扫描结果', self.output_canvas)):
            panel = QFrame()
            panel.setObjectName('panel')
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            caption = label(name, 'eyebrow')
            caption.setContentsMargins(14, 12, 10, 10)
            layout.addWidget(caption)
            zoom_bar = QHBoxLayout()
            zoom_bar.setContentsMargins(8, 0, 8, 8)
            zoom_bar.setSpacing(4)
            zoom_label = label('—', 'eyebrow')
            zoom_label.setMinimumWidth(40)
            zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            zoom_buttons = []
            for text, tip, action in (
                ('−', '缩小画布', canvas.zoom_out),
                ('+', '放大画布', canvas.zoom_in),
                ('适应', '完整显示图片（双击画布）', canvas.fit_image),
                ('100%', '按原始像素查看细节', lambda checked=False, canvas=canvas: canvas.set_zoom(1.0)),
            ):
                button = QPushButton(text)
                button.setStyleSheet('padding: 4px;')
                button.setToolTip(tip)
                button.setAccessibleName(f'{name.split(" · ")[0]}：{tip}')
                button.clicked.connect(action)
                zoom_buttons.append(button)
            zoom_bar.addWidget(zoom_buttons[0])
            zoom_bar.addWidget(zoom_buttons[1])
            zoom_bar.addWidget(zoom_label)
            zoom_bar.addStretch()
            zoom_bar.addWidget(zoom_buttons[2])
            zoom_bar.addWidget(zoom_buttons[3])

            def update_zoom(zoom, caption=zoom_label, buttons=zoom_buttons):
                caption.setText(f'{zoom * 100:.0f}%' if zoom else '—')
                for button in buttons:
                    button.setEnabled(zoom > 0)

            canvas.zoom_changed.connect(update_zoom)
            update_zoom(0)
            layout.addLayout(zoom_bar)
            if canvas is self.original_canvas:
                corner_bar = QHBoxLayout()
                corner_bar.setContentsMargins(8, 0, 8, 8)
                corner_bar.setSpacing(4)
                corner_bar.addWidget(label('微调', 'eyebrow'))
                for index, text in enumerate(('左上', '右上', '右下', '左下')):
                    button = QPushButton(text)
                    button.setStyleSheet('padding: 4px;')
                    button.setEnabled(False)
                    button.setToolTip(f'定位{text}角，方向键微调 1 像素；Shift + 方向键调整 10 像素')
                    button.clicked.connect(lambda checked=False, index=index: self.original_canvas.select_corner(index))
                    canvas.corners_available.connect(button.setEnabled)
                    corner_bar.addWidget(button)
                layout.addLayout(corner_bar)
            else:
                hint = label('选中角点后用方向键微调，Shift 加速', 'eyebrow')
                hint.setContentsMargins(8, 0, 8, 8)
                hint.setMinimumHeight(zoom_buttons[0].sizeHint().height() + 8)
                layout.addWidget(hint)
            layout.addWidget(canvas, 1)
            comparison.addWidget(panel)
        comparison.setSizes([350, 350])
        preview_layout.addWidget(comparison, 1)
        self.image_info = label('左右均可滚轮缩放、拖动平移，双击适应窗口；拖动原图四角可修正框选。', 'muted', True)
        preview_layout.addWidget(self.image_info)
        self.message = label('', None, True)
        self.message.setMinimumHeight(38)
        preview_layout.addWidget(self.message)
        actions = QHBoxLayout()
        self.preview_button = QPushButton('更新预览')
        self.preview_button.clicked.connect(self.start_preview)
        self.open_button = QPushButton('打开输出目录')
        self.open_button.clicked.connect(self.open_output)
        actions.addWidget(self.preview_button)
        actions.addStretch()
        actions.addWidget(self.open_button)
        preview_layout.addLayout(actions)
        split.addWidget(center)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        right = QFrame()
        right.setObjectName('panel')
        controls = QVBoxLayout(right)
        controls.setContentsMargins(17, 17, 17, 17)
        controls.setSpacing(12)
        controls.addWidget(label('扫描设置', 'section'))
        self.auto_crop = QCheckBox('自动识别纸边与透视校正')
        self.auto_crop.setChecked(True)
        self.auto_enhance = QCheckBox('去阴影与彩色增强')
        self.auto_enhance.setChecked(True)
        controls.addWidget(self.auto_crop)
        controls.addWidget(self.auto_enhance)
        self.fill_frame_check = QCheckBox('纸面铺满图片（清除背景细边）')
        self.fill_frame_check.setChecked(True)
        self.fill_frame_check.setToolTip('扫描增强后清除纸边外残留的桌面背景，保留内容位置和分辨率。')
        controls.addWidget(self.fill_frame_check)
        self.auto_crop.toggled.connect(self._update_options)
        self.auto_enhance.toggled.connect(self._update_options)
        self.curve_check = QCheckBox('曲面展平（弯曲纸张时启用）')
        self.curve_check.setToolTip('调用两阶段曲面模型；平整纸张建议关闭，避免改变手绘线条。')
        controls.addWidget(self.curve_check)
        strength_row = QHBoxLayout()
        strength_row.addWidget(label('增强强度'))
        self.strength_label = label('100%', 'muted')
        strength_row.addStretch()
        strength_row.addWidget(self.strength_label)
        controls.addLayout(strength_row)
        self.strength = QSlider(Qt.Orientation.Horizontal)
        self.strength.setRange(0, 100)
        self.strength.setValue(100)
        self.strength.valueChanged.connect(self.strength_changed)
        controls.addWidget(self.strength)
        self.black_white = QCheckBox('黑白文字（淡字转黑、笔画加粗）')
        self.black_white.setToolTip('在去阴影和彩色增强后转纯黑白，彩色印章等也会转黑白。勾选或取消勾选后自动更新预览，每次启动默认关闭。')
        self.black_white.toggled.connect(self._update_options)
        self.black_white.toggled.connect(self._request_preview)
        controls.addWidget(self.black_white)
        self.black_threshold = QSpinBox()
        self.black_threshold.setRange(1, 255)
        self.black_threshold.setValue(180)
        self.black_threshold.setToolTip('灰度低于阈值转黑，其余转白。值越大保留的淡字越多，也越容易带入背景。关闭彩色增强可直接按原图灰度判断。')
        self.stroke_radius = QSpinBox()
        self.stroke_radius.setRange(0, 3)
        self.stroke_radius.setValue(1)
        self.stroke_radius.setSuffix(' px')
        self.stroke_radius.setToolTip('在校正后的完整分辨率上向外扩展黑色笔画；0 不加粗。过大会导致相邻笔画粘连，无法恢复完全缺失的笔画。')
        for caption, widget in (('黑白阈值', self.black_threshold), ('加粗半径', self.stroke_radius)):
            row = QHBoxLayout()
            row.addWidget(label(caption))
            row.addStretch()
            row.addWidget(widget)
            controls.addLayout(row)
        controls.addWidget(label('纯黑白请导出 PNG；JPEG 压缩会产生灰度。', 'muted', True))
        controls.addSpacing(8)
        controls.addWidget(label('导出分辨率', 'section'))
        self.size_mode = QComboBox()
        self.size_mode.addItems(['原始 · 100%', '缩放至 70%', '缩放至 50%', '自定义比例', '自定义宽高'])
        self.size_mode.setToolTip('原始指透视校正后的完整像素；百分比同时作用于宽和高。')
        self.size_mode.currentIndexChanged.connect(self._update_options)
        controls.addWidget(self.size_mode)
        self.percent = QDoubleSpinBox()
        self.percent.setRange(1, 200)
        self.percent.setValue(80)
        self.percent.setSuffix(' %')
        controls.addWidget(self.percent)
        self.dimensions = QWidget()
        dim = QHBoxLayout(self.dimensions)
        dim.setContentsMargins(0, 0, 0, 0)
        self.width_input, self.height_input = QSpinBox(), QSpinBox()
        for widget, name in ((self.width_input, '宽'), (self.height_input, '高')):
            widget.setRange(0, 30000)
            widget.setSpecialValueText(f'{name}：自动')
            widget.setSuffix(' px')
            widget.setToolTip('保持长宽比。只填一边自动计算另一边；同时填写表示最大宽高范围。')
            dim.addWidget(widget)
        self.width_input.setValue(2000)
        controls.addWidget(self.dimensions)
        self.size_help = label('保留校正后的完整像素。', 'muted', True)
        controls.addWidget(self.size_help)
        controls.addSpacing(8)
        controls.addWidget(label('文件体积', 'section'))
        self.limit_check = QCheckBox('限制单张文件大小')
        self.limit_check.toggled.connect(self._update_options)
        controls.addWidget(self.limit_check)
        self.max_mb = QDoubleSpinBox()
        self.max_mb.setDecimals(2)
        self.max_mb.setRange(0.01, 1000)
        self.max_mb.setValue(2)
        self.max_mb.setSuffix(' MB')
        controls.addWidget(self.max_mb)
        controls.addWidget(label('JPEG 先调整质量，再按需缩图。\n1 MB = 1,000,000 字节。', 'muted', True))
        format_row = QHBoxLayout()
        format_row.addWidget(label('格式'))
        self.format = QComboBox()
        self.format.addItems(['JPEG', 'PNG'])
        self.format.currentIndexChanged.connect(self._update_options)
        format_row.addWidget(self.format, 1)
        controls.addLayout(format_row)
        quality_row = QHBoxLayout()
        quality_row.addWidget(label('JPEG 质量'))
        self.quality = QSpinBox()
        self.quality.setRange(60, 100)
        self.quality.setValue(95)
        quality_row.addWidget(self.quality, 1)
        controls.addLayout(quality_row)
        controls.addSpacing(8)
        controls.addWidget(label('输出目录', 'section'))
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText('默认保存到来源目录 / 扫描结果')
        controls.addWidget(self.output_path)
        self.output_button = QPushButton('选择输出位置')
        self.output_button.clicked.connect(self.choose_output)
        controls.addWidget(self.output_button)
        controls.addWidget(label('同名结果自动编号，保留源图片。', 'muted', True))
        controls.addStretch()
        self.export_button = QPushButton('批量导出全部图片')
        self.export_button.setObjectName('primary')
        self.export_button.clicked.connect(self.start_export)
        controls.addWidget(self.export_button)
        self.cancel_button = QPushButton('停止处理')
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setVisible(False)
        controls.addWidget(self.cancel_button)
        right.setAutoFillBackground(True)
        scroll.viewport().setAutoFillBackground(True)
        scroll.setWidget(right)
        settings_panel = QFrame()
        settings_panel.setObjectName('panel')
        right.setObjectName('settings_content')
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)
        settings_layout.addWidget(scroll, 1)
        footer = QVBoxLayout()
        footer.setContentsMargins(17, 12, 17, 16)
        footer.addWidget(self.export_button)
        footer.addWidget(self.cancel_button)
        settings_layout.addLayout(footer)
        # 按完整设置内容预留宽度，包含自定义宽高、边框和纵向滚动条。
        scroll.setMinimumWidth(max(
            360,
            right.minimumSizeHint().width()
            + scroll.verticalScrollBar().sizeHint().width()
            + 2 * scroll.frameWidth(),
        ))
        split.addWidget(settings_panel)
        split.setCollapsible(2, False)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([210, 730, max(380, settings_panel.minimumSizeHint().width())])
        body.addWidget(split, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)
        self.status_label = label('就绪 · 支持 JPG、PNG、TIFF、BMP、WebP', 'muted')
        body.addWidget(self.status_label)
        outer.addLayout(body, 1)
        self.mutating_controls = [self.source_button, self.add_button, self.clear_button, self.file_list, self.recursive, self.auto_crop, self.auto_enhance, self.fill_frame_check, self.curve_check, self.strength, self.black_white, self.black_threshold, self.stroke_radius, self.size_mode, self.percent, self.dimensions, self.limit_check, self.max_mb, self.format, self.quality, self.output_path, self.output_button, self.preview_button, self.rotate_button, self.reset_button, self.export_button]
        self._update_enabled()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f'关于{APP_NAME}')
        dialog.setWindowIcon(self.windowIcon())
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(64, 64))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        for text, style in ((APP_NAME, 'title'), (f'版本：{APP_VERSION}', None),
                            (f'作者：{APP_AUTHOR}', None), (APP_COPYRIGHT, 'muted')):
            caption = label(text, style)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(caption)
        close_button = QPushButton('关闭')
        close_button.setDefault(True)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()
        dialog.deleteLater()

    def _restore(self):
        self.size_mode.setCurrentIndex(int(self.settings.value('size_mode', 0)))
        self.percent.setValue(float(self.settings.value('percent', 80)))
        self.width_input.setValue(int(self.settings.value('width', 2000)))
        self.height_input.setValue(int(self.settings.value('height', 0)))
        self.max_mb.setValue(float(self.settings.value('max_mb', 2)))
        self.quality.setValue(int(self.settings.value('quality', 95)))
        self.format.setCurrentText(self.settings.value('format', 'JPEG'))
        self.limit_check.setChecked(self.settings.value('limit', False, type=bool))
        self.thumbnail_check.setChecked(self.settings.value('show_thumbnails', False, type=bool))
        self.black_white.setChecked(False)
        self.black_threshold.setValue(int(self.settings.value('black_threshold', 180)))
        self.stroke_radius.setValue(int(self.settings.value('stroke_radius', 1)))

    def _save_settings(self):
        self.settings.setValue('show_thumbnails', self.thumbnail_check.isChecked())
        self.settings.setValue('black_threshold', self.black_threshold.value())
        self.settings.setValue('stroke_radius', self.stroke_radius.value())
        for key, value in {'size_mode': self.size_mode.currentIndex(), 'percent': self.percent.value(), 'width': self.width_input.value(), 'height': self.height_input.value(), 'max_mb': self.max_mb.value(), 'quality': self.quality.value(), 'format': self.format.currentText(), 'limit': self.limit_check.isChecked()}.items():
            self.settings.setValue(key, value)

    def _update_options(self, *args):
        if not hasattr(self, 'size_help'):
            return
        index = self.size_mode.currentIndex()
        self.percent.setVisible(index == 3)
        self.dimensions.setVisible(index == 4)
        self.max_mb.setEnabled(self.limit_check.isChecked() and self.worker is None)
        self.fill_frame_check.setEnabled(self.auto_crop.isChecked() and self.auto_enhance.isChecked() and self.worker is None)
        self.black_threshold.setEnabled(self.black_white.isChecked() and self.worker is None)
        self.stroke_radius.setEnabled(self.black_white.isChecked() and self.worker is None)
        self.quality.setEnabled(self.format.currentText() == 'JPEG' and self.worker is None)
        self.size_help.setText(['保留校正后的完整像素。', '宽、高各为原来的 70%。', '宽、高各为原来的 50%。', '按输入百分比等比例缩放。', '保持长宽比；同时填写时适配最大宽高。'][index])

    def _update_enabled(self):
        enabled = bool(self.items) and self.worker is None
        for widget in (self.preview_button, self.export_button, self.rotate_button, self.reset_button):
            widget.setEnabled(enabled)

    def show_message(self, text='', error=False):
        self.message.setStyleSheet('color: #a14d35;' if error else 'color: #5b7049;')
        self.message.setText(text)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择图片目录', self.settings.value('last_input', str(Path.home() / 'Pictures')))
        if folder:
            self.load_folder(Path(folder))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '添加图片', str(self.source_folder or Path.home()), '图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)')
        if paths:
            self.add_files([Path(path) for path in paths])

    def load_folder(self, folder):
        self.source_folder = folder.resolve()
        self.settings.setValue('last_input', str(folder))
        self.source_label.setText(str(self.source_folder))
        if not self.output_path.text():
            self.output_path.setText(str(self.source_folder / '扫描结果'))
        try:
            pattern = folder.rglob('*') if self.recursive.isChecked() else folder.iterdir()
            output = Path(self.output_path.text()).expanduser().resolve()
            paths = [path for path in pattern if path.is_file() and path.suffix.lower() in EXTENSIONS and output not in path.resolve().parents and not any(part.startswith('.') for part in path.relative_to(folder).parts)]
            self.clear_files()
            self.source_label.setText(str(self.source_folder))
            self.add_files(paths)
            if not paths:
                self.show_message('此目录没有支持的图片，可以切换“包含子目录”或添加图片。')
        except OSError as error:
            self.show_message(f'无法读取目录：{error}', True)

    def reload_folder(self):
        if self.source_folder and self.worker is None:
            self.load_folder(self.source_folder)

    def add_files(self, paths):
        existing = {item.path for item in self.items}
        def natural(path):
            return [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)', str(path))]
        added = 0
        for path in sorted(paths, key=natural):
            path = path.resolve()
            if path in existing or path.suffix.lower() not in EXTENSIONS:
                continue
            existing.add(path)
            self.items.append(WorkItem(path))
            row = QListWidgetItem(path.name)
            row.setToolTip(str(path))
            self.file_list.addItem(row)
            content = FileRow(row)
            content.clicked.connect(lambda row=row: self.file_list.setCurrentItem(row))
            content.remove_button.clicked.connect(lambda checked=False, row=row: self.remove_file(row))
            self.file_list.setItemWidget(row, content)
            content.show_thumbnail(self.thumbnail_check.isChecked(), row)
            added += 1
        if self.items and not self.output_path.text():
            self.output_path.setText(str(self.items[0].path.parent / '扫描结果'))
        if not self.source_folder:
            self.source_label.setText(f'已添加 {len(self.items)} 张本地图片')
        self.count_label.setText(f'图片队列 · {len(self.items)}')
        self._update_enabled()
        if added:
            self.file_list.setCurrentRow(len(self.items) - 1)
            self.file_list.scrollToItem(self.file_list.currentItem())
        elif self.file_list.currentRow() < 0 and self.items:
            self.file_list.setCurrentRow(0)
        self._schedule_thumbnails()

    def clear_files(self):
        if self.worker:
            return
        self.thumbnail_timer.stop()
        self.thumbnail_loader.clear()
        self.thumbnail_rows.clear()
        self.file_list.clear()
        self.items.clear()
        self.last_result = None
        self.original_canvas.set_image()
        self.output_canvas.set_image()
        self.count_label.setText('图片队列 · 0')
        if not self.source_folder:
            self.source_label.clear()
        self.image_info.setText('左右均可滚轮缩放、拖动平移，双击适应窗口；拖动原图四角可修正框选。')
        self.show_message()
        self._update_enabled()

    def remove_file(self, row):
        if self.worker is not None:
            return
        index = self.file_list.row(row)
        if index < 0:
            return
        if len(self.items) == 1:
            self.clear_files()
            return
        current = self.selected()
        removed = self.items[index]
        self.thumbnail_rows.pop(str(removed.path), None)
        # 删除过程中阻止行号变化触发预览，等数据与列表同步后再更新。
        with QSignalBlocker(self.file_list):
            self.items.pop(index)
            self.file_list.takeItem(index)
            if removed is current:
                self.file_list.setCurrentRow(min(index, len(self.items) - 1))
        self.count_label.setText(f'图片队列 · {len(self.items)}')
        if not self.source_folder:
            self.source_label.setText(f'已添加 {len(self.items)} 张本地图片')
        self._update_enabled()
        if removed is current:
            self.select_item(self.file_list.currentRow())
        self._schedule_thumbnails()

    def eventFilter(self, watched, event):
        # 销毁期间不能再通过 QListWidget 查询已经释放的 viewport。
        if watched is self.file_viewport and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._schedule_thumbnails()
        return False

    def _schedule_thumbnails(self, *args):
        if hasattr(self, 'thumbnail_check') and self.thumbnail_check.isChecked():
            self.thumbnail_timer.start()

    def _toggle_thumbnails(self, enabled):
        current = self.file_list.currentItem()
        keep_current_visible = current is not None and self.file_list.visualItemRect(current).intersects(self.file_list.viewport().rect())
        self.thumbnail_timer.stop()
        self.thumbnail_loader.clear()
        self.thumbnail_rows.clear()
        for index in range(self.file_list.count()):
            row = self.file_list.item(index)
            self.file_list.itemWidget(row).show_thumbnail(enabled, row)
        self.file_list.doItemsLayout()
        if keep_current_visible:
            self.file_list.scrollToItem(current)
        self._schedule_thumbnails()

    def _load_visible_thumbnails(self):
        if not self.thumbnail_check.isChecked():
            return
        viewport = self.file_list.viewport()
        first = self.file_list.indexAt(QPoint(1, 0)).row()
        last = self.file_list.indexAt(QPoint(1, max(0, viewport.height() - 1))).row()
        visible = {}
        if viewport.isVisible() and viewport.height() > 0 and first >= 0:
            if last < 0:
                last = self.file_list.count() - 1
            for index in range(first, last + 1):
                row = self.file_list.item(index)
                visible[str(self.items[index].path)] = self.file_list.itemWidget(row)
        # 行控件只保留当前可见图片，避免滚动后每一行都持有 QPixmap。
        for path, content in self.thumbnail_rows.items():
            if path not in visible:
                content.clear_thumbnail()
        self.thumbnail_rows = visible
        self.thumbnail_loader.request(visible)

    def _thumbnail_ready(self, path, image):
        if self.thumbnail_check.isChecked() and path in self.thumbnail_rows:
            self.thumbnail_rows[path].set_thumbnail(image)

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, '选择输出目录', self.output_path.text() or str(Path.home()))
        if folder:
            self.output_path.setText(folder)

    def selected(self):
        index = self.file_list.currentRow()
        return self.items[index] if 0 <= index < len(self.items) else None

    def select_item(self, index):
        if index < 0 or self.worker:
            return
        self.last_result = None
        self.original_canvas.set_image()
        self.output_canvas.set_image()
        self.show_message()
        self.start_preview()

    def corners_changed(self, corners):
        item = self.selected()
        if item:
            item.corners = corners
            self.start_preview()

    def rotate(self):
        item = self.selected()
        if item:
            item.rotation = (item.rotation + 90) % 360
            item.corners = None
            self.original_canvas.fit_image()
            self.output_canvas.fit_image()
            self.start_preview()

    def reset_corners(self):
        item = self.selected()
        if item:
            item.corners = None
            self.start_preview()

    def scan_options(self):
        return ScanOptions(auto_crop=self.auto_crop.isChecked(), enhance=self.auto_enhance.isChecked(),
                           strength=self.strength.value() / 100, dewarp=self.curve_check.isChecked(),
                           fill_frame=self.fill_frame_check.isChecked(), black_white=self.black_white.isChecked(),
                           black_threshold=self.black_threshold.value(), stroke_radius=self.stroke_radius.value())

    def strength_changed(self, value):
        self.strength_label.setText(f'{value}%')
        self._request_preview()

    def _request_preview(self, *args):
        if not self.selected() or self.close_when_done:
            return
        if self.worker:
            # 计算期间合并刷新请求，完成后读取最新的强度与模式开关。
            if not self.is_exporting and not self.worker.cancel_event.is_set():
                self.preview_pending = True
            return
        self.start_preview()

    def export_options(self):
        index = self.size_mode.currentIndex()
        mode = 'original' if index == 0 else 'custom' if index == 4 else 'percent'
        percent = 70 if index == 1 else 50 if index == 2 else self.percent.value()
        options = ExportOptions(mode, percent, self.width_input.value(), self.height_input.value(), self.format.currentText(), self.quality.value(), self.max_mb.value() if self.limit_check.isChecked() else None)
        options.validate()
        return options

    def _launch(self, worker, exporting=False):
        self.worker = worker
        self.is_exporting = exporting
        self._save_settings()
        self.original_canvas.editable = False
        self.original_canvas.update()
        for widget in self.mutating_controls:
            if widget in (self.strength, self.black_white) and not exporting:
                continue
            widget.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, len(worker.items) if exporting else 0)
        self.progress.setValue(0)
        worker.result.connect(self.receive)
        worker.status.connect(self.status_label.setText)
        worker.finished.connect(self._idle)
        worker.start()

    def start_preview(self):
        item = self.selected()
        if not item or self.worker:
            return
        self.preview_pending = False
        self.show_message('正在识别纸边与生成扫描预览…')
        self._launch(Worker([WorkItem(item.path, item.rotation, item.corners)], self.scan_options(), parent=self))

    def start_export(self):
        if not self.items or self.worker:
            return
        try:
            options = self.export_options()
            if not self.output_path.text().strip():
                raise ValueError('请选择输出目录')
            output = Path(self.output_path.text()).expanduser().resolve()
            if output.exists() and not output.is_dir():
                raise ValueError('输出位置是文件，请选择目录')
            output.mkdir(parents=True, exist_ok=True)
        except (ValueError, OSError) as error:
            self.show_message(str(error), True)
            return
        self.batch_ok = self.batch_failed = 0
        self.show_message('正在批量处理，源图片保持不变。')
        tasks = [WorkItem(item.path, item.rotation, item.corners) for item in self.items]
        self._launch(Worker(tasks, self.scan_options(), output, options, self), exporting=True)

    def receive(self, message):
        kind = message['kind']
        if kind == 'preview':
            result = message['result']
            self.last_result = result
            self.original_canvas.set_image(result.original, result.corners if self.auto_crop.isChecked() else None)
            self.output_canvas.set_image(result.image, preserve_view=True)
            item = self.selected()
            if item:
                self.image_info.setText(f'{item.path.name}  ·  原图 {result.original.width} × {result.original.height}  →  扫描 {result.image.width} × {result.image.height}  ·  {result.seconds:.1f} 秒')
            self.show_message(result.warning or '预览已更新，可调整导出尺寸和文件大小。')
            self.preview_ready.emit()
        elif kind in {'export', 'error'}:
            index = next((i for i, item in enumerate(self.items) if str(item.path) == message['path']), None)
            if kind == 'export':
                self.batch_ok += 1
                encoded = message['encoded']
                if index is not None:
                    self.file_list.item(index).setText(f"{self.items[index].path.name}\n{encoded.width} × {encoded.height} · {len(encoded.data) / 1e6:.2f} MB")
                    self.file_list.item(index).setForeground(QColor('#496436'))
                    self.file_list.item(index).setToolTip(message['output'] + ('\n' + message['warning'] if message['warning'] else ''))
            else:
                self.batch_failed += 1
                if index is not None:
                    self.file_list.item(index).setForeground(QColor('#a14d35'))
                    self.file_list.item(index).setToolTip(message['error'])
                self.show_message(f"{Path(message['path']).name}：{message['error']}", True)
            if index is not None:
                row = self.file_list.item(index)
                self.file_list.itemWidget(row).refresh(row)
            self.progress.setValue(message.get('index', 0))
        elif kind == 'record_error':
            self.show_message(f"图片已保存，但处理记录写入失败：{message['error']}", True)

    def _idle(self):
        worker = self.worker
        cancelled = worker.cancel_event.is_set()
        self.worker = None
        self.original_canvas.editable = self.auto_crop.isChecked()
        self.original_canvas.update()
        for widget in self.mutating_controls:
            widget.setEnabled(True)
        self._update_options()
        self._update_enabled()
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if self.is_exporting and not cancelled else 0)
        self.cancel_button.setVisible(False)
        if self.is_exporting:
            self.show_message(f"{'处理已停止' if cancelled else '导出完成'}：成功 {self.batch_ok} 张，失败 {self.batch_failed} 张。", self.batch_failed > 0)
            self.status_label.setText(f'已保存到 {self.output_path.text()}')
        elif cancelled:
            self.show_message('预览已取消')
        else:
            self.status_label.setText('就绪 · 增强强度和黑白文字开关自动更新预览，其他扫描设置修改后点击更新预览')
        worker.deleteLater()
        if self.close_when_done:
            self.close()
        elif self.preview_pending and not cancelled:
            self.start_preview()

    def cancel(self):
        self.preview_pending = False
        if self.worker:
            self.worker.cancel()
            self.strength.setEnabled(False)
            self.black_white.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.status_label.setText('正在停止，等待当前计算完成…')

    def open_output(self):
        path = Path(self.output_path.text()).expanduser()
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        else:
            self.show_message('输出目录尚未创建，请先导出图片。')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.worker is None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.worker:
            return
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        folders = [path for path in paths if path.is_dir()]
        if folders:
            self.load_folder(folders[0])
        self.add_files([path for path in paths if path.is_file()])
        event.acceptProposedAction()

    def closeEvent(self, event):
        self.original_canvas.corner_update_timer.stop()
        self.original_canvas.corner_edit_pending = False
        if self.worker:
            self.close_when_done = True
            self.cancel()
            event.ignore()
        else:
            self.file_viewport.removeEventFilter(self)
            self.thumbnail_timer.stop()
            self.thumbnail_loader.close()
            self._save_settings()
            event.accept()


def configure_application(application):
    # 使用随包分发的 PNG，避免局部 QSS 与系统主题混用时丢失默认箭头。
    QDir.addSearchPath('scanner_icons', str(Path(__file__).resolve().parent / 'assets'))
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.styleHints().setColorScheme(Qt.ColorScheme.Light)
    application.setStyle('Fusion')
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: '#f5f4f0',
        QPalette.ColorRole.WindowText: '#292d28',
        QPalette.ColorRole.Base: '#fbfbf8',
        QPalette.ColorRole.AlternateBase: '#f0f2e9',
        QPalette.ColorRole.Text: '#292d28',
        QPalette.ColorRole.PlaceholderText: '#697360',
        QPalette.ColorRole.Button: '#fbfbf8',
        QPalette.ColorRole.ButtonText: '#292d28',
        QPalette.ColorRole.Highlight: '#e8eddf',
        QPalette.ColorRole.HighlightedText: '#354b25',
        QPalette.ColorRole.ToolTipBase: '#303a29',
        QPalette.ColorRole.ToolTipText: '#ffffff',
    }.items():
        palette.setColor(role, QColor(color))
    application.setPalette(palette)
    application.setStyleSheet(STYLE)


def main():
    application = QApplication(sys.argv)
    configure_application(application)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_dir():
            QTimer.singleShot(0, lambda: window.load_folder(path))
        elif path.is_file():
            QTimer.singleShot(0, lambda: window.add_files([path]))
    return application.exec()
