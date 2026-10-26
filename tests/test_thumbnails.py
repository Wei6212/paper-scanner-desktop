"""验证缩略图按需读取、后台串行、缓存上限及开关期间的过期结果。"""
import os
from pathlib import Path
import threading
import time
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
import pytest
from PySide6.QtCore import QEvent, QSettings, QThreadPool, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from paper_scanner import thumbnails, ui


@pytest.fixture(scope='session')
def application():
    app = QApplication.instance() or QApplication([])
    ui.configure_application(app)
    return app


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), '后台缩略图未在预期时间内完成'


@pytest.fixture
def window(application, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    monkeypatch.setattr(ui, 'QSettings', lambda *args: settings)
    widget = ui.MainWindow()
    widget.start_preview = lambda: None
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    QThreadPool.globalInstance().waitForDone(5000)
    application.processEvents()
    widget.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_small_image_size_orientation_and_invalid_file(tmp_path):
    path = tmp_path / '横图.jpg'
    image = Image.new('RGB', (400, 100), '#e03020')
    image.save(path)
    thumbnail = thumbnails.read_thumbnail(path)
    assert (thumbnail.width(), thumbnail.height()) == (80, 20)
    assert thumbnail.pixelColor(0, 0).red() > 200
    exif = image.getexif()
    exif[274] = 6
    image.save(path, exif=exif)
    thumbnail = thumbnails.read_thumbnail(path)
    assert (thumbnail.width(), thumbnail.height()) == (20, 80)
    path.write_bytes(b'broken image')
    assert thumbnails.read_thumbnail(path).isNull()


def test_disable_discards_active_result_and_pending_reads(application, monkeypatch):
    started, release = threading.Event(), threading.Event()
    reads, received = [], []
    main_thread = threading.get_ident()

    def read(path):
        reads.append((path, threading.get_ident()))
        started.set()
        release.wait(5)
        return QImage(80, 80, QImage.Format.Format_RGB32)

    monkeypatch.setattr(thumbnails, 'read_thumbnail', read)
    loader = thumbnails.ThumbnailLoader()
    loader.ready.connect(lambda path, image: received.append(path))
    try:
        loader.request(['第一张', '第二张'])
        wait_until(started.is_set)
        loader.clear()
        release.set()
        wait_until(lambda: loader.active is None)
        assert [path for path, _ in reads] == ['第一张']
        assert reads[0][1] != main_thread
        assert not loader.cache and not received
    finally:
        release.set()
        loader.close()
        QThreadPool.globalInstance().waitForDone(5000)


def test_scroll_replaces_pending_images(application, monkeypatch):
    started, release = threading.Event(), threading.Event()
    reads, received = [], []

    def read(path):
        reads.append(path)
        if path == '离开视野':
            started.set()
            release.wait(5)
        return QImage(80, 80, QImage.Format.Format_RGB32)

    monkeypatch.setattr(thumbnails, 'read_thumbnail', read)
    loader = thumbnails.ThumbnailLoader()
    loader.ready.connect(lambda path, image: received.append(path))
    try:
        loader.request(['离开视野', '尚未读取'])
        wait_until(started.is_set)
        loader.request(['新的可见图片'])
        release.set()
        wait_until(lambda: loader.active is None and received == ['新的可见图片'])
        assert reads == ['离开视野', '新的可见图片']
        loader.request(['新的可见图片'])
        assert reads == ['离开视野', '新的可见图片']
    finally:
        release.set()
        loader.close()
        QThreadPool.globalInstance().waitForDone(5000)


def test_cache_is_bounded_without_repeated_decoding(application, monkeypatch):
    reads, received = [], []

    def read(path):
        reads.append(path)
        return QImage(80, 80, QImage.Format.Format_RGB32)

    monkeypatch.setattr(thumbnails, 'read_thumbnail', read)
    loader = thumbnails.ThumbnailLoader(cache_limit=2)
    loader.ready.connect(lambda path, image: received.append(path))
    loader.request(['一', '二', '三'])
    wait_until(lambda: loader.active is None and len(received) == 3)
    assert reads == ['一', '二', '三']
    assert list(loader.cache) == ['二', '三']
    loader.close()


def test_checkbox_visible_rows_and_release(window, application, monkeypatch, tmp_path):
    reads = []

    def read(path):
        reads.append(path)
        return QImage(80, 80, QImage.Format.Format_RGB32)

    monkeypatch.setattr(thumbnails, 'read_thumbnail', read)
    window.add_files([tmp_path / f'{index:03}.jpg' for index in range(100)])
    QTest.qWait(80)
    assert not window.thumbnail_check.isChecked()
    assert not reads
    window.thumbnail_check.setChecked(True)
    wait_until(lambda: bool(window.thumbnail_rows) and window.thumbnail_loader.active is None)
    assert 0 < len(reads) < 100
    row = window.file_list.currentItem()
    content = window.file_list.itemWidget(row)
    assert content.thumbnail.width() == content.thumbnail.height() == 40
    assert not content.thumbnail.pixmap().isNull()
    window.file_list.scrollToTop()
    wait_until(lambda: str(tmp_path / '000.jpg') in window.thumbnail_rows)
    wait_until(lambda: window.thumbnail_loader.active is None)
    assert content.thumbnail.pixmap() is None or content.thumbnail.pixmap().isNull()
    first = window.file_list.itemWidget(window.file_list.item(0))
    QTest.mouseClick(first, Qt.MouseButton.LeftButton, pos=first.thumbnail.geometry().center())
    assert window.file_list.currentRow() == 0
    window.thumbnail_check.setChecked(False)
    assert not window.thumbnail_loader.cache
    assert not window.thumbnail_rows
    assert first.thumbnail.isHidden()
    assert first.thumbnail.pixmap() is None or first.thumbnail.pixmap().isNull()
    window._save_settings()
    assert not window.settings.value('show_thumbnails', True, type=bool)
    window.thumbnail_check.setChecked(True)
    window._save_settings()
    window.thumbnail_check.setChecked(False)
    window._restore()
    assert window.thumbnail_check.isChecked()


def test_clear_queue_during_load_ignores_deleted_rows(window, monkeypatch, tmp_path):
    started, release = threading.Event(), threading.Event()

    def read(path):
        started.set()
        release.wait(5)
        return QImage(80, 80, QImage.Format.Format_RGB32)

    monkeypatch.setattr(thumbnails, 'read_thumbnail', read)
    try:
        window.add_files([tmp_path / '一.jpg', tmp_path / '二.jpg'])
        window.thumbnail_check.setChecked(True)
        wait_until(started.is_set)
        window.remove_file(window.file_list.currentItem())
        window.clear_files()
        release.set()
        wait_until(lambda: window.thumbnail_loader.active is None)
        assert not window.thumbnail_rows
        assert not window.thumbnail_loader.cache
        assert window.file_list.count() == 0
    finally:
        release.set()


@pytest.mark.parametrize('loading', [False, True])
def test_application_shutdown_with_thumbnail_filter(tmp_path, loading):
    source = '''
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from paper_scanner import thumbnails, ui
import sys
import time
app = QApplication([])
ui.configure_application(app)
settings = QSettings(str(Path(sys.argv[1]) / 'shutdown.ini'), QSettings.Format.IniFormat)
ui.QSettings = lambda *args: settings
if sys.argv[2] == 'True':
    def slow_read(path):
        time.sleep(.5)
        return QImage(80, 80, QImage.Format.Format_RGB32)
    thumbnails.read_thumbnail = slow_read
window = ui.MainWindow()
window.start_preview = lambda: None
window.show()
window.add_files([Path('不存在.jpg')])
window.thumbnail_check.setChecked(True)
def finish():
    window.close()
    app.quit()
QTimer.singleShot(150, finish)
app.exec()
'''
    result = subprocess.run([sys.executable, '-c', source, str(tmp_path), str(loading)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert 'Traceback' not in result.stderr
