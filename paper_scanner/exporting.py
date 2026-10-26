"""输出尺寸、严格体积限制与不覆盖源文件的保存逻辑。"""
from dataclasses import dataclass
from io import BytesIO
import math
import os
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class ExportOptions:
    mode: str = 'original'
    percent: float = 100
    width: int = 0
    height: int = 0
    format: str = 'JPEG'
    quality: int = 95
    max_mb: float | None = None
    watermark_text: str = ''
    watermark_color: str = '#808080'
    watermark_size: int = 36

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
        if len(self.watermark_text) > 100 or any(ord(char) < 32 or ord(char) == 127 for char in self.watermark_text):
            raise ValueError('水印文字最多 100 个字符，不能包含换行或控制字符')
        if re.fullmatch(r'#[0-9a-fA-F]{6}', self.watermark_color) is None:
            raise ValueError('水印颜色必须为 #RRGGBB，例如 #808080')
        if type(self.watermark_size) is not int or not 8 <= self.watermark_size <= 300:
            raise ValueError('水印字号必须为 8 到 300 之间的整数像素')


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
        if image.mode == '1':
            image = image.convert('RGB')
        image.save(buffer, 'JPEG', quality=quality, subsampling=0, optimize=False)
    else:
        image.save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


def _resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    if image.mode == '1':
        # 缩放后重新二值化，既保留抗锯齿采样，又避免 PNG 中重新出现灰度。
        gray = image.convert('L').resize(size, Image.Resampling.LANCZOS)
        return gray.point(lambda value: 255 if value >= 128 else 0, mode='1')
    return image.resize(size, Image.Resampling.LANCZOS)


def _watermark_font(size: int) -> ImageFont.FreeTypeFont:
    """直接使用系统中文字体，命令行不加载 Qt 或依赖界面线程。"""
    windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [
        windows_fonts / 'msyh.ttc', windows_fonts / 'simhei.ttf', windows_fonts / 'simsun.ttc',
        Path('/System/Library/Fonts/PingFang.ttc'),
        Path('/System/Library/Fonts/STHeiti Medium.ttc'),
        Path('/System/Library/Fonts/Supplemental/Songti.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    raise ValueError('未找到可用的系统中文字体，请安装微软雅黑、黑体或 Noto Sans CJK 后重试')


def apply_watermark(image: Image.Image, options: ExportOptions) -> Image.Image:
    """用倾斜重复文字叠加半透明水印，保留传入图片。"""
    text = options.watermark_text.strip()
    if not text:
        return image
    font = _watermark_font(options.watermark_size)
    left, top, right, bottom = font.getbbox(text)
    # 小图或长文字自动缩小；限制单个印章尺寸，避免创建整图旋转画布。
    max_width = max(1, min(4096, int(min(image.size) * 1.2)))
    if right - left > max_width:
        font = font.font_variant(size=max(1, int(font.size * max_width / (right - left))))
        left, top, right, bottom = font.getbbox(text)
    padding = 2
    mask = Image.new('L', (max(1, right - left) + padding * 2, max(1, bottom - top) + padding * 2))
    ImageDraw.Draw(mask).text((padding - left, padding - top), text, font=font, fill=128)
    stamp = mask.rotate(45, resample=Image.Resampling.BICUBIC, expand=True).point(lambda value: min(value, 128))
    output = image.convert('RGB')
    step_x, step_y = stamp.width + font.size * 2, stamp.height + font.size * 2
    center_x, center_y = (image.width - stamp.width) // 2, (image.height - stamp.height) // 2
    for y in range(center_y % step_y - step_y, image.height, step_y):
        for x in range(center_x % step_x - step_x, image.width, step_x):
            output.paste(options.watermark_color, (x, y, x + stamp.width, y + stamp.height), stamp)
    return output


def encode_image(image: Image.Image, options: ExportOptions) -> EncodedImage:
    """优先保持像素，必要时在质量下限后缩图；每次返回前核对字节数。"""
    requested = target_size(image.size, options)
    if image.mode != '1':
        image = image.convert('RGB')
    if image.size != requested:
        image = _resize(image, requested)
    image = apply_watermark(image, options)
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
        image = _resize(image, next_size)
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
    except BaseException:
        # Ctrl+C 也要清理预留文件和临时文件，避免留下空的扫描结果。
        candidate.unlink(missing_ok=True)
        if temporary:
            temporary.unlink(missing_ok=True)
        raise
    return candidate
