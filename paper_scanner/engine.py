"""文档检测、透视校正与模型辅助的彩色去光照。"""
from dataclasses import dataclass
from pathlib import Path
import sys
import threading
import time

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

from .edges import fill_document_frame


class Cancelled(Exception):
    """用户取消当前处理。"""


def resource_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'models'


def read_image(path: Path, rotation: int = 0) -> Image.Image:
    with Image.open(path) as source:
        if max(source.size) > 30000:
            raise ValueError('图片边长超过 30000 像素，请先缩小后导入')
        if source.width * source.height > 80_000_000:
            raise ValueError('图片超过 8000 万像素，请先缩小后导入')
        source.seek(0)
        image = ImageOps.exif_transpose(source)
        if 'A' in image.getbands():
            rgba = image.convert('RGBA')
            image = Image.new('RGBA', rgba.size, 'white')
            image.alpha_composite(rgba)
        image = image.convert('RGB')
        profile = source.info.get('icc_profile')
        if profile:
            try:
                from io import BytesIO
                image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
            except (ImageCms.PyCMSError, OSError, ValueError):
                pass
        if rotation % 360:
            image = image.rotate(-rotation, expand=True)
        return image.copy()


class Model:
    def __init__(self, path: Path, input_name: str, output_name: str):
        import MNN
        if not path.is_file():
            raise FileNotFoundError(f'缺少模型：{path.name}')
        self.expr = MNN.expr
        self.runtime = MNN.nn.create_runtime_manager(({'backend': 0, 'precision': 'high', 'numThread': 4},))
        self.module = MNN.nn.load_module_from_file(str(path), [input_name], [output_name], runtime_manager=self.runtime)
        if self.module is None:
            raise RuntimeError(f'无法加载模型：{path.name}')

    def run(self, image: np.ndarray) -> np.ndarray:
        data = np.ascontiguousarray(image[None], dtype=np.float32)
        variable = self.expr.placeholder(list(data.shape), self.expr.NHWC)
        variable.write(data)
        result = self.module.forward([self.expr.convert(variable, self.expr.NC4HW4)])
        if isinstance(result, (list, tuple)):
            result = result[0]
        result = self.expr.convert(result, self.expr.NHWC)
        array = np.array(result.read(), dtype=np.float32).reshape(result.shape)
        if not np.isfinite(array).all():
            raise RuntimeError('模型输出包含无效数值')
        return array[0]


@dataclass
class ScanOptions:
    auto_crop: bool = True
    enhance: bool = True
    strength: float = 1.0
    dewarp: bool = False
    fill_frame: bool = True


@dataclass
class ScanResult:
    original: Image.Image
    image: Image.Image
    corners: np.ndarray
    warning: str
    seconds: float


def ordered_quad(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = points.mean(axis=0)
    points = points[np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))]
    return np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)


def validate_quad(points: np.ndarray, width: int, height: int) -> np.ndarray:
    points = ordered_quad(points)
    if not np.isfinite(points).all():
        raise ValueError('裁剪坐标无效')
    points[:, 0] = np.clip(points[:, 0], 0, width - 1)
    points[:, 1] = np.clip(points[:, 1], 0, height - 1)
    if not cv2.isContourConvex(points.reshape(-1, 1, 2)):
        raise ValueError('四个角不能交叉，请重新调整')
    if cv2.contourArea(points) < max(64, width * height * 0.005):
        raise ValueError('框选区域过小，请重新调整四角')
    return points


def warp_document(rgb: np.ndarray, normalized: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    points = validate_quad(normalized * [width - 1, height - 1], width, height)
    tl, tr, br, bl = points
    out_width = max(2, round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))) + 1)
    out_height = max(2, round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))) + 1)
    if out_width * out_height > 80_000_000:
        raise ValueError('校正结果过大，请缩小框选范围')
    target = np.float32([[0, 0], [out_width - 1, 0], [out_width - 1, out_height - 1], [0, out_height - 1]])
    matrix = cv2.getPerspectiveTransform(points, target)
    return cv2.warpPerspective(rgb, matrix, (out_width, out_height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


class Scanner:
    """实例只在创建它的工作线程内使用，避免共享 MNN 执行上下文。"""
    def __init__(self):
        self.detector = None
        self.enhancer = None
        self.dewarp_first = None
        self.dewarp_second = None
        self.owner = threading.get_ident()

    def _check(self, cancel=None):
        if threading.get_ident() != self.owner:
            raise RuntimeError('扫描引擎需要在所属工作线程执行')
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    def detect(self, rgb: np.ndarray) -> tuple[np.ndarray, str]:
        if self.detector is None:
            self.detector = Model(resource_dir() / 'document_detect.mnn', 'hed_input', 'img_output')
        small = cv2.resize(rgb, (384, 384), interpolation=cv2.INTER_AREA)
        heatmaps = self.detector.run(small)
        candidates = []
        for channel in range(heatmaps.shape[-1]):
            heat = heatmaps[..., channel]
            if heat.max() > 1.5:
                heat = heat / 255
            mask = np.uint8(heat > 0.35) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
                area = cv2.contourArea(contour)
                if area < 384 * 384 * 0.12:
                    continue
                hull = cv2.convexHull(contour)
                for epsilon in (0.015, 0.025, 0.04):
                    polygon = cv2.approxPolyDP(hull, epsilon * cv2.arcLength(hull, True), True)
                    if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                        continue
                    quad = ordered_quad(polygon[:, 0, :])
                    quad_area = cv2.contourArea(quad)
                    if quad_area <= 0:
                        continue
                    score = area / (384 * 384) * min(area / quad_area, 1)
                    candidates.append((score, quad / 383))
                    break
        if not candidates:
            return np.float32([[0, 0], [1, 0], [1, 1], [0, 1]]), '纸张边缘不够明确，暂用整图；可拖动四角修正'
        return max(candidates, key=lambda item: item[0])[1].astype(np.float32), ''

    @staticmethod
    def _remap_normalized(rgb: np.ndarray, grid: np.ndarray, size=None) -> np.ndarray:
        height, width = rgb.shape[:2]
        out_width, out_height = size or (width, height)
        result = np.empty((out_height, out_width, 3), dtype=np.uint8)
        grid_x = np.linspace(0, grid.shape[1] - 1, out_width, dtype=np.float32)
        for row in range(0, out_height, 256):
            rows = np.arange(row, min(row + 256, out_height), dtype=np.float32)
            map_x = np.broadcast_to(grid_x, (len(rows), out_width)).copy()
            map_y = np.broadcast_to((rows * (grid.shape[0] - 1) / max(1, out_height - 1))[:, None], map_x.shape).copy()
            local_grid = cv2.remap(grid, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            local_grid[..., 0] = (local_grid[..., 0] + 1) * (width - 1) * 0.5
            local_grid[..., 1] = (local_grid[..., 1] + 1) * (height - 1) * 0.5
            result[row:row + len(rows)] = cv2.remap(rgb, local_grid[..., 0], local_grid[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return result

    def dewarp(self, rgb: np.ndarray, cancel=None) -> tuple[np.ndarray, str]:
        if self.dewarp_first is None:
            self.dewarp_first = Model(resource_dir() / 'document_dewarp.mnn', 'input', 'output')
            self.dewarp_second = Model(resource_dir() / 'document_dewarp_stage2.mnn', 'input', 'output')
        # 第一阶段输入 193，输出 385 的位移场；第二阶段以第一次重映射后的图像为输入。
        flow = self.dewarp_first.run(cv2.resize(rgb, (193, 193), interpolation=cv2.INTER_AREA))
        if flow.shape != (385, 385, 2) or np.abs(flow).max() > 0.5:
            return rgb, '曲面模型输出超出安全范围，已保留透视校正结果'
        axis = np.linspace(-1, 1, 385, dtype=np.float32)
        grid = np.stack(np.meshgrid(axis, axis), axis=-1) + flow
        intermediate = self._remap_normalized(rgb, grid, (385, 385))
        self._check(cancel)
        residual = self.dewarp_second.run(intermediate)
        if residual.shape != grid.shape or np.abs(residual).max() > 0.5:
            return rgb, '曲面细化输出超出安全范围，已保留透视校正结果'
        grid = grid + residual * 0.2
        dx = np.diff(grid, axis=1)[:-1]
        dy = np.diff(grid, axis=0)[:, :-1]
        determinant = dx[..., 0] * dy[..., 1] - dx[..., 1] * dy[..., 0]
        if (determinant <= 0).mean() > 0.01:
            return rgb, '曲面模型产生局部折叠，已跳过展平；可关闭曲面展平重新预览'
        self._check(cancel)
        return self._remap_normalized(rgb, grid), ''

    def enhance(self, rgb: np.ndarray, strength: float) -> np.ndarray:
        if self.enhancer is None:
            self.enhancer = Model(resource_dir() / 'document_enhance.mnn', 'img_input', 'img_output')
        background = self.enhancer.run(cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_AREA))
        background = np.clip(background, 0, 255)
        height, width = rgb.shape[:2]
        background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
        corrected = np.empty_like(rgb)
        for row in range(0, height, 256):
            light = background[row:row + 256]
            values = rgb[row:row + 256].astype(np.float32)
            output = (values * 255 + 765) / np.maximum(light, 1)
            output[light < 0.5] = 255
            corrected[row:row + 256] = np.clip(output, 0, 255).astype(np.uint8)
        del background
        gamma = np.uint8(np.clip(255 * (np.arange(256) / 255) ** 1.4, 0, 255))
        corrected = cv2.LUT(corrected, gamma)
        # 用小图统计亮度分布，将同一个线性变换应用到所有通道以保留颜色。
        preview = cv2.resize(corrected, (max(1, round(width * min(1, 720 / max(width, height)))), max(1, round(height * min(1, 720 / max(width, height))))), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(preview, cv2.COLOR_RGB2GRAY)
        low, high = np.percentile(gray, [0.7, 99.3])
        if high - low > 5:
            span = high - low + 1
            target_span = min(255.0, span * 1.4)
            lower = max(0.0, low - (target_span - span) * 0.5)
            table = np.clip((np.arange(256) - low) * target_span / span + lower, 0, 255).astype(np.uint8)
            corrected = cv2.LUT(corrected, table)
        strength = min(1.0, max(0.0, strength))
        if strength < 1:
            corrected = cv2.addWeighted(rgb, 1 - strength, corrected, strength, 0)
        return corrected

    def process(self, path: Path, options: ScanOptions, corners=None, rotation=0, cancel=None) -> ScanResult:
        self._check(cancel)
        started = time.monotonic()
        original = read_image(path, rotation)
        rgb = np.asarray(original)
        warning = ''
        if corners is not None:
            normalized = np.asarray(corners, dtype=np.float32)
        elif options.auto_crop:
            normalized, warning = self.detect(rgb)
        else:
            normalized = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
        self._check(cancel)
        if options.auto_crop or corners is not None:
            rgb = warp_document(rgb, normalized)
        self._check(cancel)
        if options.dewarp:
            rgb, curve_warning = self.dewarp(rgb, cancel)
            warning = '；'.join(value for value in (warning, curve_warning) if value)
        self._check(cancel)
        if options.enhance:
            unenhanced = rgb
            rgb = self.enhance(rgb, options.strength)
            if options.auto_crop and options.fill_frame:
                rgb = fill_document_frame(unenhanced, rgb)
        self._check(cancel)
        return ScanResult(original, Image.fromarray(rgb), normalized, warning, time.monotonic() - started)
