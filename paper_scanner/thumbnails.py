"""按可见队列串行生成缩略图，限制缓存并丢弃过期结果。"""
from collections import OrderedDict
import threading

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage


def read_thumbnail(path, size=80):
    try:
        with Image.open(path) as image:
            # JPEG 优先利用解码器缩小尺寸；其他格式也只保留小图结果。
            image.draft('RGB', (size, size))
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            image = ImageOps.contain(ImageOps.exif_transpose(image), (size, size),
                                     Image.Resampling.LANCZOS).convert('RGBA')
            return QImage(image.tobytes(), image.width, image.height,
                          image.width * 4, QImage.Format.Format_RGBA8888).copy()
    except Exception:
        # 损坏或不支持的图片使用占位，不能阻塞后续图片。
        return QImage()


class ThumbnailSignals(QObject):
    finished = Signal(object)


class ThumbnailTask(QRunnable):
    def __init__(self, path, generation):
        super().__init__()
        self.path = path
        self.generation = generation
        self.signals = ThumbnailSignals()
        self.cancelled = threading.Event()

    def run(self):
        if self.cancelled.is_set():
            return
        image = read_thumbnail(self.path)
        if not self.cancelled.is_set():
            try:
                self.signals.finished.emit((self.generation, self.path, image))
            except RuntimeError:
                # QApplication 退出时可能已销毁信号对象。
                pass


class ThumbnailLoader(QObject):
    ready = Signal(str, QImage)

    def __init__(self, parent=None, cache_limit=128):
        super().__init__(parent)
        self.cache_limit = cache_limit
        self.cache = OrderedDict()
        self.paths = []
        self.pending = []
        self.active = None
        self.generation = 0
        self.closed = False

    def request(self, paths):
        if self.closed:
            return
        self.paths = list(dict.fromkeys(str(path) for path in paths))
        self.pending = [path for path in self.paths if path not in self.cache]
        for path in self.paths:
            if path in self.cache:
                self.cache.move_to_end(path)
                self.ready.emit(path, self.cache[path])
        self._start_next()

    def clear(self):
        self.generation += 1
        self.paths.clear()
        self.pending.clear()
        self.cache.clear()

    def close(self):
        self.closed = True
        if self.active is not None:
            self.active.cancelled.set()
        self.clear()

    def _start_next(self):
        if self.closed or self.active is not None:
            return
        while self.pending and self.pending[0] in self.cache:
            self.pending.pop(0)
        if not self.pending:
            return
        path = self.pending.pop(0)
        self.active = ThumbnailTask(path, self.generation)
        self.active.signals.finished.connect(self._finished)
        # 每次只提交一张；滚动、关闭开关后，尚未提交的图片不会被读取。
        QThreadPool.globalInstance().start(self.active)

    @Slot(object)
    def _finished(self, result):
        generation, path, image = result
        self.active = None
        if not self.closed and generation == self.generation:
            self.cache[path] = image
            while len(self.cache) > self.cache_limit:
                self.cache.popitem(last=False)
            if path in self.paths:
                self.ready.emit(path, image)
        self._start_next()
