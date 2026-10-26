"""精修纸边外侧的细窄背景，保留内容坐标与边缘笔迹。"""
import cv2
import numpy as np


def _boundary(strip: np.ndarray, depth: int) -> np.ndarray | None:
    """沿长边追踪纸张过渡，剔除文字造成的短距离边缘峰值。"""
    lab = cv2.GaussianBlur(strip.astype(np.float32), (19, 3), 0)
    light = lab[..., 0]
    chroma = np.linalg.norm(lab[..., 1:] - 128, axis=2)
    drop = np.median(chroma[:3]) - np.median(chroma[depth // 2:depth])
    light_gradient = np.maximum(np.diff(light, axis=0), 0)
    chroma_gradient = np.maximum(-np.diff(chroma, axis=0), 0)
    if drop > 3:
        score = np.minimum(light_gradient, 4) * 0.15 + 3 * np.minimum(chroma_gradient, 4)
        threshold = 0.6
    else:
        score = np.minimum(light_gradient, 8) + chroma_gradient
        threshold = 1.5
    score = cv2.GaussianBlur(score, (1, 5), 0)[:depth]
    score *= np.exp(-np.arange(depth)[:, None] / (depth * 0.8))
    peaks = np.argmax(score, axis=0)
    positions = np.arange(strip.shape[1])
    inside = np.minimum(peaks + 6, len(light) - 1)
    jump = light[inside, positions] - light[0, positions]
    color_drop = chroma[0, positions] - chroma[inside, positions]
    valid = (score[peaks, positions] > threshold) & ((jump > 7) | (color_drop > 4))
    ends = max(1, strip.shape[1] // 20)
    valid[:ends] = valid[-ends:] = False
    if valid.mean() < 0.5 or np.count_nonzero(valid) < 12:
        return None
    x = np.linspace(-1, 1, len(positions))
    offsets = peaks.astype(np.float32) + 3
    keep = valid.copy()
    for _ in range(5):
        polynomial = np.polynomial.Polynomial.fit(x[keep], offsets[keep], 3)
        residual = offsets - polynomial(x)
        median = np.median(residual[keep])
        deviation = max(1.0, np.median(np.abs(residual[keep] - median)))
        selected = valid & (residual < median + 2.5 * deviation) & (residual > median - 3.5 * deviation)
        if np.count_nonzero(selected) < 12:
            break
        keep = selected
    return np.clip(polynomial(x), 0, depth).astype(np.float32)


def fill_document_frame(source: np.ndarray, enhanced: np.ndarray) -> np.ndarray:
    """只清除已确认的纸边外背景，不缩放、拉伸或移动图片中的内容。"""
    if source.shape != enhanced.shape:
        raise ValueError('纸边精修的原图和增强图尺寸必须一致')
    height, width = source.shape[:2]
    if min(height, width) < 80:
        return enhanced
    output = enhanced.copy() if np.shares_memory(source, enhanced) else enhanced
    orientations = [
        (source, output),
        (source[::-1], output[::-1]),
        (source.transpose(1, 0, 2), output.transpose(1, 0, 2)),
        (source.transpose(1, 0, 2)[::-1], output.transpose(1, 0, 2)[::-1]),
    ]
    for original, target in orientations:
        depth = min(original.shape[0] - 9, max(8, round(original.shape[0] * 0.035)))
        # 只读取边缘窄带，避免为整张高分辨率图片创建 Lab 浮点副本。
        strip = cv2.cvtColor(np.ascontiguousarray(original[:depth + 8]), cv2.COLOR_RGB2LAB)
        boundary = _boundary(strip, depth)
        if boundary is None:
            continue
        values = strip[:depth].astype(np.float32)
        rows = np.arange(depth)[:, None]
        outside = rows < boundary[None, :]
        background = np.median(values[:3].reshape(-1, 3), axis=0)
        similar_background = np.linalg.norm(values - background, axis=2) < 13
        # 纸角轻微卷曲时，补清最外侧约 1% 内与背景同色的小三角。
        outside |= (rows < max(2, round(original.shape[0] * 0.01))) & similar_background
        chroma = np.linalg.norm(values[..., 1:] - 128, axis=2)
        protected_ink = ((values[..., 0] < 100) & (chroma < 7)) | (chroma > 35)
        target[:depth][outside & ~protected_ink] = 255
    return output
