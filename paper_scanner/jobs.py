"""后台顺序处理，支持取消与单文件失败后继续。"""
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from .engine import Cancelled, ScanOptions, Scanner
from .exporting import ExportOptions, encode_image, save_unique


@dataclass
class WorkItem:
    path: Path
    rotation: int = 0
    corners: list | None = None


class Worker(QThread):
    result = Signal(object)
    status = Signal(str)

    def __init__(self, items: list[WorkItem], scan: ScanOptions, output: Path | None = None, export: ExportOptions | None = None, parent=None):
        super().__init__(parent)
        self.items = items
        self.scan = scan
        self.output = output
        self.export_options = export
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        scanner = Scanner()
        rows = []
        for index, item in enumerate(self.items):
            if self.cancel_event.is_set():
                break
            self.status.emit(f'正在处理 {index + 1} / {len(self.items)} · {item.path.name}')
            try:
                result = scanner.process(item.path, self.scan, item.corners if self.scan.auto_crop else None, item.rotation, self.cancel_event)
                if self.output is None:
                    self.result.emit({'kind': 'preview', 'path': str(item.path), 'result': result})
                else:
                    encoded = encode_image(result.image, self.export_options)
                    if self.cancel_event.is_set():
                        break
                    output = save_unique(encoded, self.output, item.path.stem, self.export_options.format)
                    row = {'源文件': str(item.path), '输出文件': str(output), '宽': encoded.width, '高': encoded.height, '字节': len(encoded.data), 'JPEG质量': encoded.quality or '', '体积限制缩图': '是' if encoded.resized_for_limit else '否', '状态': '完成', '说明': result.warning}
                    rows.append(row)
                    self.result.emit({'kind': 'export', 'path': str(item.path), 'output': str(output), 'encoded': encoded, 'warning': result.warning, 'index': index + 1})
            except Cancelled:
                break
            except Exception as error:
                message = str(error) or type(error).__name__
                rows.append({'源文件': str(item.path), '状态': '失败', '说明': message})
                self.result.emit({'kind': 'error', 'path': str(item.path), 'error': message, 'index': index + 1})
                traceback.print_exc()
        if self.output is not None and rows:
            try:
                record = self.output / f'处理记录_{datetime.now():%Y%m%d_%H%M%S_%f}.csv'
                columns = ['源文件', '输出文件', '宽', '高', '字节', 'JPEG质量', '体积限制缩图', '状态', '说明']
                with record.open('x', encoding='utf-8-sig', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
            except OSError as error:
                self.result.emit({'kind': 'record_error', 'error': str(error)})
