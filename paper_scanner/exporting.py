"""输出尺寸、严格体积限制与不覆盖源文件的保存逻辑。"""
from dataclasses import dataclass
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile

from PIL import Image


@dataclass(frozen=True)
class ExportOptions:
    mode: str = 'original'
    percent: float = 100
    width: int = 0
    height: int = 0
    format: str = 'JPEG'
    quality: int = 95
    max_mb: float | None = None

    def validate(self):
        if self.mode not in {'original', 'percent', 'custom'}:
            raise ValueError('请选择有效的分辨率设置')
        if self.mode == 'percent' and not 1 <= self.percent <= 200:
            raise ValueError('缩放比例必须在 1% 到 200% 之间')
        if self.mode == 'custom' and (max(self.width, self.height) <= 0 or min(self.width, self.height) < 0):
            raise ValueError('自定义尺寸至少填写一个大于零的宽或高')
        if max(self.width, self.height) > 30000:
            raise ValueError('自定义边长不能超过 30000 像素')
        if self.format not in {'JPEG', 'PNG'}:
            raise ValueError('仅支持 JPEG 或 PNG 输出')
        if not 60 <= self.quality <= 100:
            raise ValueError('JPEG 质量必须在 60 到 100 之间')
        if self.max_mb is not None and (not math.isfinite(self.max_mb) or not 0.01 <= self.max_mb <= 1000):
            raise ValueError('文件上限必须在 0.01 MB 到 1000 MB 之间')


@dataclass
class EncodedImage:
    data: bytes
    width: int
    height: int
    quality: int | None
    resized_for_limit: bool


def target_size(size: tuple[int, int], options: ExportOptions) -> tuple[int, int]:
    options.validate()
    width, height = size
    if width < 1 or height < 1:
        raise ValueError('图片尺寸无效')
    if options.mode == 'original':
        scale = 1.0
    elif options.mode == 'percent':
        scale = options.percent / 100
    else:
        factors = []
        if options.width:
            factors.append(options.width / width)
        if options.height:
            factors.append(options.height / height)
        scale = min(factors)
    result = max(1, round(width * scale)), max(1, round(height * scale))
    if result[0] * result[1] > 80_000_000:
        raise ValueError('输出超过 8000 万像素，请减小自定义尺寸')
    return result


def _encode(image: Image.Image, options: ExportOptions, quality: int) -> bytes:
    buffer = BytesIO()
    if options.format == 'JPEG':
        image.save(buffer, 'JPEG', quality=quality, subsampling=0, optimize=False)
    else:
        image.save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


def encode_image(image: Image.Image, options: ExportOptions) -> EncodedImage:
    """优先保持像素，必要时在质量下限后缩图；每次返回前核对字节数。"""
    requested = target_size(image.size, options)
    image = image.convert('RGB')
    if image.size != requested:
        image = image.resize(requested, Image.Resampling.LANCZOS)
    limit = int(options.max_mb * 1_000_000) if options.max_mb is not None else None
    for _ in range(80):
        data = _encode(image, options, options.quality)
        if limit is None or len(data) <= limit:
            return EncodedImage(data, *image.size, options.quality if options.format == 'JPEG' else None, image.size != requested)
        smallest = data
        if options.format == 'JPEG':
            smallest = _encode(image, options, 60)
            if len(smallest) <= limit:
                best_data, best_quality = smallest, 60
                low, high = 61, options.quality - 1
                while low <= high:
                    middle = (low + high) // 2
                    candidate = _encode(image, options, middle)
                    if len(candidate) <= limit:
                        best_data, best_quality = candidate, middle
                        low = middle + 1
                    else:
                        high = middle - 1
                return EncodedImage(best_data, *image.size, best_quality, image.size != requested)
        if image.size == (1, 1):
            raise ValueError('文件上限过小，无法生成符合上限的图片')
        factor = min(0.9, max(0.1, math.sqrt(limit / len(smallest)) * 0.92))
        next_size = max(1, int(image.width * factor)), max(1, int(image.height * factor))
        image = image.resize(next_size, Image.Resampling.LANCZOS)
    raise ValueError('无法在指定体积内完成导出，请提高文件上限')


def save_unique(encoded: EncodedImage, directory: Path, stem: str, format_name: str) -> Path:
    """同名文件使用序号，原文件与已存在的结果均不覆盖。"""
    directory.mkdir(parents=True, exist_ok=True)
    suffix = '.jpg' if format_name == 'JPEG' else '.png'
    candidate = directory / f'{stem}_扫描{suffix}'
    index = 2
    while True:
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.close(descriptor)
            break
        except FileExistsError:
            candidate = directory / f'{stem}_扫描_{index}{suffix}'
            index += 1
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.scan-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded.data)
        os.replace(temporary, candidate)
    except Exception:
        candidate.unlink(missing_ok=True)
        if temporary:
            temporary.unlink(missing_ok=True)
        raise
    return candidate
